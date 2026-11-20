import os
import json
import csv
import io
from pathlib import Path
from redis import Redis
from sqlalchemy import select
from fastapi import HTTPException
from src.models.run import Run
from src.models.review import Review
from src.services import studies
from src.services.grid_validation import (
    validate_parameters, validate_alignability, MAX_SHEETS, MAX_GRID)
from src.services.audits import log
from src.utils.serializers import record, now, checksum


def _freeze(rows):
    """排队时冻结配对格图与门槛所用快照：只保留分析必需字段。"""
    snapshot = []
    for x in rows:
        if x['rows'] > MAX_GRID or x['cols'] > MAX_GRID:
            raise HTTPException(422, f"纸样 {x['source_key']} 格图超过每图 {MAX_GRID}×{MAX_GRID} 上限")
        snapshot.append({
            'source_key': x['source_key'],
            'angle': x['angle'],
            'rows': x['rows'],
            'cols': x['cols'],
            'grids': x['grids'],
        })
    if len(snapshot) > MAX_SHEETS:
        raise HTTPException(422, f'容量超出 {MAX_SHEETS} 张纸，拒绝排队')
    return snapshot


def create(db, data, user):
    studies.require(db, data.study_id)
    rows = studies.observations(db, data.study_id)
    if not rows:
        raise HTTPException(422, '先补传至少一张纸样的双工艺格图')
    try:
        params = validate_parameters(data.parameters)
        validate_alignability(rows)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    snapshot = _freeze(rows)
    run = Run(
        study_id=data.study_id, name=data.name, parameters=params,
        snapshot=snapshot, checksum=checksum(snapshot),
        created_at=now(), status='queued')
    db.add(run)
    db.flush()
    log(db, user, 'run.queue', f'{run.id} 门槛{params["threshold"]} 张数{len(snapshot)}')
    db.commit()
    Redis.from_url(os.environ['REDIS_URL']).rpush('analysis-queue', run.id)
    return record(run)


def get(db, id):
    run = db.get(Run, id)
    if not run:
        raise HTTPException(404, '运行不存在')
    result = record(run)
    review = db.scalar(select(Review).where(Review.run_id == id))
    result['review'] = record(review) if review else None
    return result


def list_runs(db):
    return [get(db, x) for x in db.scalars(select(Run.id).order_by(Run.id.desc()))]


def approve(db, id, data, user):
    run = db.get(Run, id)
    if not run:
        raise HTTPException(404, '运行不存在')
    if run.status != 'completed':
        raise HTTPException(409, '只能复核已完成运行')
    if db.scalar(select(Review).where(Review.run_id == id)):
        raise HTTPException(409, '已复核，记录不可覆盖')
    obj = Review(run_id=id, note=data.note, author=user.email, created_at=now())
    db.add(obj)
    log(db, user, 'review.approve', f'{id}: {data.note}')
    db.commit()
    return record(obj)


def export(db, id, user):
    r = get(db, id)
    if r['status'] != 'completed':
        raise HTTPException(409, '尚无完成结果')
    if user.role == 'viewer' and not r['review']:
        raise HTTPException(403, '观察员只能导出已复核结果')
    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow(['运行编号', '输入校验SHA256', '指标', '值'])
    for k, v in r['result']['metrics'].items():
        w.writerow([id, r['checksum'], k,
                    json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v])
    # 斑块与每格样本数一并导出
    res = r['result']
    w.writerow([id, r['checksum'], '解释', res['interpretation']])
    w.writerow([])
    w.writerow(['斑块编号', '面积(格)', '方向', '最大平均差', '格坐标(r,c)'])
    for p in res.get('patches', []):
        w.writerow([p['patch_id'], p['area'], p['direction'], p['mean_diff_max'],
                    ';'.join(f'{r},{c}' for r, c in p['cells'])])
    w.writerow([])
    g = res['grid']
    w.writerow(['行', '列', '平均配对差(B−A)', '成对样本数', '斑块编号'])
    for rr in range(g['rows']):
        for cc in range(g['cols']):
            w.writerow([rr, cc, g['mean_diff'][rr][cc], g['samples'][rr][cc],
                        g['patch_labels'][rr][cc]])
    log(db, user, 'run.export', id)
    db.commit()
    return '\ufeff' + stream.getvalue()
