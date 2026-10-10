from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from pipeline.config import load_env_local
from pipeline.guardrail import GuardrailJudgeClient, GuardrailStatus, evaluate_prompt
from pipeline.parse.client import PromptParserClient
from pipeline.parse.schema import ParseResult, ParseStatus, ParsedPrompt
from pipeline.sql.client import SQLPlannerClient
from pipeline.sql.executor import ResultWriter, execute_query_plan
from pipeline.sql.schema import QueryResult


class OrchestratorState(TypedDict, total=False):
    thread_id: str
    user_prompt: str
    guarded_prompt: str
    guardrail_status: str
    guardrail_decision: str
    guardrail_confidence: float
    parse_result: dict[str, Any]
    sql_result: dict[str, Any]
    conversation_context: dict[str, Any]
    response: str


@dataclass
class OrchestratorDependencies:
    parser: PromptParserClient = field(default_factory=lambda: _build_parser_client())
    sql_planner: SQLPlannerClient = field(default_factory=lambda: _build_sql_planner_client())
    writer: ResultWriter = field(default_factory=ResultWriter)
    guardrail_judge: GuardrailJudgeClient = field(default_factory=lambda: _build_guardrail_judge_client())


ProgressCallback = Callable[[str], None]


def _build_parser_client() -> PromptParserClient:
    """Create a prompt parser client after loading local environment settings."""
    load_env_local()
    return PromptParserClient()


def _build_sql_planner_client() -> SQLPlannerClient:
    """Create an SQL planner client after loading local environment settings."""
    load_env_local()
    return SQLPlannerClient()


def _build_guardrail_judge_client() -> GuardrailJudgeClient:
    """Create the guardrail judge client after loading local environment settings."""
    load_env_local()
    return GuardrailJudgeClient()


class Orchestrator:
    """Coordinate guardrail checks, parsing, planning, and result writing."""

    def __init__(
        self,
        dependencies: OrchestratorDependencies | None = None,
    ) -> None:
        """Initialize the orchestrator and compile the execution graph."""
        load_env_local()
        self.dependencies = dependencies or OrchestratorDependencies()
        self._checkpointer = MemorySaver()
        self._progress: ProgressCallback | None = None
        self._graph = self._build_graph().compile(checkpointer=self._checkpointer)

    def _build_graph(self):
        """Build the state graph that drives request processing."""
        graph = StateGraph(OrchestratorState)
        graph.add_node("guardrail", self._guardrail_node)
        graph.add_node("parse", self._parse_node)
        graph.add_node("sql", self._sql_node)
        graph.set_entry_point("guardrail")
        graph.add_conditional_edges("guardrail", self._route_after_guardrail, {"parse": "parse", END: END})
        graph.add_conditional_edges("parse", self._route_after_parse, {"sql": "sql", END: END})
        graph.add_edge("sql", END)
        return graph

    def run(self, prompt: str, thread_id: str | None = None) -> OrchestratorState:
        """Run the orchestrator without emitting progress events."""
        return self.run_with_progress(prompt, thread_id=thread_id)

    def run_with_progress(
        self,
        prompt: str,
        thread_id: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> OrchestratorState:
        """Run the orchestrator and optionally report stage progress."""
        thread_id = thread_id or "thread-" + uuid4().hex
        self._progress = progress
        state = {
            "thread_id": thread_id,
            "user_prompt": prompt,
            "conversation_context": self._load_context(thread_id),
        }
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = self._graph.invoke(state, config=config)
        finally:
            self._progress = None
        return result

    def _load_context(self, thread_id: str) -> dict[str, Any]:
        """Load the conversation context stored for a thread."""
        snapshot = self._checkpointer.get({"configurable": {"thread_id": thread_id}})
        if not snapshot:
            return {}
        values = snapshot.get("channel_values") or {}
        return values.get("conversation_context", {})

    def _guardrail_node(self, state: OrchestratorState) -> OrchestratorState:
        """Apply prompt guardrails before any parsing or SQL work."""
        if self._progress:
            self._progress("Running prompt against guardrail...")
        result = evaluate_prompt(state["user_prompt"], judge_client=self.dependencies.guardrail_judge)
        updated = dict(state)
        updated["guardrail_status"] = result.status.value
        updated["guardrail_decision"] = result.decision.value
        updated["guardrail_confidence"] = result.confidence
        updated["guarded_prompt"] = result.normalized_prompt or state["user_prompt"]
        if result.status == GuardrailStatus.ALLOW:
            return updated
        updated["response"] = f"{result.decision.value} ({result.confidence:.2f}): {result.reason}"
        return updated

    def _route_after_guardrail(self, state: OrchestratorState) -> str:
        """Route to parsing only when the prompt is allowed."""
        status = state.get("guardrail_status")
        return "parse" if status == GuardrailStatus.ALLOW.value else END

    def _parse_node(self, state: OrchestratorState) -> OrchestratorState:
        """Parse the prompt into structured query filters and context."""
        if self._progress:
            self._progress("Parsing prompt into structured query filters...")
        prompt = state.get("guarded_prompt", state["user_prompt"])
        merged_prompt = self._merge_with_context(prompt, state.get("conversation_context", {}))
        parse_result = self.dependencies.parser.parse(merged_prompt)
        updated = dict(state)
        updated["parse_result"] = parse_result.model_dump()
        updated["conversation_context"] = self._update_context(state.get("conversation_context", {}), parse_result)
        if self._progress and parse_result.status == ParseStatus.OK and parse_result.parsed is not None:
            cameras = ", ".join(parse_result.parsed.camera_names) if parse_result.parsed.camera_names else "no camera filters"
            time_filters = (
                ", ".join(
                    [f.label for f in parse_result.parsed.datetime_filters]
                    + [f.label for f in parse_result.parsed.date_ranges]
                    + [f.label for f in parse_result.parsed.recurrence_filters]
                )
                if (
                    parse_result.parsed.datetime_filters
                    or parse_result.parsed.date_ranges
                    or parse_result.parsed.recurrence_filters
                )
                else "no time filters"
            )
            self._progress(f"Parsed prompt into cameras: {cameras}; time constraints: {time_filters}.")
        if parse_result.status == ParseStatus.OK and parse_result.parsed is not None:
            updated["guarded_prompt"] = merged_prompt
            updated["response"] = "Parsed successfully."
        elif parse_result.status == ParseStatus.NEEDS_CLARIFICATION:
            updated["response"] = parse_result.clarification_question or "Please clarify your request."
        else:
            updated["response"] = parse_result.unsupported_reason or "Unsupported request."
        return updated

    def _route_after_parse(self, state: OrchestratorState) -> str:
        """Route to SQL planning only when parsing succeeds."""
        parse_result = ParseResult.model_validate(state["parse_result"])
        return "sql" if parse_result.status == ParseStatus.OK else END

    def _sql_node(self, state: OrchestratorState) -> OrchestratorState:
        """Turn a parsed prompt into SQL and write the resulting rows."""
        if self._progress:
            self._progress("Feeding parsed information into SQL planner...")
        parse_result = ParseResult.model_validate(state["parse_result"])
        query_plan = self.dependencies.sql_planner.plan(parse_result)
        if self._progress:
            self._progress("Extracting SQL records from the database...")
        sql_result = execute_query_plan(query_plan, writer=self.dependencies.writer)
        updated = dict(state)
        updated["sql_result"] = sql_result.model_dump()
        updated["response"] = sql_result.result_file
        if self._progress:
            self._progress(f"Results extracted at {sql_result.result_file}")
        return updated

    def _merge_with_context(self, prompt: str, context: dict[str, Any]) -> str:
        """Prepend prior conversation constraints to the current prompt."""
        parts = []
        if context.get("camera_names"):
            parts.append("Previous cameras: " + ", ".join(context["camera_names"]))
        if context.get("datetime_filters"):
            parts.append("Previous time filters: " + ", ".join(context["datetime_filters"]))
        if context.get("date_ranges"):
            parts.append("Previous date ranges: " + ", ".join(context["date_ranges"]))
        if context.get("recurrence_filters"):
            parts.append("Previous recurrences: " + ", ".join(context["recurrence_filters"]))
        parts.append("Current request: " + prompt)
        return "\n".join(parts)

    def _update_context(self, context: dict[str, Any], parse_result: ParseResult) -> dict[str, Any]:
        """Merge parsed filters into the stored conversation context."""
        if parse_result.parsed is None:
            return context
        updated = dict(context)
        updated["camera_names"] = parse_result.parsed.camera_names or updated.get("camera_names", [])
        updated["datetime_filters"] = [f.label for f in parse_result.parsed.datetime_filters] or updated.get("datetime_filters", [])
        updated["date_ranges"] = [f.label for f in parse_result.parsed.date_ranges] or updated.get("date_ranges", [])
        updated["recurrence_filters"] = [f.label for f in parse_result.parsed.recurrence_filters] or updated.get("recurrence_filters", [])
        return updated
