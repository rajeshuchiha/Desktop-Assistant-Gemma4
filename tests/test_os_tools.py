from types import SimpleNamespace

from src.core.types import ToolResult
from src.tools import os_tools


def test_get_clipboard(monkeypatch):
    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"os_clipboard_read": True})
    monkeypatch.setattr(os_tools, "pyperclip", SimpleNamespace(paste=lambda: "clip text"))

    result = os_tools.get_clipboard()

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == "clip text"


def test_get_clipboard_capability_blocked(monkeypatch):
    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"os_clipboard_read": False})

    result = os_tools.get_clipboard()

    assert result.success is False
    assert "CAPABILITY_DISABLED: os_clipboard_read" in result.error


def test_get_active_window(monkeypatch):
    window = SimpleNamespace(title="Editor", pid=123)

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def exe(self):
            return "editor.exe"

    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"screen_read": True})
    monkeypatch.setattr(os_tools, "pygetwindow", SimpleNamespace(getActiveWindow=lambda: window))
    monkeypatch.setattr(os_tools, "psutil", SimpleNamespace(Process=FakeProcess))

    result = os_tools.get_active_window()

    assert result.success is True
    assert result.data == {"title": "Editor", "exe": "editor.exe", "pid": 123}


def test_get_active_window_capability_blocked(monkeypatch):
    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"screen_read": False})

    result = os_tools.get_active_window()

    assert result.success is False
    assert "CAPABILITY_DISABLED: screen_read" in result.error


def test_list_running_apps(monkeypatch):
    processes = [
        SimpleNamespace(info={"name": "python.exe", "pid": 1}),
        SimpleNamespace(info={"name": "chrome.exe", "pid": 2}),
    ]
    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"screen_read": True})
    monkeypatch.setattr(os_tools, "psutil", SimpleNamespace(process_iter=lambda attrs: processes))

    result = os_tools.list_running_apps()

    assert result.success is True
    assert result.data == [{"name": "python.exe", "pid": 1}, {"name": "chrome.exe", "pid": 2}]


def test_list_running_apps_capability_blocked(monkeypatch):
    monkeypatch.setattr(os_tools, "load_capabilities", lambda: {"screen_read": False})

    result = os_tools.list_running_apps()

    assert result.success is False
    assert "CAPABILITY_DISABLED: screen_read" in result.error


def test_deferred_write_operations_are_blocked():
    assert "CAPABILITY_DISABLED: os_clipboard_write" in os_tools.set_clipboard("hello").error
    assert "CAPABILITY_DISABLED: os_notification" in os_tools.send_notification("Hi", "Done").error
    assert "CAPABILITY_DISABLED: os_open" in os_tools.open_with_default_app("settings.json").error
