"""Operating system interaction tools."""

from __future__ import annotations

import os
import time

from src.core.types import ToolResult

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

try:
    from plyer import notification
except ImportError:
    notification = None


def get_clipboard() -> ToolResult:
    started = time.perf_counter()
    try:
        _require(pyperclip, "pyperclip")
        return _result(started, True, data=pyperclip.paste())
    except Exception as exc:
        return _result(started, False, error=str(exc))


def set_clipboard(text: str) -> ToolResult:
    started = time.perf_counter()
    try:
        _require(pyperclip, "pyperclip")
        pyperclip.copy(text)
        return _result(started, True)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def get_active_window() -> ToolResult:
    started = time.perf_counter()
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
    try:
        _require(psutil, "psutil")
        apps = []
        for process in psutil.process_iter(["name", "pid"]):
            info = getattr(process, "info", {})
            apps.append({"name": info.get("name"), "pid": info.get("pid")})
        return _result(started, True, data=apps)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def send_notification(title: str, message: str) -> ToolResult:
    started = time.perf_counter()
    try:
        _require(notification, "plyer")
        notification.notify(title=title, message=message)
        return _result(started, True)
    except Exception as exc:
        return _result(started, False, error=str(exc))


def open_with_default_app(path: str) -> ToolResult:
    started = time.perf_counter()
    try:
        os.startfile(path)
        return _result(started, True, data={"path": path})
    except Exception as exc:
        return _result(started, False, error=str(exc))


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
