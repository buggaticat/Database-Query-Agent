from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class QueryPlanStatus(str, Enum):
    OK = "ok"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class QueryPredicate(BaseModel):
    field: Literal["camera_name", "datetime"]
    operator: Literal["eq", "in", "between", "on", "gte", "lte"]
    value: str | list[str] | datetime | list[datetime]


class QueryPlan(BaseModel):
    status: QueryPlanStatus
    sql: Optional[str] = None
    parameters: list[str] = Field(default_factory=list)
    output_columns: list[str] = Field(default_factory=lambda: ["frame_id", "datetime", "camera_name"])
    order_by: list[str] = Field(default_factory=lambda: ["datetime", "frame_id"])
    limit: Optional[int] = None
    predicates: list[QueryPredicate] = Field(default_factory=list)
    rationale: Optional[str] = None
    clarification_question: Optional[str] = None
    unsupported_reason: Optional[str] = None


class QueryResult(BaseModel):
    result_file: str
    row_count: int
    sql: str

