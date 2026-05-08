"""Read-only filesystem tools."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.types import ToolResult, capability_blocked, load_capabilities


SUPPORTED_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".json",
    ".csv",
    ".log",
    ".html",
    ".yaml",
    ".toml",
}


def list_dir(path: str) -> ToolResult:
    started = time.perf_counter()
    blocked = _file_read_blocked()
    if blocked is not None:
        return blocked
    try:
        data = [_entry_data(child) for child in Path(path).iterdir()]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def read_file(path: str) -> ToolResult:
    started = time.perf_counter()
    blocked = _file_read_blocked()
    if blocked is not None:
        return blocked
    try:
        target = Path(path)
        if target.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
            return _result(started, False, error=f"binary or unsupported file type: {target.suffix}")
        if _is_binary(target):
            return _result(started, False, error="binary file rejected")
        content = target.read_text(encoding="utf-8")
        return _result(
            started,
            True,
            data={"content": content, "encoding": "utf-8", "size_bytes": target.stat().st_size},
        )
    except UnicodeDecodeError:
        return _result(started, False, error="binary file rejected: unable to decode as utf-8")
    except Exception as exc:
        return _result(started, False, error=str(exc))


def search_files(directory: str, pattern: str) -> ToolResult:
    started = time.perf_counter()
    blocked = _file_read_blocked()
    if blocked is not None:
        return blocked
    try:
        data = [_search_result(path) for path in Path(directory).rglob(pattern)]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def get_file_info(path: str) -> ToolResult:
    started = time.perf_counter()
    blocked = _file_read_blocked()
    if blocked is not None:
        return blocked
    try:
        target = Path(path)
        stat = target.stat()
        return _result(
            started,
            True,
            data={
                "name": target.name,
                "path": str(target.resolve(strict=False)),
                "size_bytes": stat.st_size,
                "created": _timestamp(stat.st_ctime),
                "modified": _timestamp(stat.st_mtime),
                "extension": target.suffix.lower(),
                "is_binary": _is_binary(target),
            },
        )
    except Exception as exc:
        return _result(started, False, error=str(exc))


def write_file(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("file_write")


def delete_file(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("file_write")


def move_file(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("file_write")


def create_dir(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("file_write")


def _file_read_blocked() -> ToolResult | None:
    caps = load_capabilities()
    if not caps.get("file_read", False):
        return capability_blocked("file_read")
    return None


def _entry_data(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "type": "dir" if path.is_dir() else "file",
        "size_bytes": stat.st_size,
        "modified": _timestamp(stat.st_mtime),
    }


def _search_result(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "modified": _timestamp(stat.st_mtime)}


def _is_binary(path: Path) -> bool:
    if path.is_dir():
        return False
    sample = path.read_bytes()[:1024]
    return b"\0" in sample


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _result(started: float, success: bool, data=None, error: str | None = None) -> ToolResult:
    return ToolResult(
        success=success,
        data=data,
        error=error,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
