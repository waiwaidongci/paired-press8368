from typing import Optional
from pydantic import BaseModel, Field


class PressSheetInput(BaseModel):
    source_key: str = Field(min_length=1, max_length=100)
    angle: int = Field(default=0)
    grids: dict  # {'a': [[float|None]], 'b': [[...]]}，校验在服务层做


ObservationInput = PressSheetInput
MatchedPairInput = PressSheetInput
