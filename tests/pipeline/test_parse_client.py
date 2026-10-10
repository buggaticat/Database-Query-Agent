from pipeline.parse.client import PromptParserClient
from pipeline.models import CameraName
from pipeline.parse.schema import ParseConfidence, ParseResult, ParseStatus, ParsedPrompt


class _FakeResponses:
    def __init__(self, parsed):
        self._parsed = parsed
        self.last_request = None

    def parse(self, **kwargs):
        self.last_request = kwargs

        class _Response:
            output_parsed = self._parsed

        return _Response()


class _FakeClient:
    def __init__(self, parsed):
        self.responses = _FakeResponses(parsed)


def test_prompt_parser_uses_gpt_54_mini():
    parsed = ParseResult(
        status=ParseStatus.OK,
        confidence=ParseConfidence.HIGH,
        parsed=ParsedPrompt(original_prompt="Show me CTE today", camera_names=[CameraName.CTE]),
    )
    fake_client = _FakeClient(parsed)
    parser = PromptParserClient(client=fake_client)  # type: ignore[arg-type]

    result = parser.parse("Show me CTE today")

    assert result == parsed
    assert fake_client.responses.last_request["model"] == "gpt-5.4-mini"
    assert fake_client.responses.last_request["text_format"] is ParseResult
