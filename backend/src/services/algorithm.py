import math
import time
import numpy as np
from scipy import stats
from scipy.ndimage import label

from src.config.domain import DOMAIN

MAX_SHEETS = int(DOMAIN['limits']['max_sheets'])
MAX_GRID = int(DOMAIN['limits']['max_grid'])
ENUM_SECONDS = float(DOMAIN['limits']['enum_seconds'])
# 四邻接连通结构（不含对角）。
STRUCT4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
CHUNK = 2048


class EnumTimeout(RuntimeError):
    pass


def _nan_mean(x, axis):
    """忽略 NaN 的均值；空切片给 NaN 且不产生 RuntimeWarning。"""
    counts = np.isfinite(x).sum(axis=axis)
    sums = np.nansum(x, axis=axis)
    return np.divide(sums, counts, out=np.full_like(sums, np.nan, dtype=float),
                     where=counts > 0)


def _orient(grid, angle):
    """按定位角把格图旋转到统一朝向（逆时针为正，np.rot90 逆时针）。"""
    g = np.asarray(grid, dtype=float)
    turns = {0: 0, 90: 3, 180: 2, 270: 1}[angle]
    return np.rot90(g, turns) if turns else g


def build_sheet_matrices(snapshot):
    """把冻结快照对齐成 (S, R, C) 的两张工艺矩阵，缺测为 NaN；返回每格样本数。"""
    if not snapshot:
        raise ValueError('空批次无法分析')
    if len(snapshot) > MAX_SHEETS:
        raise ValueError(f'排队容量超出 {MAX_SHEETS} 张纸，拒绝排队')
    dims = None
    oriented_shape = None
    a_stack, b_stack, angles, keys = [], [], [], []
    for sheet in snapshot:
        if dims is None:
            dims = (sheet['rows'], sheet['cols'])
        elif (sheet['rows'], sheet['cols']) != dims:
            raise ValueError(f"纸样 {sheet['source_key']} 格图尺寸与同版不一致，无法对齐")
        a = _orient(sheet['grids']['a'], sheet['angle'])
        b = _orient(sheet['grids']['b'], sheet['angle'])
        # 旋转后必须能叠到同一张坐标格图上：矩形格经 90/270 度会交换行列，
        # 与 0/180 度形状不同，物理上无法对齐，明确拒绝。
        if oriented_shape is None:
            oriented_shape = a.shape
        elif a.shape != oriented_shape:
            raise ValueError(
                f"纸样 {sheet['source_key']} 定位角 {sheet['angle']}° 旋转后形状 {a.shape} "
                f"与同版对齐形状 {oriented_shape} 不一致；矩形格图仅支持 0/180 度，"
                "方阵格图方可使用 90/270 度")
        a_stack.append(a)
        b_stack.append(b)
        angles.append(sheet['angle'])
        keys.append(sheet['source_key'])
    A = np.stack(a_stack)  # (S,R,C)
    B = np.stack(b_stack)
    if A.shape[1] > MAX_GRID or A.shape[2] > MAX_GRID:
        raise ValueError(f'每图不得超过 {MAX_GRID}×{MAX_GRID} 格')
    return A, B, keys, angles


def paired_cells(A, B):
    """逐格配对：同纸样两工艺均实测才成对，缺测不补值。返回差值栈与每格样本数。"""
    paired = np.isfinite(A) & np.isfinite(B)          # (S,R,C)
    n = paired.sum(axis=0).astype(int)                 # (R,C) 每格成对样本数
    D = np.where(paired, B - A, np.nan)                # 工艺B − 工艺A
    return D, n


def max_patch_area(mean_diff, threshold, valid_mask):
    """越门槛的同向平均配对差按四邻接连成斑块，返回最大斑块面积与斑块标签/分量。"""
    over = valid_mask & (np.abs(mean_diff) > threshold)
    if not over.any():
        return 0, None, over
    labeled, components = label(over, structure=STRUCT4)
    if components == 0:
        return 0, labeled, over
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0  # 背景
    return int(sizes.max()), labeled, over


def sign_flip_max_patch(D, n, threshold, deadline):
    """
    逐张整图翻转差值：每张纸一次性对其整张差值格图乘同一符号。
    对全部 2^S 种符号组合枚举，统计最大斑块面积 >= 观测值的比例（加一校正）。
    """
    S = D.shape[0]
    valid = n >= 2  # 每格至少两张纸成对实测才进入统计；缺测不补值
    if not valid.any():
        raise ValueError('没有任何格具备至少两张纸的成对实测，无法分析')
    # 观测统计量
    mean_obs = _nan_mean(np.where(valid, D, np.nan), axis=0)
    mean_obs = np.where(valid, mean_obs, 0.0)
    observed_area, labeled_obs, over_obs = max_patch_area(mean_obs, threshold, valid)

    total = 2 ** S
    count_ge = 0
    # 向量化枚举，分块控制内存；含全零符号等所有组合。
    for start in range(0, total, CHUNK):
        if time.perf_counter() > deadline:
            raise EnumTimeout(f'全枚举超过 {ENUM_SECONDS:.0f} 秒限制，已中止')
        codes = np.arange(start, min(total, start + CHUNK), dtype=np.uint64)
        signs = 2 * ((codes[:, None] >> np.arange(S, dtype=np.uint64)) & 1).astype(float) - 1
        # (K,S,1,1)*(1,S,R,C) -> (K,S,R,C) -> 沿纸均值 (K,R,C)
        flipped = signs[:, :, None, None] * D[None, :, :, :]
        means = _nan_mean(flipped, axis=1)
        means = np.where(valid[None, :, :], means, 0.0)
        over = valid[None, :, :] & (np.abs(means) > threshold)
        for k in range(means.shape[0]):
            if not over[k].any():
                continue
            lab, comp = label(over[k], structure=STRUCT4)
            if comp == 0:
                continue
            sizes = np.bincount(lab.ravel())
            sizes[0] = 0
            if int(sizes.max()) >= observed_area:
                count_ge += 1
    # 加一校正，避免 p=0
    p_value = (count_ge + 1) / (total + 1)
    return {
        'mean_diff': mean_obs,
        'valid': valid,
        'observed_area': observed_area,
        'labeled': labeled_obs,
        'over': over_obs,
        'p_value': float(p_value),
        'combinations': int(total),
        'count_ge': int(count_ge),
    }


def _patch_records(labeled, over, mean_diff, n):
    """把斑块整理成前端可标注的记录列表。"""
    if labeled is None or not over.any():
        return []
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    order = np.argsort(sizes)[::-1]
    records = []
    for cid in order:
        if cid == 0 or sizes[cid] == 0:
            continue
        r_idx, c_idx = np.where(labeled == cid)
        cells = [[int(r), int(c)] for r, c in zip(r_idx, c_idx)]
        sign = '正向(B−A>0)' if mean_diff[r_idx[0], c_idx[0]] > 0 else '负向(B−A<0)'
        records.append({
            'patch_id': int(cid),
            'area': int(sizes[cid]),
            'direction': sign,
            'mean_diff_max': float(np.max(np.abs(mean_diff[r_idx, c_idx]))),
            'cells': cells,
        })
    return records


def calculate(snapshot, params):
    threshold = float(params['threshold'])
    started = time.perf_counter()
    deadline = started + ENUM_SECONDS

    A, B, keys, angles = build_sheet_matrices(snapshot)
    S, R, C = A.shape
    D, n = paired_cells(A, B)

    valid = n >= 2
    if not valid.any():
        raise ValueError('每格至少需要两张纸成对实测；当前没有合格格，缺测不补值')

    # —— 保留：原平均色差分析（整纸/逐格平均，会被成片偏差盖住的口径，照用）——
    mean_a = float(np.nanmean(A))
    mean_b = float(np.nanmean(B))
    mean_diff_grid = _nan_mean(np.where(valid, D, np.nan), axis=0)
    mean_diff_grid = np.where(valid, mean_diff_grid, np.nan)
    overall_mean_diff = float(np.nanmean(mean_diff_grid))

    # 配对差的 t 区间（沿用原口径，仅作参考；汇总所有成对差值）
    d_values = D[np.isfinite(D)]
    if d_values.size >= 2:
        sd = float(np.std(d_values, ddof=1))
        se = sd / math.sqrt(d_values.size)
        q = float(stats.t.ppf(.975, d_values.size - 1))
        ci = [overall_mean_diff - q * se, overall_mean_diff + q * se]
    else:
        sd, ci = float('nan'), [float('nan'), float('nan')]

    # —— 新口径：斑块 + 整图符号翻转校正 p ——
    flip = sign_flip_max_patch(D, n, threshold, deadline)
    patches = _patch_records(flip['labeled'], flip['over'], flip['mean_diff'], n)

    # 每格样本数网格（含 0/1 的不合格格，前端标注）
    sample_grid = [[int(n[r, c]) for c in range(C)] for r in range(R)]
    mean_grid = [[None if not valid[r, c] else round(float(flip['mean_diff'][r, c]), 6)
                  for c in range(C)] for r in range(R)]
    label_grid = [[int(flip['labeled'][r, c]) if flip['labeled'] is not None and flip['over'][r, c]
                   else 0 for c in range(C)] for r in range(R)]

    elapsed = time.perf_counter() - started
    metrics = {
        '纸样张数': S,
        '格图尺寸': f'{R}×{C}',
        '参与分析格数': int(valid.sum()),
        '门槛ΔE': threshold,
        '原工艺A平均ΔE': round(mean_a, 6),
        '工艺B平均ΔE': round(mean_b, 6),
        '整图平均配对差(B−A)': round(overall_mean_diff, 6),
        '配对差标准差': round(sd, 6) if math.isfinite(sd) else None,
        '均值差95%t区间': [round(ci[0], 6), round(ci[1], 6)] if all(map(math.isfinite, ci)) else None,
        '最大斑块面积(格)': flip['observed_area'],
        '斑块数量': len(patches),
        '校正p值(加一)': flip['p_value'],
        '符号组合数': flip['combinations'],
        '命中组合数': flip['count_ge'],
        '枚举耗时秒': round(elapsed, 4),
        '计算方法': f'逐张整图符号翻转全枚举 2^{S}={flip["combinations"]}，加一校正',
    }
    interpretation = (
        f"门槛 {threshold:g} ΔE 下检出 {len(patches)} 个四邻接同向斑块，"
        f"最大斑块 {flip['observed_area']} 格；逐张整图翻转 {flip['combinations']} 种符号组合，"
        f"校正 p={flip['p_value']:.6g}（加一）。"
        f"整图平均配对差 {overall_mean_diff:+.4f} ΔE（原平均色差口径，可能掩盖成片套印偏差）。"
    )
    caveat = (
        '每张纸的整张差值格图在零假设下共用一个符号（整图翻转），不逐格独立翻转；'
        '仅四邻接、同向且越过门槛的格连为斑块，对角不连通。每格需≥2张纸成对实测，缺测不补值、不插补；'
        'p 值基于最大斑块面积的全枚举分布并加一校正，全枚举限时 60 秒。'
        '原平均色差分析保留，但成片套印偏差可能在平均中相互抵消。'
    )
    return {
        'metrics': metrics,
        'interpretation': interpretation,
        'caveat': caveat,
        'grid': {
            'rows': R, 'cols': C,
            'threshold': threshold,
            'mean_diff': mean_grid,          # 每格平均配对差
            'samples': sample_grid,         # 每格成对样本数
            'patch_labels': label_grid,     # 斑块标注（0=非斑块）
            'valid_cells': [[bool(valid[r, c]) for c in range(C)] for r in range(R)],
        },
        'patches': patches,
        'sheets': [{'source_key': k, 'angle': a} for k, a in zip(keys, angles)],
        'columns': ['纸样编号', '定位角', '格图尺寸', '工艺A平均ΔE', '工艺B平均ΔE'],
        'rows': [
            [keys[i], angles[i], f'{R}×{C}',
             round(float(np.nanmean(A[i])), 4), round(float(np.nanmean(B[i])), 4)]
            for i in range(S)
        ],
        'table_title': '每张纸样的双工艺对齐与配对概况',
    }
