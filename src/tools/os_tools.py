"""Read-only operating system inspection tools."""

from __future__ import annotations

import time
from typing import Any

from src.core.types import ToolResult, capability_blocked, load_capabilities

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pygetwindow
except ImportError:
    pygetwindow = None

try:
    import psutil
except ImportError:
    psutil = None


def get_clipboard() -> ToolResult:
    started = time.perf_counter()
    blocked = _capability_block("os_clipboard_read")
    if blocked is not None:
        return blocked
    try:
        _require(pyperclip, "pyperclip")
        return _result(started, True, data=pyperclip.paste())
    except Exception as exc:
        return _result(started, False, error=str(exc))


def get_active_window() -> ToolResult:
    started = time.perf_counter()
    blocked = _capability_block("screen_read")
    if blocked is not None:
        return blocked
    try:
        _require(pygetwindow, "pygetwindow")
        _require(psutil, "psutil")
        window = pygetwindow.getActiveWindow()
        if window is None:
            return _result(started, False, error="no active window")
        pid = _window_pid(window)
        process = psutil.Process(pid)
        exe_getter = getattr(process, "exe", None)
        exe = exe_getter() if callable(exe_getter) else ""
        if not exe:
            name_getter = getattr(process, "name", None)
            exe = name_getter() if callable(name_getter) else ""
        return _result(started, True, data={"title": getattr(window, "title", ""), "exe": exe, "pid": pid})
    except Exception as exc:
        return _result(started, False, error=str(exc))


def list_running_apps() -> ToolResult:
    started = time.perf_counter()
    blocked = _capability_block("screen_read")
    if blocked is not None:
        return blocked
    try:
        _require(psutil, "psutil")
        apps = []
        for process in psutil.process_iter(["name", "pid"]):
            info = getattr(process, "info", {})
            apps.append({"name": info.get("name"), "pid": info.get("pid")})
        return _result(started, True, data=apps)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def set_clipboard(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("os_clipboard_write")


def send_notification(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("os_notification")


def open_with_default_app(*args: Any, **kwargs: Any) -> ToolResult:
    return capability_blocked("os_open")


def _capability_block(capability: str) -> ToolResult | None:
    caps = load_capabilities()
    if not caps.get(capability, False):
        return capability_blocked(capability)
    return None


def _window_pid(window) -> int:
    pid = getattr(window, "pid", None)
    if pid is not None:
        return int(pid)
    private_pid = getattr(window, "_pid", None)
    if private_pid is not None:
        return int(private_pid)

    hwnd = getattr(window, "_hWnd", None) or getattr(window, "hWnd", None)
    if hwnd:
        try:
            import win32process

            return int(win32process.GetWindowThreadProcessId(hwnd)[1])
        except ImportError as exc:
            raise RuntimeError("active window pid unavailable without pywin32") from exc
    raise RuntimeError("active window pid unavailable")


def _require(module, name: str) -> None:
    if module is None:
        raise RuntimeError(f"{name} is not installed")


def _result(started: float, success: bool, data=None, error: str | None = None) -> ToolResult:
    return ToolResult(
        success=success,
        data=data,
        error=error,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
