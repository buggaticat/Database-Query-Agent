from __future__ import annotations

from openai import OpenAI

from pipeline.config import load_env_local

from .schema import ParseResult


class PromptParserClient:
    """Call the OpenAI parser to convert prompts into structured filters."""

    def __init__(self, client: OpenAI | None = None, model: str = "gpt-5.4-mini") -> None:
        """Create a parser client that uses the configured OpenAI model."""
        load_env_local()
        self._client = client or OpenAI()
        self._model = model

    @property
    def model(self) -> str:
        """Return the model name used by this parser."""
        return self._model

    def parse(self, prompt: str) -> ParseResult:
        """Parse a natural-language prompt into a structured query result."""
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You convert CCTV database user prompts into structured query filters. "
                        "Extract every camera name mentioned as one or more exact enum values from the supported camera list, "
                        "extract every datetime range mentioned, "
                        "and every recurring weekday constraint. "
                        "Support camera aliases like acronyms and common variations, plus simple typos when unambiguous. "
                        "Resolve relative time expressions such as today, yesterday, this week, last month, and calendar months. "
                        "If the prompt is ambiguous, ask one concise clarification question. "
                        "If the prompt is unsupported, explain why. "
                        "Return structured data only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text_format=ParseResult,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("The parser returned no structured output.")
        return parsed
