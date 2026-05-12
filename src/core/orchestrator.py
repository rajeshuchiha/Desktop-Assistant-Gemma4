"""
Spec:
- Load Gemma 4 E2B Q4_K_M via llama_cpp.Llama
- model_path and n_ctx from .env
- n_gpu_layers=-1, chat_format="gemma"
- async generate(prompt: str, image: PIL.Image | None = None) -> str
  if image: resize to 1280x720, pass as llava-style image embed
  record ttft via first-token stream callback to BenchmarkLogger
  record token_throughput from llm.last_run_metadata after completion
- parse_tool_call(text: str) -> ToolCall | None
  parse JSON {"tool": str, "params": dict} from LLM output
  handle both raw JSON and JSON inside markdown code blocks
  return None if no valid tool call found
- reset_context() -> None - flush KV cache
- Import ToolCall from src.core.types, BenchmarkLogger from
  src.core.benchmark_logger
Tests: mock the Llama class - test parse_tool_call with raw JSON,
       markdown-wrapped JSON, invalid text, empty string
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any, cast

from src.core.benchmark_logger import BenchmarkLogger
from src.core.types import ToolCall

from llama_cpp import Llama
from llama_cpp.llama_types import ChatCompletionRequestMessage, CreateChatCompletionStreamResponse


class Orchestrator:
    """Thin async wrapper around the local Gemma model."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        n_ctx: int | None = None,
        benchmark_logger: BenchmarkLogger | None = None,
    ):
        resolved_model_path = str(model_path or _env_value("MODEL_PATH", ""))
        if not resolved_model_path:
            raise ValueError("MODEL_PATH is required in the environment or .env")
        if Llama is None:
            raise RuntimeError("llama_cpp is not installed")

        self.benchmark_logger = benchmark_logger or BenchmarkLogger()
        self.llm = Llama(
            model_path=resolved_model_path,
            n_ctx=int(n_ctx or _env_value("N_CTX", "8192")),
            n_gpu_layers=-1,
            chat_format="gemma",
        )

    async def generate(self, prompt: str, image: Any | None = None) -> str:
        """Generate text, optionally including a resized image payload."""
        return await asyncio.to_thread(self._generate_sync, prompt, image)

    def reset_context(self) -> None:
        """Flush the model context when the backend exposes a reset hook."""
        reset = getattr(self.llm, "reset", None)
        if callable(reset):
            reset()

    def _generate_sync(self, prompt: str, image: Any | None = None) -> str:
        messages = cast(list[ChatCompletionRequestMessage], 
            [
                {
                    "role": "user", 
                    "content": _message_content(prompt, image)
                }
            ]
        )
        started = time.perf_counter()
        first_token_recorded = False
        chunks: list[str] = []

        stream = self.llm.create_chat_completion(messages=messages, stream=True)
        for chunk in stream:
            token = _chunk_text(chunk)
            if token and not first_token_recorded:
                self.benchmark_logger.record_ttft(time.perf_counter() - started)
                first_token_recorded = True
            chunks.append(token)

        metadata = getattr(self.llm, "last_run_metadata", {}) or {}
        throughput = metadata.get("tokens_per_second") or metadata.get("token_throughput")
        if throughput is not None:
            self.benchmark_logger.record_token_throughput(float(throughput))

        return "".join(chunks)


def parse_tool_call(text: str) -> ToolCall | None:
    """Parse a JSON tool call from raw output or fenced markdown."""
    if not text or not text.strip():
        return None

    for candidate in _json_candidates(text):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        try:
            return ToolCall(tool=payload["tool"], params=payload.get("params", {}))
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    candidates = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        candidates.append(match.group(1).strip())

    stripped = text.strip()
    candidates.append(stripped)

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            _, end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(stripped[index : index + end])
        break

    return candidates


def _message_content(prompt: str, image: Any | None) -> str | list[dict[str, Any]]:
    if image is None:
        return prompt
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": _image_data_url(image)}},
    ]


def _image_data_url(image: Any) -> str:
    resized = image.resize((1280, 720))
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _chunk_text(chunk: str | CreateChatCompletionStreamResponse) -> str:
    
    if isinstance(chunk, str):
        return chunk
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    delta = choice.get("delta") or {}
    if "content" in delta:
        return delta["content"] or ""
    message = choice.get("message") or {}
    return message.get("content") or choice.get("text") or ""


def _env_value(key: str, default: str | None = None) -> str:
    value = os.getenv(key)
    if value is not None:
        return value

    env_path = Path(".env")
    if not default:
        return "" #TODO: Remove it later and manage None in other functions
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, line_value = line.partition("=")
        if separator and name.strip() == key:
            return line_value.strip() or ""
    return default
