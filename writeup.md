# Natural Language to Database Query Agent Write-Up

## 1. Objective

This project implements a natural-language interface for querying CCTV frame records stored in SQLite. The agent accepts free-form user requests, resolves the request into structured filters, validates the request for safety and scope, and returns the matching frame records.

The intended query space is narrow and practical:

- camera lookups
- date and time reasoning
- date ranges and recurring days
- conversational follow-ups
- guardrails for unsafe or out-of-domain prompts

The design favors a small, readable pipeline over a fully autonomous agent loop.

## 2. Data Model

The database contains one row per CCTV frame with three fields:

- `frame_id`
- `datetime`
- `camera_name`

The supported camera names are the Singapore expressway cameras listed in `pipeline/models.py`. The bundled SQLite database in `data/cctv_frames.db` spans the 2026 frame range used by the assignment.

## 3. Pipeline Overview

The system is organized as a short, ordered pipeline:

1. **Guardrail check** decides whether the request is safe and in scope.
2. **Prompt parsing** converts the request into structured filters.
3. **SQL planning** turns the structured filters into a read-only query plan.
4. **Execution** runs the query and writes the result payload.
5. **Orchestration** ties the stages together and preserves relevant session context for follow-up turns.

Each stage has a single responsibility and is implemented in its own module:

- `pipeline/guardrail/checker.py`
- `pipeline/parse/client.py`
- `pipeline/parse/schema.py`
- `pipeline/sql/client.py`
- `pipeline/sql/schema.py`
- `pipeline/sql/executor.py`
- `pipeline/orchestrator.py`

## 4. Guardrail Stage

The guardrail uses a two-layer design.

The first layer is deterministic and rejects or short-circuits prompts that are not appropriate for the query pipeline, including:

- direct SQL attempts
- SQL injection-style input
- prompt injection and instruction override attempts
- requests to modify or delete database data
- unrelated or out-of-domain requests
- unsupported time scopes that should not be guessed

The second layer is an OpenAI-backed judge that runs only after the deterministic layer allows a prompt through. It re-evaluates relevance, unsupported scope, malicious or sensitive intent, prompt injection, SQL-like attempts, and database modification requests. The judge returns an `allow` or `disallow` decision together with a confidence score, which makes the guardrail output easier to inspect and reason about.

This stage still runs before parsing or SQL planning, so unsafe prompts do not reach the rest of the pipeline.

There is one special case for year-scoped prompts. If the request refers to a year that partially overlaps the available database range, the prompt is normalized to the supported window instead of failing immediately. That keeps the agent useful when the request is broadly valid but not perfectly bounded.

## 5. Parsing Stage

The parser in `pipeline/parse/client.py` uses OpenAI structured outputs to convert a natural-language request into a `ParseResult`.

The parser extracts:

- camera names
- datetime windows
- date ranges
- recurring weekday filters
- clarification questions when the request is ambiguous
- unsupported reasons when the request is outside scope

The schema in `pipeline/parse/schema.py` keeps the output explicit and machine-readable. That makes downstream handling predictable and reduces the chance of ad hoc string parsing later in the pipeline.

The parsing step handles the main language patterns required by the assignment:

- exact dates
- relative dates such as `today`, `yesterday`, `this week`, and `last month`
- date ranges such as `from the 15th to 18th of last month`
- time ranges such as `between 8 AM and 10 AM`
- recurring expressions such as `every Tuesday`
- combinations of camera and time constraints

## 6. SQL Planning Stage

The SQL planner in `pipeline/sql/client.py` transforms the parsed filters into a `QueryPlan`.

This stage is separate from parsing because the two tasks are different:

- parsing determines what the user means
- planning determines how to query the database safely

The planner is constrained to produce read-only SQLite queries over the `frames` table. That constraint keeps the model from wandering into unrelated SQL and makes the execution path easier to trust.

The schema in `pipeline/sql/schema.py` records:

- query status
- SQL text
- bound parameters
- output columns
- ordering
- predicate metadata

That structure makes it easier to validate and execute the plan without relying on free-form text.

## 7. Execution Stage

`pipeline/sql/executor.py` executes the validated query plan against SQLite and writes the results to JSON.

The executor is intentionally deterministic:

- it only runs plans marked successful
- it uses bound parameters
- it writes results in a stable file format
- it renders the SQL for inspection in the result file

This keeps the final step predictable and easy to debug.

## 8. Orchestration

The orchestrator in `pipeline/orchestrator.py` connects the stages using `langgraph`.

The graph is deliberately small:

- guardrail
- parse
- SQL
- end

The guardrail node now records both the final status and the judge-style decision/confidence pair. If the guardrail does not allow the request, orchestration stops immediately and returns the guardrail response instead of continuing to parsing.

`langgraph` is useful here because it gives an explicit state machine without introducing a larger custom framework.

The orchestrator keeps a small session-scoped context from the latest successful turn. If a follow-up omits a previously established camera or time filter, the missing constraint is inherited so prompts like "How about only those from this week?" preserve the earlier camera selection.

## 9. Ambiguity and Clarification

The system avoids guessing when the request is underspecified.

Ambiguity can be handled in two ways:

- the guardrail can stop clearly inappropriate input
- the parser can return a clarification question when the request cannot be resolved confidently

This is preferable to silently making the wrong query, especially for date expressions and vague follow-ups.

## 10. Camera Name Resolution

Camera-name variation is handled at the parsing stage.

The parser is instructed to support:

- full names such as `Central Expressway`
- acronyms such as `CTE`
- common variations such as `Kranji Highway`
- reasonable typos when the intent is still clear

This keeps the downstream SQL layer simple. Once the camera has been resolved into the canonical enum, query generation can stay strict and deterministic.

## 11. Query Validation

Validation happens at several points in the pipeline:

- the deterministic guardrail rejects unsafe or unrelated prompts first
- the LLM guardrail judge adds a second relevance and safety check
- the parser returns structured data instead of free text
- the SQL planner is restricted to read-only query generation
- the executor only runs successful plans

This layered approach is enough for the assignment while keeping the codebase compact.

I did not add a full SQL AST validator, multi-step self-correction, or a large tool orchestration layer. Those additions would increase complexity without clearly improving the required behavior.

## 12. Model Choices

The parser, SQL planner, and guardrail judge use OpenAI structured outputs with `gpt-5.4-mini`.

The model choice is practical for this task:

- strong enough for prompt interpretation and structured planning
- lightweight enough for a simple pipeline
- compatible with typed outputs
- avoids unnecessary model complexity

The guardrail judge is intentionally separate from the deterministic layer. That keeps the fast rule checks easy to reason about while still allowing a model-based relevance check when the prompt passes the first pass.

I split parsing and planning into separate model calls because the responsibilities are different and the failure modes are easier to reason about when they are isolated.

## 13. Reliability Trade-Offs

The main design principle is to keep the system reliable without turning it into a large agent framework.

What the implementation keeps:

- a short, explicit pipeline
- deterministic guardrails followed by a model-based judge
- typed intermediate objects
- bounded SQL execution
- session-scoped prompt handling with lightweight follow-up context

What it avoids:

- multi-agent coordination
- recursive tool use
- reflection or self-correction loops
- long, brittle system prompts

This makes the control flow easier to understand and lowers the chance of subtle failure modes.

## 14. Coverage of Expected Behavior

The implementation and tests cover the main query patterns expected by the assignment:

- camera-only queries
- date-only queries
- date and time windows
- date ranges
- recurring weekday queries
- combined camera and time queries
- conversational follow-ups with retained camera/time context

The tests also cover edge conditions such as:

- typos and camera-name variations
- ambiguous requests
- empty prompts
- unsupported questions
- prompt injection
- direct SQL attempts
- requests to modify data
- deterministic guardrail outcomes
- judge-driven allow/disallow decisions and confidence handling
- session-scoped request handling

## 15. Summary

The final system is a small, session-scoped query pipeline rather than a fully autonomous agent. That is intentional. The result is easier to inspect, easier to test, and more reliable for the constrained query domain of CCTV frame lookup while still supporting practical follow-up queries.
