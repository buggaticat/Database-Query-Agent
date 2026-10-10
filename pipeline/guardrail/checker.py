from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from enum import Enum
import re
import sqlite3
from typing import Iterable

from .judge import GuardrailDecision, GuardrailJudgeClient, GuardrailJudgment


class GuardrailStatus(str, Enum):
    ALLOW = "allow"
    CLARIFY = "clarify"
    BLOCK = "block"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class GuardrailResult:
    status: GuardrailStatus
    decision: GuardrailDecision
    confidence: float
    reason: str
    matched_rule: str
    normalized_prompt: str | None = None
    judge_reason: str | None = None
    judge_categories: tuple[str, ...] = ()


SQL_PATTERNS = (
    re.compile(r"\b(select|insert|update|delete|drop|alter|create|truncate|replace)\b", re.IGNORECASE),
    re.compile(r";\s*(select|insert|update|delete|drop|alter|create|truncate|replace)\b", re.IGNORECASE),
    re.compile(r"--|/\*|\*/"),
)

INJECTION_PATTERNS = (
    re.compile(r"\bignore (all )?(previous|prior) instructions\b", re.IGNORECASE),
    re.compile(r"\bdisregard (all )?(previous|prior) instructions\b", re.IGNORECASE),
    re.compile(r"\boverride (all )?safety\b", re.IGNORECASE),
    re.compile(r"\b(system prompt|developer message|hidden prompt|tool schema)\b", re.IGNORECASE),
)

MODIFICATION_PATTERNS = (
    re.compile(r"\b(modify|delete|remove|drop|insert|update|truncate|alter)\b", re.IGNORECASE),
    re.compile(r"\b(write|change|edit)\b.*\b(database|records?|rows?)\b", re.IGNORECASE),
)

OUT_OF_SCOPE_PATTERNS = (
    re.compile(r"\b(weather|news|stock|stocks|email|emails|browser|file|files|file system|filesystem)\b", re.IGNORECASE),
    re.compile(r"\b(person|face|license plate|identity|private person)\b", re.IGNORECASE),
)

UNSUPPORTED_PATTERNS = (
    re.compile(r"\b(after|before)\s+(?:20(?:2[6-9]|[3-9]\d)|2[1-9]\d{2})\b", re.IGNORECASE),
    re.compile(r"\b(last century|next year|two years ago from 2026)\b", re.IGNORECASE),
)

YEAR_ONLY_PATTERN = re.compile(r"\b(20\d{2})\b")
YEAR_CONTEXT_PATTERN = re.compile(r"\b(?:for|in|during|on|of)\s+(20\d{2})\b", re.IGNORECASE)

DB_DEFAULT_PATH = Path("data") / "cctv_frames.db"


@dataclass(frozen=True)
class DatabaseBounds:
    start: datetime
    end: datetime


def _load_database_bounds(db_path: str | Path = DB_DEFAULT_PATH) -> DatabaseBounds:
    """Read the minimum and maximum datetimes available in the database."""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT MIN(datetime), MAX(datetime) FROM frames").fetchone()
        if row is None or row[0] is None or row[1] is None:
            raise RuntimeError("Unable to determine database date bounds.")
        return DatabaseBounds(
            start=datetime.fromisoformat(row[0]),
            end=datetime.fromisoformat(row[1]),
        )
    finally:
        conn.close()


def _year_window(year: int) -> DatabaseBounds:
    """Build the full datetime window for a calendar year."""
    return DatabaseBounds(
        start=datetime(year, 1, 1, 0, 0, 0),
        end=datetime(year, 12, 31, 23, 59, 59),
    )


def _intersects(left: DatabaseBounds, right: DatabaseBounds) -> bool:
    """Return whether two datetime windows overlap."""
    return left.start <= right.end and right.start <= left.end


def _clamp_to_bounds(requested: DatabaseBounds, available: DatabaseBounds) -> DatabaseBounds:
    """Clamp a requested window to the available database range."""
    return DatabaseBounds(
        start=max(requested.start, available.start),
        end=min(requested.end, available.end),
    )


def _format_clamped_prompt(prompt: str, year: int, clamped: DatabaseBounds) -> str:
    """Attach the available database range to a normalized prompt."""
    return (
        f"{prompt.strip()}\n"
        f"Available database range for {year}: "
        f"{clamped.start.date().isoformat()} to {clamped.end.date().isoformat()}."
    )


def _extract_year(prompt: str) -> int | None:
    """Extract a year from the prompt when the request is year-scoped."""
    match = YEAR_CONTEXT_PATTERN.search(prompt)
    if match:
        return int(match.group(1))
    match = YEAR_ONLY_PATTERN.search(prompt)
    if match:
        return int(match.group(1))
    return None


def _first_match(patterns: Iterable[re.Pattern[str]], text: str) -> str | None:
    """Return the first regex pattern string that matches the input text."""
    for pattern in patterns:
        if pattern.search(text):
            return pattern.pattern
    return None


def _build_result(
    *,
    status: GuardrailStatus,
    reason: str,
    matched_rule: str,
    normalized_prompt: str | None = None,
    decision: GuardrailDecision | None = None,
    confidence: float = 1.0,
    judge_reason: str | None = None,
    judge_categories: tuple[str, ...] = (),
) -> GuardrailResult:
    if decision is None:
        decision = GuardrailDecision.ALLOW if status == GuardrailStatus.ALLOW else GuardrailDecision.DISALLOW
    return GuardrailResult(
        status=status,
        decision=decision,
        confidence=confidence,
        reason=reason,
        matched_rule=matched_rule,
        normalized_prompt=normalized_prompt,
        judge_reason=judge_reason,
        judge_categories=judge_categories,
    )


def _status_from_judgment(judgment: GuardrailJudgment) -> GuardrailStatus:
    categories = {category.lower() for category in judgment.categories}
    if "clarification" in categories or "ambiguous" in categories or "needs_clarification" in categories:
        return GuardrailStatus.CLARIFY
    if categories & {"unsupported", "out_of_scope", "unrelated"}:
        return GuardrailStatus.UNSUPPORTED
    return GuardrailStatus.BLOCK


def _run_judge(
    deterministic: GuardrailResult,
    prompt: str,
    *,
    judge_client: GuardrailJudgeClient | None,
) -> GuardrailResult:
    if judge_client is None or deterministic.status != GuardrailStatus.ALLOW:
        return deterministic

    normalized_prompt = deterministic.normalized_prompt or " ".join(prompt.strip().split())
    judgment = judge_client.judge(
        prompt=prompt,
        deterministic_reason=deterministic.reason,
        deterministic_rule=deterministic.matched_rule,
        normalized_prompt=normalized_prompt,
    )
    if judgment.decision == GuardrailDecision.ALLOW:
        return GuardrailResult(
            status=GuardrailStatus.ALLOW,
            decision=GuardrailDecision.ALLOW,
            confidence=judgment.confidence,
            reason=judgment.reason,
            matched_rule=deterministic.matched_rule,
            normalized_prompt=normalized_prompt,
            judge_reason=judgment.reason,
            judge_categories=tuple(judgment.categories),
        )

    status = _status_from_judgment(judgment)
    return GuardrailResult(
        status=status,
        decision=GuardrailDecision.DISALLOW,
        confidence=judgment.confidence,
        reason=judgment.reason,
        matched_rule=f"llm_{status.value}",
        normalized_prompt=normalized_prompt,
        judge_reason=judgment.reason,
        judge_categories=tuple(judgment.categories),
    )


def evaluate_prompt(
    prompt: str,
    db_path: str | Path = DB_DEFAULT_PATH,
    judge_client: GuardrailJudgeClient | None = None,
) -> GuardrailResult:
    """Classify a prompt as allowed, blocked, unsupported, or needing clarification."""
    normalized = " ".join(prompt.strip().split())
    lower = normalized.lower()

    sql_match = _first_match(SQL_PATTERNS, normalized)
    if sql_match:
        return _build_result(
            status=GuardrailStatus.BLOCK,
            reason="Request appears to contain direct SQL or SQL-injection style syntax.",
            matched_rule=sql_match,
        )

    injection_match = _first_match(INJECTION_PATTERNS, normalized)
    if injection_match:
        return _build_result(
            status=GuardrailStatus.BLOCK,
            reason="Request attempts prompt injection or instruction override.",
            matched_rule=injection_match,
        )

    modification_match = _first_match(MODIFICATION_PATTERNS, normalized)
    if modification_match and ("database" in lower or "records" in lower or "rows" in lower):
        return _build_result(
            status=GuardrailStatus.BLOCK,
            reason="Request attempts to modify or delete database data.",
            matched_rule=modification_match,
        )

    unsupported_match = _first_match(UNSUPPORTED_PATTERNS, normalized)
    if unsupported_match:
        return _build_result(
            status=GuardrailStatus.UNSUPPORTED,
            reason="Request asks for unsupported date or time scope.",
            matched_rule=unsupported_match,
        )

    requested_year = _extract_year(normalized)
    if requested_year is not None:
        available = _load_database_bounds(db_path)
        requested = _year_window(requested_year)
        if not _intersects(requested, available):
            return _build_result(
                status=GuardrailStatus.CLARIFY,
                reason="Requested year is outside the available database range. Please reprompt with a supported time window.",
                matched_rule=f"year_{requested_year}_outside_db_range",
            )
        clamped = _clamp_to_bounds(requested, available)
        if clamped.start == requested.start and clamped.end == requested.end:
            deterministic = _build_result(
                status=GuardrailStatus.ALLOW,
                reason="Requested year is fully available in the database.",
                matched_rule=f"year_{requested_year}_fully_available",
                normalized_prompt=normalized,
                confidence=0.99,
            )
            return _run_judge(deterministic, prompt, judge_client=judge_client)
        deterministic = _build_result(
            status=GuardrailStatus.ALLOW,
            reason="Requested year partially overlaps the database; clamping to available records.",
            matched_rule=f"year_{requested_year}_partially_available",
            normalized_prompt=_format_clamped_prompt(normalized, requested_year, clamped),
            confidence=0.99,
        )
        return _run_judge(deterministic, prompt, judge_client=judge_client)

    out_of_scope_match = _first_match(OUT_OF_SCOPE_PATTERNS, normalized)
    if out_of_scope_match:
        return _build_result(
            status=GuardrailStatus.UNSUPPORTED,
            reason="Request appears outside the CCTV database querying domain.",
            matched_rule=out_of_scope_match,
        )

    if any(token in lower for token in ("who is", "what is your name", "how are you", "tell me about yourself")):
        return _build_result(
            status=GuardrailStatus.UNSUPPORTED,
            reason="Request is unrelated to CCTV database queries.",
            matched_rule="conversation_out_of_scope",
        )

    if not normalized:
        return _build_result(
            status=GuardrailStatus.CLARIFY,
            reason="Empty prompt; ask the user for a database query.",
            matched_rule="empty_prompt",
        )

    deterministic = _build_result(
        status=GuardrailStatus.ALLOW,
        reason="Prompt is within the supported CCTV query scope.",
        matched_rule="default_allow",
        normalized_prompt=normalized,
        confidence=0.95,
    )
    return _run_judge(deterministic, prompt, judge_client=judge_client)
