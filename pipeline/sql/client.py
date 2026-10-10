from __future__ import annotations

from openai import OpenAI

from pipeline.config import load_env_local
from pipeline.parse.schema import ParseResult, ParseStatus

from .schema import QueryPlan


class SQLPlannerClient:
    """Convert structured filters into a read-only SQLite query plan."""

    def __init__(self, client: OpenAI | None = None, model: str = "gpt-5.4-mini") -> None:
        """Create an SQL planner client that uses the configured OpenAI model."""
        load_env_local()
        self._client = client or OpenAI()
        self._model = model

    @property
    def model(self) -> str:
        """Return the model name used by this planner."""
        return self._model

    def plan(self, parsed: ParseResult) -> QueryPlan:
        """Plan a safe SQL query from a parsed prompt."""
        if parsed.status != ParseStatus.OK or parsed.parsed is None:
            raise ValueError("Parsed prompt must be successful before SQL planning.")

        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You translate structured CCTV query filters into a read-only SQLite query plan. "
                        "Only target the frames table with columns frame_id, datetime, and camera_name. "
                        "Only generate a single SELECT statement or a WITH clause that ends in SELECT. "
                        "Do not generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, ATTACH, DETACH, PRAGMA, VACUUM, REINDEX, BEGIN, COMMIT, or ROLLBACK. "
                        "Return only a structured query plan."
                    ),
                },
                {"role": "user", "content": parsed.model_dump_json()},
            ],
            text_format=QueryPlan,
        )
        plan = response.output_parsed
        if plan is None:
            raise RuntimeError("The SQL planner returned no structured output.")
        return plan
