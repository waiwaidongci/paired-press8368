from sqlalchemy import Column, Integer, String, JSON, ForeignKey, UniqueConstraint
from src.config.database import Base


class PressSheet(Base):
    __tablename__ = 'observations'
    __table_args__ = (UniqueConstraint('study_id', 'source_key'),)
    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, ForeignKey('studies.id'), nullable=False)
    # 纸样编号
    source_key = Column(String(100), nullable=False)
    # 定位角 0/90/180/270
    angle = Column(Integer, nullable=False, default=0)
    rows = Column(Integer, nullable=False)
    cols = Column(Integer, nullable=False)
    # {'a': [[...]], 'b': [[...]]}，None 表示该格缺测
    grids = Column(JSON, nullable=False)


# 兼容旧命名
Observation = PressSheet
MatchedPair = PressSheet
