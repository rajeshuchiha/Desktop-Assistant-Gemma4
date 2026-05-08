import json
import pytest
from pathlib import Path
from src.core.benchmark_logger import BenchmarkLogger


def test_creates_output_file():
    logger = BenchmarkLogger(output_dir=Path("benchmarks"))
    logger.start_task("test_001", "open_tab")
    logger.record_ttft(1.2)
    logger.record_vram_peak(4.1)
    output = logger.end_task(success=True, e2e_latency_sec=3.5)
    assert output.exists()
    assert output.suffix == ".json"

def test_json_has_all_metrics():
    # After flush(), output JSON must contain all 11 metric keys
    logger = BenchmarkLogger(output_dir=Path("benchmarks"))
    logger.start_task("test_metrics", "metrics_shape")
    output = logger.end_task(success=True, e2e_latency_sec=1.0)

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert set(payload["metrics"]) == set(BenchmarkLogger.METRIC_KEYS)
    assert len(payload["metrics"]) == 11

def test_vram_peak_is_highest_sample():
    # If VRAM is polled at [3.8, 4.2, 4.0], peak should be 4.2
    logger = BenchmarkLogger(output_dir=Path("benchmarks"))
    logger.start_task("test_vram", "vram_peak")

    logger.record_vram_peak(3.8)
    logger.record_vram_peak(4.2)
    logger.record_vram_peak(4.0)
    output = logger.end_task(success=True, e2e_latency_sec=1.0)

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["metrics"]["vram_peak_gb"] == 4.2

def test_retry_rate_calculated_correctly():
    # 1 retry out of 5 calls = 20% retry rate in output
    logger = BenchmarkLogger(output_dir=Path("benchmarks"))
    logger.start_task("test_retry", "retry_rate")

    logger.record_tool_call("get_open_tabs", success=True, retried=False)
    logger.record_tool_call("switch_to_tab", success=True, retried=False)
    logger.record_tool_call("read_file", success=True, retried=True)
    logger.record_tool_call("write_file", success=False, retried=False)
    logger.record_tool_call("get_clipboard", success=True, retried=False)
    output = logger.end_task(success=False, e2e_latency_sec=1.0)

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["metrics"]["tool_calls"] == 5
    assert payload["metrics"]["tool_retry_rate"] == pytest.approx(0.2)


def test_valid_json_output():
    logger = BenchmarkLogger(output_dir=Path("benchmarks"))
    logger.start_task("test_json", "valid_json")

    output = logger.end_task(success=True, e2e_latency_sec=0.5)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["task_id"] == "test_json"
    assert payload["task_name"] == "valid_json"
    assert payload["success"] is True
