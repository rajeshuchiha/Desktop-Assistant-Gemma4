from types import SimpleNamespace

import pytest
from typing import cast

from src.core.benchmark_logger import BenchmarkLogger
from src.core.orchestrator import Orchestrator, parse_tool_call


def test_parse_tool_call_raw_json():
    result = parse_tool_call('{"tool": "get_open_tabs", "params": {"limit": 3}}')

    assert result is not None
    assert result.tool == "get_open_tabs"
    assert result.params == {"limit": 3}


def test_parse_tool_call_markdown_wrapped_json():
    result = parse_tool_call(
        """```json
        {"tool": "read_file", "params": {"path": "settings.json"}}
        ```"""
    )

    assert result is not None
    assert result.tool == "read_file"
    assert result.params == {"path": "settings.json"}


def test_parse_tool_call_invalid_text():
    assert parse_tool_call("open the browser please") is None


def test_parse_tool_call_empty_string():
    assert parse_tool_call("") is None


def test_orchestrator_loads_llama_with_env_settings(monkeypatch):
    captured = {}

    class FakeLlama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.core.orchestrator.Llama", FakeLlama)
    monkeypatch.setenv("MODEL_PATH", "C:/models/gemma.gguf")
    monkeypatch.setenv("N_CTX", "4096")

    Orchestrator()

    assert captured == {
        "model_path": "C:/models/gemma.gguf",
        "n_ctx": 4096,
        "n_gpu_layers": -1,
        "chat_format": "gemma",
    }


@pytest.mark.asyncio
async def test_generate_records_ttft_and_token_throughput(monkeypatch):
    class FakeLogger(BenchmarkLogger):
        def __init__(self):
            super().__init__(output_dir="benchmarks")
            self.ttft = None
            self.throughput = None

        def record_ttft(self, seconds: float) -> None:
            self.ttft = seconds

        def record_token_throughput(self, tokens_per_sec: float) -> None:
            self.throughput = tokens_per_sec

    class FakeLlama:
        last_run_metadata = {"tokens_per_second": 42.0}

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_chat_completion(self, messages, stream):
            assert stream is True
            assert messages == [{"role": "user", "content": "hello"}]
            return iter(
                [
                    {"choices": [{"delta": {"content": "hi"}}]},
                    {"choices": [{"delta": {"content": " there"}}]},
                ]
            )

    monkeypatch.setattr("src.core.orchestrator.Llama", FakeLlama)
    logger = FakeLogger()
    orchestrator = Orchestrator(model_path="model.gguf", n_ctx=1024, benchmark_logger=logger)

    result = await orchestrator.generate("hello")

    assert result == "hi there"
    assert logger.ttft is not None
    assert logger.throughput == 42.0


def test_reset_context_calls_llm_reset(monkeypatch):
    class FakeLlama:
        def __init__(self, **kwargs):
            self.reset_called = False

        def reset(self):
            self.reset_called = True

    monkeypatch.setattr("src.core.orchestrator.Llama", FakeLlama)
    orchestrator = Orchestrator(model_path="model.gguf", n_ctx=1024)

    orchestrator.reset_context()

    fake_llm = cast(FakeLlama, orchestrator.llm)

    assert fake_llm.reset_called
