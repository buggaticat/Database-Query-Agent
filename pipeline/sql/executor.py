from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import re
from typing import Iterable

from pipeline.models import CCTVFrameRecord, CameraName, FrameDatetime, FrameID

from .schema import QueryPlan, QueryPlanStatus, QueryResult


READ_ONLY_SQL_FORBIDDEN_PATTERNS = (
    re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|detach|pragma|vacuum|reindex|begin|commit|rollback)\b", re.IGNORECASE),
    re.compile(r"--|/\*|\*/"),
)


class ResultWriter:
    """Persist query results as JSON files on disk."""

    def __init__(self, directory: str | Path = "results") -> None:
        """Create a writer that stores result files in the target directory."""
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def next_path(self) -> Path:
        """Return the next unused result file path."""
        index = 0
        while True:
            candidate = self.directory / f"result_{index}.json"
            if not candidate.exists():
                return candidate
            index += 1

    def write(self, rows: Iterable[CCTVFrameRecord], sql: str) -> QueryResult:
        """Write rows and the rendered SQL to a JSON result file."""
        path = self.next_path()
        payload = {
            "sql": sql,
            "row_count": 0,
            "results": [],
        }
        results = []
        for row in rows:
            results.append(
                {
                    "frame_id": int(row.frame_id),
                    "datetime": row.datetime.isoformat(timespec="seconds"),
                    "camera_name": row.camera_name.value,
                }
            )
        payload["row_count"] = len(results)
        payload["results"] = results
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return QueryResult(result_file=str(path), row_count=len(results), sql=sql)


def _render_sql(sql: str, parameters: list[str]) -> str:
    """Render SQL by replacing positional parameters with quoted values."""
    rendered = sql
    for parameter in parameters:
        rendered = rendered.replace("?", _quote_sql_parameter(parameter), 1)
    return rendered


def _quote_sql_parameter(parameter: str) -> str:
    """Quote a SQL parameter for display in the saved output."""
    escaped = parameter.replace("'", "''")
    return f"'{escaped}'"


def _validate_read_only_sql(sql: str) -> str:
    """Ensure the SQL is a single read-only query."""
    normalized = " ".join(sql.strip().split())
    if not normalized:
        raise ValueError("Query plan SQL is empty.")
    if ";" in normalized:
        raise ValueError("Query plan SQL must be a single statement without semicolons.")
    if not (normalized.lower().startswith("select ") or normalized.lower().startswith("with ")):
        raise ValueError("Query plan SQL must start with SELECT or WITH.")
    for pattern in READ_ONLY_SQL_FORBIDDEN_PATTERNS:
        if pattern.search(normalized):
            raise ValueError("Query plan SQL contains forbidden mutating or administrative syntax.")
    return normalized


def execute_query_plan(
    plan: QueryPlan,
    db_path: str | Path = Path("data") / "cctv_frames.db",
    writer: ResultWriter | None = None,
) -> QueryResult:
    """Execute a validated query plan and persist the resulting frames."""
    if plan.status != QueryPlanStatus.OK or not plan.sql:
        raise ValueError("Query plan must be successful and include SQL.")

    sql = _validate_read_only_sql(plan.sql)
    db_uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        rows = []
        for row in conn.execute(sql, plan.parameters):
            rows.append(
                CCTVFrameRecord(
                    frame_id=FrameID(row["frame_id"]),
                    datetime=FrameDatetime(__import__("datetime").datetime.fromisoformat(row["datetime"])),
                    camera_name=CameraName(row["camera_name"]),
                )
            )
        writer = writer or ResultWriter()
        return writer.write(rows, _render_sql(sql, plan.parameters))
    finally:
        conn.close()
