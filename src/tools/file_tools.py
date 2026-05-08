"""File operation tools with zone-restricted writes."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from send2trash import send2trash

from src.core.types import ToolResult
from src.tools import zone_validator


def list_dir(path: str) -> ToolResult:
    started = time.perf_counter()
    try:
        data = [child.name for child in Path(path).iterdir()]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def read_file(path: str) -> ToolResult:
    started = time.perf_counter()
    try:
        return _result(started, True, data=Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return _result(started, False, error=str(exc))


def search_files(directory: str, pattern: str) -> ToolResult:
    started = time.perf_counter()
    try:
        data = [str(path) for path in Path(directory).glob(pattern)]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def write_file(path: str, content: str) -> ToolResult:
    started = time.perf_counter()
    target = Path(path)
    allowed, reason = zone_validator.is_write_allowed(target)
    if not allowed:
        return _result(started, False, error=reason)
    if zone_validator.is_destructive(target):
        return _result(started, False, error=f"CONFIRM_REQUIRED: overwrite {target}")
    try:
        target.write_text(content, encoding="utf-8")
        return _result(started, True, data={"path": str(target)})
    except Exception as exc:
        return _result(started, False, error=str(exc))


def create_dir(path: str) -> ToolResult:
    started = time.perf_counter()
    target = Path(path)
    allowed, reason = zone_validator.is_write_allowed(target)
    if not allowed:
        return _result(started, False, error=reason)
    try:
        target.mkdir(parents=True, exist_ok=True)
        return _result(started, True, data={"path": str(target)})
    except Exception as exc:
        return _result(started, False, error=str(exc))


def move_file(src: str, dst: str) -> ToolResult:
    started = time.perf_counter()
    destination = Path(dst)
    allowed, reason = zone_validator.is_write_allowed(destination)
    if not allowed:
        return _result(started, False, error=reason)
    if zone_validator.is_destructive(destination):
        return _result(started, False, error=f"CONFIRM_REQUIRED: overwrite {destination}")
    try:
        shutil.move(src, dst)
        return _result(started, True, data={"src": src, "dst": dst})
    except Exception as exc:
        return _result(started, False, error=str(exc))


def delete_file(path: str) -> ToolResult:
    started = time.perf_counter()
    return _result(started, False, error=f"CONFIRM_REQUIRED: delete {path}")


def confirm_delete(path: str) -> ToolResult:
    started = time.perf_counter()
    try:
        send2trash(path)
        return _result(started, True, data={"path": path})
    except Exception as exc:
        return _result(started, False, error=str(exc))


def _result(started: float, success: bool, data=None, error: str | None = None) -> ToolResult:
    return ToolResult(
        success=success,
        data=data,
        error=error,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
