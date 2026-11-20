import json
import numpy as np
from sqlalchemy import select, func
from src.config.database import Base, engine, Session
from src.config.domain import DOMAIN
from src.models.user import User
from src.models.study import Study
from src.models.observation import PressSheet
from src.models import run, review, audit  # noqa: F401  保证建表
from src.utils.security import hash_password

ROWS, COLS = 12, 12
# 容量上限 14；演示每研究放 6 张，保证每格有≥2张成对实测，且含若干缺测。
# 方阵格图支持 0/90/180/270 全部定位角的旋转对齐。
SHEETS_PER_STUDY = 6


# 入库扫描旋转（与算法的定位角还原互逆）：标准物理坐标 -> 存储坐标。
_STORE_TURNS = {0: 0, 90: 1, 180: 2, 270: 3}


def _make_grids(rng, k, angle):
    # 缺陷固定在标准物理坐标：基础色差场 + 同版成片套印偏差（同向越门槛）。
    base = rng.uniform(2.5, 5.0, size=(ROWS, COLS))
    blob = np.zeros((ROWS, COLS))
    blob[3:7, 4:9] = 2.6 + 0.4 * k          # 正向越门槛斑块（B 系统性偏高）
    blob[8:10, 2:4] = -2.4                  # 负向越门槛斑块
    turns = _STORE_TURNS[angle]
    grids = {}
    for proc in ('a', 'b'):
        g = base + (blob if proc == 'b' else 0.0) + rng.normal(0, 0.25, size=(ROWS, COLS))
        g = np.clip(g, 0.05, None)
        g = np.rot90(g, turns)              # 按扫描定位角旋转入库
        grid = np.round(g, 3).astype(object)
        # 缺测：约 4% 格置 None，缺测不补值；两侧各自独立缺一些
        miss = rng.random(size=(ROWS, COLS)) < 0.04
        grid[miss] = None
        grids[proc] = grid.tolist()
    return grids


def seed():
    Base.metadata.create_all(engine)
    rng = np.random.default_rng(42)
    with Session() as db:
        for role in ('admin', 'analyst', 'viewer'):
            email = role + '@demo.local'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, role=role, password_hash=hash_password('Research2026!')))
        for k, name in enumerate(DOMAIN['names']):
            study = db.scalar(select(Study).where(Study.name == name))
            if not study:
                study = Study(
                    name=name,
                    source_filename=DOMAIN['slug'] + f'-202611-{k + 1}.csv',
                    description='独立合成格图观测 / 固定种子42 / 双工艺双版对齐 / 仅用于方法与流程演示')
                db.add(study)
                db.flush()
            for n in range(SHEETS_PER_STUDY):
                key = f'SHEET-{k + 1}-{n + 1:03}'
                if db.scalar(select(PressSheet.id).where(
                        PressSheet.study_id == study.id, PressSheet.source_key == key)):
                    continue
                angle = (n % 4) * 90
                grids = _make_grids(rng, k, angle)
                db.add(PressSheet(
                    study_id=study.id, source_key=key,
                    angle=angle, rows=ROWS, cols=COLS, grids=grids))
        db.commit()
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in (User, Study, PressSheet)}
        print(json.dumps(counts, ensure_ascii=False))
        return counts


if __name__ == '__main__':
    seed()
