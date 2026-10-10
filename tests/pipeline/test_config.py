import os

from pipeline.config import load_env_local


def test_load_env_local(tmp_path, monkeypatch):
    env_file = tmp_path / "env.local"
    env_file.write_text("OPENAI_API_KEY=test-key\nOTHER=value\n", encoding="utf-8")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)

    load_env_local(env_file)

    assert os.environ["OPENAI_API_KEY"] == "test-key"
    assert os.environ["OTHER"] == "value"
