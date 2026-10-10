from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from pipeline.models import CameraName


class ParseStatus(str, Enum):
    OK = "ok"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class ParseConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DatetimeFilter(BaseModel):
    kind: Literal["datetime"] = "datetime"
    start: datetime
    end: datetime
    label: str = Field(..., description="User-facing description of the resolved time window.")


class DateRangeFilter(BaseModel):
    kind: Literal["date_range"] = "date_range"
    start: datetime
    end: datetime
    label: str = Field(..., description="User-facing description of the resolved date window.")


class RecurrenceFilter(BaseModel):
    kind: Literal["recurrence"] = "recurrence"
    weekday: int = Field(..., ge=0, le=6, description="Monday=0 ... Sunday=6.")
    label: str = Field(..., description="User-facing description of the recurring window.")


class ParsedPrompt(BaseModel):
    camera_names: list[CameraName] = Field(default_factory=list)
    datetime_filters: list[DatetimeFilter] = Field(default_factory=list)
    date_ranges: list[DateRangeFilter] = Field(default_factory=list)
    recurrence_filters: list[RecurrenceFilter] = Field(default_factory=list)
    original_prompt: str
    clarified_prompt: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class ParseResult(BaseModel):
    status: ParseStatus
    confidence: ParseConfidence
    parsed: ParsedPrompt | None = None
    clarification_question: str | None = None
    unsupported_reason: str | None = None
