import math
from src.config.domain import DOMAIN

MAX_SHEETS = int(DOMAIN['limits']['max_sheets'])
MAX_GRID = int(DOMAIN['limits']['max_grid'])
PROCESSES = tuple(p[0] for p in DOMAIN['processes'])
# 定位角：格图在纸样上的旋转/对齐角度，仅允许 0/90/180/270 度。
ANGLES = (0, 90, 180, 270)


def _grid(values, label):
    """校验一张二维格图：规整矩阵、有限非负数值、None 表示缺测。"""
    if not isinstance(values, list) or not values:
        raise ValueError(label + ' 必须为非空二维数组')
    rows = len(values)
    if rows > MAX_GRID:
        raise ValueError(f'{label} 行数 {rows} 超过每图上限 {MAX_GRID}')
    width = None
    for r, line in enumerate(values):
        if not isinstance(line, list) or not line:
            raise ValueError(label + f' 第 {r + 1} 行必须为非空数组')
        if width is None:
            width = len(line)
            if width > MAX_GRID:
                raise ValueError(f'{label} 列数 {width} 超过每图上限 {MAX_GRID}')
        if len(line) != width:
            raise ValueError(label + ' 各行长度必须一致（矩形格图）')
        for cell in line:
            if cell is None:
                continue
            if isinstance(cell, bool):
                raise ValueError(label + ' 格值必须为数值或缺测(null)')
            try:
                v = float(cell)
            except (TypeError, ValueError):
                raise ValueError(label + ' 格值必须为数值或缺测(null)')
            if not math.isfinite(v) or v < 0 or abs(v) > 1e9:
                raise ValueError(label + ' 格值必须为 0 到 1e9 的有限数值')
    return rows, width


def validate_sheet(payload):
    """校验一张纸样的双工艺格图与定位角，返回规范化结构。"""
    if not isinstance(payload, dict):
        raise ValueError('纸样数据格式错误')
    key = payload.get('source_key')
    if not isinstance(key, str) or not key.strip() or len(key) > 100:
        raise ValueError('纸样编号必填且不超过100字符')
    angle = payload.get('angle', 0)
    if isinstance(angle, bool) or not isinstance(angle, int) or angle not in ANGLES:
        raise ValueError('定位角必须为 0/90/180/270 度之一')
    grids = payload.get('grids')
    if not isinstance(grids, dict):
        raise ValueError('必须分别提交两道工艺的色差格图')
    if set(grids) != set(PROCESSES):
        raise ValueError('必须且只能包含工艺A、工艺B两张格图')
    dims = None
    norm = {}
    labels = dict(DOMAIN['processes'])
    for proc in PROCESSES:
        rows, width = _grid(grids[proc], labels[proc])
        if dims is None:
            dims = (rows, width)
        elif (rows, width) != dims:
            raise ValueError('同版两侧格图尺寸必须一致，才能一次性对齐切换')
        norm[proc] = [[None if c is None else float(c) for c in line] for line in grids[proc]]
    return {'source_key': key.strip(), 'angle': angle,
            'rows': dims[0], 'cols': dims[1], 'grids': norm}


def validate_alignability(sheets):
    """排队前校验全部纸样按定位角旋转后能落到同一张坐标格图。"""
    if not sheets:
        raise ValueError('空批次无法分析')
    base_dims = None
    oriented = None
    for s in sheets:
        rows, cols, angle = s['rows'], s['cols'], s['angle']
        if base_dims is None:
            base_dims = (rows, cols)
        elif (rows, cols) != base_dims:
            raise ValueError(f"纸样 {s['source_key']} 格图尺寸与同版不一致，无法对齐")
        shape = (cols, rows) if angle in (90, 270) else (rows, cols)
        if oriented is None:
            oriented = shape
        elif shape != oriented:
            raise ValueError(
                f"纸样 {s['source_key']} 定位角 {angle}° 旋转后形状 {shape} 与同版对齐形状 "
                f"{oriented} 不一致；矩形格图仅支持 0/180 度，方阵格图方可使用 90/270 度")


def validate_parameters(params):
    """运行参数白名单：仅门槛 threshold。"""
    defaults = DOMAIN['defaults']
    if not isinstance(params, dict) or set(params) - set(defaults):
        raise ValueError('存在未知分析参数；仅允许门槛 threshold')
    p = dict(defaults)
    p.update(params)
    t = p['threshold']
    if isinstance(t, bool) or not isinstance(t, (int, float)):
        raise ValueError('门槛必须为数值')
    t = float(t)
    if not math.isfinite(t) or not (0 < t <= 1000):
        raise ValueError('门槛必须为大于 0 且不超过 1000 的有限 ΔE 值')
    p['threshold'] = t
    return p
