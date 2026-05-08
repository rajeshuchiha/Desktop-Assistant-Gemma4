"""
benchmark_logger.py — ARIA Telemetry Module

PURPOSE:
  Records structured JSON telemetry for every agent task run.
  Captures all 11 metrics defined in PRD Section 5.1.

INTERFACE (implement exactly this):
  class BenchmarkLogger:
    def start_task(self, task_id: str, task_name: str) -> None
    def record_ttft(self, seconds: float) -> None
    def record_token_throughput(self, tokens_per_sec: float) -> None
    def record_vram_peak(self, gb: float) -> None
    def record_cdp_latency(self, ms: float) -> None
    def record_stt_latency(self, ms: float) -> None
    def record_vision_grounding(self, success: bool, px_error: float) -> None
    def record_tool_call(self, tool: str, success: bool, retry: bool) -> None
    def end_task(self, success: bool, e2e_latency_sec: float) -> None
    def flush(self) -> Path  # writes JSON to ~/.aria/benchmarks/

DEPENDENCIES:
  - nvidia-ml-py for VRAM polling (poll every 100ms during task, record peak)
  - pathlib for output path
  - datetime for run timestamps
  - json for output

OUTPUT FORMAT:
  ~/.aria/benchmarks/YYYYMMDD_HHMMSS_{task_id}.json
  {
    "task_id": "...",
    "task_name": "...",
    "timestamp": "...",
    "metrics": { ...all 11 metrics... },
    "success": true/false
  }

DO NOT:
  - Use any cloud APIs
  - Import from other aria modules (this must be standalone)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BenchmarkLogger:
    """Standalone JSON telemetry logger for one benchmark task."""

    METRIC_KEYS = (
        "ttft_sec",
        "token_throughput",
        "vram_peak_gb",
        "cdp_latency_ms",
        "stt_latency_ms",
        "vision_grounding_success",
        "vision_grounding_px_error",
        "tool_calls",
        "tool_success_rate",
        "tool_retry_rate",
        "e2e_latency_sec",
    )

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir).expanduser() if output_dir is not None else Path("~/.aria/benchmarks").expanduser()
        self.task_id = ""
        self.task_name = ""
        self.timestamp = ""
        self.success = False
        self.metrics: dict[str, Any] = self._empty_metrics()
        self._tool_calls: list[dict[str, Any]] = []
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._nvml_handle: Any | None = None

    def start_task(self, task_id: str, task_name: str) -> None:
        self._stop_vram_polling()
        self.task_id = task_id
        self.task_name = task_name
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.success = False
        self.metrics = self._empty_metrics()
        self._tool_calls = []
        self._start_vram_polling()

    def record_ttft(self, seconds: float) -> None:
        self.metrics["ttft_sec"] = seconds

    def record_token_throughput(self, tokens_per_sec: float) -> None:
        self.metrics["token_throughput"] = tokens_per_sec

    def record_vram_peak(self, gb: float) -> None:
        self.metrics["vram_peak_gb"] = max(self.metrics["vram_peak_gb"], gb)

    def record_cdp_latency(self, ms: float) -> None:
        self.metrics["cdp_latency_ms"] = ms

    def record_stt_latency(self, ms: float) -> None:
        self.metrics["stt_latency_ms"] = ms

    def record_vision_grounding(self, success: bool, px_error: float) -> None:
        self.metrics["vision_grounding_success"] = success
        self.metrics["vision_grounding_px_error"] = px_error

    def record_tool_call(self, tool: str, success: bool, retried: bool) -> None:
        self._tool_calls.append({"tool": tool, "success": success, "retried": retried})
        self.metrics["tool_calls"] = len(self._tool_calls)
        self._recalculate_tool_rates()

    def end_task(self, success: bool, e2e_latency_sec: float) -> Path:
        self._stop_vram_polling()
        self.success = success
        self.metrics["e2e_latency_sec"] = e2e_latency_sec
        return self.flush()

    def flush(self) -> Path:
        output_dir = self._ensure_output_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = self.task_id or "task"
        output_path = output_dir / f"{timestamp}_{task_id}.json"
        payload = {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "metrics": self.metrics,
            "success": self.success,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    def _recalculate_tool_rates(self) -> None:
        total = len(self._tool_calls)
        if total == 0:
            self.metrics["tool_success_rate"] = 0.0
            self.metrics["tool_retry_rate"] = 0.0
            return
        successes = sum(1 for call in self._tool_calls if call["success"])
        retries = sum(1 for call in self._tool_calls if call["retried"])
        self.metrics["tool_success_rate"] = successes / total
        self.metrics["tool_retry_rate"] = retries / total

    def _start_vram_polling(self) -> None:
        self._poll_stop.clear()
        self._nvml_handle = self._init_nvml_handle()
        if self._nvml_handle is None:
            return
        self._poll_thread = threading.Thread(target=self._poll_vram_loop, daemon=True)
        self._poll_thread.start()

    def _stop_vram_polling(self) -> None:
        self._poll_stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

    def _poll_vram_loop(self) -> None:
        while not self._poll_stop.is_set():
            sample = self._poll_vram_sample()
            if sample is not None:
                self.record_vram_peak(sample)
            time.sleep(0.1)

    def _init_nvml_handle(self) -> Any | None:
        try:
            import pynvml  # provided by the nvidia-ml-py package

            pynvml.nvmlInit()
            return pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            return None

    def _poll_vram_sample(self) -> float | None:
        if self._nvml_handle is None:
            return None
        try:
            import pynvml  # provided by the nvidia-ml-py package

            info = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            return float(info.used) / (1024**3)
        except Exception:
            return None

    def _ensure_output_dir(self) -> Path:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            return self.output_dir
        except OSError:
            fallback = Path("benchmarks")
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    @classmethod
    def _empty_metrics(cls) -> dict[str, Any]:
        return {
            "ttft_sec": 0.0,
            "token_throughput": 0.0,
            "vram_peak_gb": 0.0,
            "cdp_latency_ms": 0.0,
            "stt_latency_ms": 0.0,
            "vision_grounding_success": False,
            "vision_grounding_px_error": 0.0,
            "tool_calls": 0,
            "tool_success_rate": 0.0,
            "tool_retry_rate": 0.0,
            "e2e_latency_sec": 0.0,
        }
