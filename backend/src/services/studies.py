from fastapi import HTTPException
from sqlalchemy import select, func
from src.models.study import Study
from src.models.observation import PressSheet
from src.services.grid_validation import validate_sheet, MAX_SHEETS
from src.services.audits import log
from src.utils.serializers import record


def list_studies(db):
    data = []
    for s in db.scalars(select(Study).order_by(Study.id)):
        x = record(s)
        x['row_count'] = db.scalar(
            select(func.count()).select_from(PressSheet).where(PressSheet.study_id == s.id))
        data.append(x)
    return data


def create(db, data, user):
    if db.scalar(select(Study).where(Study.name == data.name)):
        raise HTTPException(409, '批次名称已存在')
    s = Study(**data.model_dump())
    db.add(s)
    log(db, user, 'study.create', data.name)
    db.commit()
    return record(s)


def require(db, id):
    s = db.get(Study, id)
    if not s:
        raise HTTPException(404, '业务批次不存在')
    return s


def observations(db, id):
    require(db, id)
    return [record(x) for x in db.scalars(
        select(PressSheet).where(PressSheet.study_id == id).order_by(PressSheet.id))]


# 旧名兼容
list_rows = observations


def save_observation(db, id, data, user, row_id=None):
    require(db, id)
    try:
        norm = validate_sheet(data if isinstance(data, dict) else data.model_dump())
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))

    other = db.scalar(select(PressSheet).where(
        PressSheet.study_id == id, PressSheet.source_key == norm['source_key']))
    if other and other.id != row_id:
        raise HTTPException(409, '纸样编号重复')

    if row_id:
        row = db.get(PressSheet, row_id)
        if not row or row.study_id != id:
            raise HTTPException(404, '记录不存在')
        row.source_key = norm['source_key']
        row.angle = norm['angle']
        row.rows = norm['rows']
        row.cols = norm['cols']
        row.grids = norm['grids']
    else:
        count = db.scalar(select(func.count()).select_from(PressSheet)
                          .where(PressSheet.study_id == id))
        if count >= MAX_SHEETS:
            raise HTTPException(422, f'排队容量超出 {MAX_SHEETS} 张纸，拒绝录入')
        row = PressSheet(
            study_id=id, source_key=norm['source_key'], angle=norm['angle'],
            rows=norm['rows'], cols=norm['cols'], grids=norm['grids'])
        db.add(row)
    log(db, user, 'sheet.save', f"{id}/{norm['source_key']} 角度{norm['angle']}")
    db.commit()
    return record(row)


# 旧名兼容
save_row = save_observation
