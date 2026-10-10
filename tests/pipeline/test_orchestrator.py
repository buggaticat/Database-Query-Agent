from pipeline.orchestrator import Orchestrator, OrchestratorDependencies
from pipeline.models import CameraName
from pipeline.guardrail import GuardrailDecision, GuardrailJudgment
from pipeline.parse.schema import (
    DateRangeFilter,
    DatetimeFilter,
    ParseConfidence,
    ParseResult,
    ParseStatus,
    ParsedPrompt,
    RecurrenceFilter,
)
from pipeline.sql.schema import QueryPlan, QueryPlanStatus


class FakeParser:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def parse(self, prompt: str):
        self.calls.append(prompt)
        return self.results.pop(0)


class FakeSQLPlanner:
    def __init__(self):
        self.calls = []

    def plan(self, parsed):
        self.calls.append(parsed)
        return QueryPlan(
            status=QueryPlanStatus.OK,
            sql="SELECT frame_id, datetime, camera_name FROM frames LIMIT 1",
        )


class FakeWriter:
    def __init__(self):
        self.calls = []

    def write(self, rows, sql):
        self.calls.append((list(rows), sql))
        from pipeline.sql.schema import QueryResult

        return QueryResult(result_file="results/result_0.json", row_count=1, sql=sql)


class FakeGuardrailJudge:
    def __init__(self, judgment=None):
        self.judgment = judgment or GuardrailJudgment(
            decision=GuardrailDecision.ALLOW,
            confidence=0.99,
            reason="Prompt is within the supported CCTV query scope.",
            categories=["relevant"],
        )
        self.calls = []

    def judge(self, prompt: str, *, deterministic_reason: str, deterministic_rule: str, normalized_prompt: str):
        self.calls.append(
            {
                "prompt": prompt,
                "deterministic_reason": deterministic_reason,
                "deterministic_rule": deterministic_rule,
                "normalized_prompt": normalized_prompt,
            }
        )
        return self.judgment


def test_orchestrator_keeps_context_across_turns():
    first = ParseResult(
        status=ParseStatus.OK,
        confidence=ParseConfidence.HIGH,
        parsed=ParsedPrompt(
            original_prompt="Show me frames from CTE.",
            camera_names=[CameraName.CTE],
            datetime_filters=[],
            date_ranges=[],
        ),
    )
    second = ParseResult(
        status=ParseStatus.OK,
        confidence=ParseConfidence.HIGH,
        parsed=ParsedPrompt(
            original_prompt="How about only those from this week?",
            camera_names=[],
            datetime_filters=[],
            date_ranges=[
                DateRangeFilter(
                    start=__import__("datetime").datetime(2026, 10, 5, 0, 0, 0),
                    end=__import__("datetime").datetime(2026, 10, 11, 23, 59, 59),
                    label="this week",
                )
            ],
        ),
    )
    parser = FakeParser([first, second])
    planner = FakeSQLPlanner()
    writer = FakeWriter()
    judge = FakeGuardrailJudge()
    orchestrator = Orchestrator(OrchestratorDependencies(parser=parser, sql_planner=planner, writer=writer, guardrail_judge=judge))

    first_state = orchestrator.run("Show me frames from CTE.", thread_id="thread-1")
    second_state = orchestrator.run("How about only those from this week?", thread_id="thread-1")

    assert first_state["response"] == "results/result_0.json"
    assert second_state["response"] == "results/result_0.json"
    assert "Previous cameras: Central Expressway (CTE)" in parser.calls[1]
    assert "Current request: How about only those from this week?" in parser.calls[1]


def test_orchestrator_route_for_real_query_examples():
    prompts = [
        "Show me frames from CTE today.",
        "Show me frames from Tampines Expressway for the whole of August.",
        "Show me frames from MCE on every Tuesday.",
        "Show me frames from Kranji Highway from the 15th to 18th of last month.",
        "Show me PIE frames between 8 AM and 10 AM yesterday.",
    ]
    parsed_results = [
        ParseResult(
            status=ParseStatus.OK,
            confidence=ParseConfidence.HIGH,
            parsed=ParsedPrompt(
                original_prompt=prompts[0],
                camera_names=[CameraName.CTE],
                datetime_filters=[
                    DatetimeFilter(
                        start=__import__("datetime").datetime(2026, 10, 10, 0, 0, 0),
                        end=__import__("datetime").datetime(2026, 10, 10, 23, 59, 59),
                        label="today",
                    )
                ],
            ),
        ),
        ParseResult(
            status=ParseStatus.OK,
            confidence=ParseConfidence.HIGH,
            parsed=ParsedPrompt(
                original_prompt=prompts[1],
                camera_names=[CameraName.TPE],
                date_ranges=[
                    DateRangeFilter(
                        start=__import__("datetime").datetime(2026, 8, 1, 0, 0, 0),
                        end=__import__("datetime").datetime(2026, 8, 31, 23, 59, 59),
                        label="whole of August",
                    )
                ],
            ),
        ),
        ParseResult(
            status=ParseStatus.OK,
            confidence=ParseConfidence.HIGH,
            parsed=ParsedPrompt(
                original_prompt=prompts[2],
                camera_names=[CameraName.MCE],
                recurrence_filters=[RecurrenceFilter(weekday=1, label="every Tuesday")],
            ),
        ),
        ParseResult(
            status=ParseStatus.OK,
            confidence=ParseConfidence.HIGH,
            parsed=ParsedPrompt(
                original_prompt=prompts[3],
                camera_names=[CameraName.KJE],
                date_ranges=[
                    DateRangeFilter(
                        start=__import__("datetime").datetime(2026, 9, 15, 0, 0, 0),
                        end=__import__("datetime").datetime(2026, 9, 18, 23, 59, 59),
                        label="15th to 18th of last month",
                    )
                ],
            ),
        ),
        ParseResult(
            status=ParseStatus.OK,
            confidence=ParseConfidence.HIGH,
            parsed=ParsedPrompt(
                original_prompt=prompts[4],
                camera_names=[CameraName.PIE],
                datetime_filters=[
                    DatetimeFilter(
                        start=__import__("datetime").datetime(2026, 10, 9, 8, 0, 0),
                        end=__import__("datetime").datetime(2026, 10, 9, 10, 0, 0),
                        label="between 8 AM and 10 AM yesterday",
                    )
                ],
            ),
        ),
    ]
    parser = FakeParser(parsed_results)
    planner = FakeSQLPlanner()
    writer = FakeWriter()
    judge = FakeGuardrailJudge()
    orchestrator = Orchestrator(OrchestratorDependencies(parser=parser, sql_planner=planner, writer=writer, guardrail_judge=judge))

    for prompt in prompts:
        state = orchestrator.run(prompt)
        assert state["guardrail_status"] == "allow"
        assert state["response"] == "results/result_0.json"

    assert parser.calls[0] == "Current request: Show me frames from CTE today."
    assert parser.calls[1] == "Current request: Show me frames from Tampines Expressway for the whole of August."
    assert parser.calls[2] == "Current request: Show me frames from MCE on every Tuesday."
    assert parser.calls[3] == "Current request: Show me frames from Kranji Highway from the 15th to 18th of last month."
    assert parser.calls[4] == "Current request: Show me PIE frames between 8 AM and 10 AM yesterday."


def test_orchestrator_emits_progress_events_only_for_executed_stages():
    parsed = ParseResult(
        status=ParseStatus.OK,
        confidence=ParseConfidence.HIGH,
        parsed=ParsedPrompt(
            original_prompt="Show me frames from CTE today.",
            camera_names=[CameraName.CTE],
            datetime_filters=[],
            date_ranges=[],
        ),
    )
    parser = FakeParser([parsed])
    planner = FakeSQLPlanner()
    writer = FakeWriter()
    judge = FakeGuardrailJudge()
    orchestrator = Orchestrator(OrchestratorDependencies(parser=parser, sql_planner=planner, writer=writer, guardrail_judge=judge))

    events: list[str] = []
    state = orchestrator.run_with_progress(
        "Show me frames from CTE today.",
        thread_id="thread-progress",
        progress=events.append,
    )

    assert state["response"] == "results/result_0.json"
    assert events == [
        "Running prompt against guardrail...",
        "Parsing prompt into structured query filters...",
        "Parsed prompt into cameras: Central Expressway (CTE); time constraints: no time filters.",
        "Feeding parsed information into SQL planner...",
        "Extracting SQL records from the database...",
        "Results extracted at results/result_0.json",
    ]


def test_orchestrator_clamps_year_prompt_to_available_database_range():
    parsed = ParseResult(
        status=ParseStatus.OK,
        confidence=ParseConfidence.HIGH,
        parsed=ParsedPrompt(
            original_prompt="Give me query records for 2026.",
            camera_names=[],
            datetime_filters=[],
            date_ranges=[],
        ),
    )
    parser = FakeParser([parsed])
    planner = FakeSQLPlanner()
    writer = FakeWriter()
    judge = FakeGuardrailJudge()
    orchestrator = Orchestrator(OrchestratorDependencies(parser=parser, sql_planner=planner, writer=writer, guardrail_judge=judge))

    state = orchestrator.run("Give me query records for 2026.")

    assert state["guardrail_status"] == "allow"
    assert "Available database range for 2026: 2026-01-01 to 2026-10-09." in parser.calls[0]
