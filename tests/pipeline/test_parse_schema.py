from datetime import datetime

from pipeline.models import CameraName
from pipeline.parse.schema import (
    DateRangeFilter,
    DatetimeFilter,
    ParseConfidence,
    ParseResult,
    ParseStatus,
    ParsedPrompt,
    RecurrenceFilter,
)


def test_parse_schema_supports_multiple_filters():
    parsed = ParsedPrompt(
        original_prompt="Show me CTE and PIE yesterday and every Tuesday.",
        camera_names=[CameraName.CTE, CameraName.PIE],
        datetime_filters=[
            DatetimeFilter(
                start=datetime(2026, 10, 8, 0, 0, 0),
                end=datetime(2026, 10, 8, 23, 59, 59),
                label="yesterday",
            )
        ],
        date_ranges=[
            DateRangeFilter(
                start=datetime(2026, 8, 1, 0, 0, 0),
                end=datetime(2026, 8, 31, 23, 59, 59),
                label="August 2026",
            )
        ],
        recurrence_filters=[RecurrenceFilter(weekday=1, label="every Tuesday")],
    )

    result = ParseResult(status=ParseStatus.OK, confidence=ParseConfidence.HIGH, parsed=parsed)
    assert result.parsed is not None
    assert len(result.parsed.camera_names) == 2
    assert result.parsed.camera_names[0] == CameraName.CTE
    assert len(result.parsed.datetime_filters) == 1
    assert len(result.parsed.date_ranges) == 1
    assert len(result.parsed.recurrence_filters) == 1
