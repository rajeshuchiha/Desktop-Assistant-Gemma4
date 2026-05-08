from types import SimpleNamespace

from src.core.types import ToolResult
from src.tools import os_tools


def test_get_clipboard(monkeypatch):
    monkeypatch.setattr(os_tools, "pyperclip", SimpleNamespace(paste=lambda: "clip text"))

    result = os_tools.get_clipboard()

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == "clip text"


def test_set_clipboard(monkeypatch):
    copied = {}
    monkeypatch.setattr(os_tools, "pyperclip", SimpleNamespace(copy=lambda text: copied.update({"text": text})))

    result = os_tools.set_clipboard("hello")

    assert result.success is True
    assert copied == {"text": "hello"}


def test_get_active_window(monkeypatch):
    window = SimpleNamespace(title="Editor", pid=123)

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def exe(self):
            return "editor.exe"

    monkeypatch.setattr(os_tools, "pygetwindow", SimpleNamespace(getActiveWindow=lambda: window))
    monkeypatch.setattr(os_tools, "psutil", SimpleNamespace(Process=FakeProcess))

    result = os_tools.get_active_window()

    assert result.success is True
    assert result.data == {"title": "Editor", "exe": "editor.exe", "pid": 123}


def test_list_running_apps(monkeypatch):
    processes = [
        SimpleNamespace(info={"name": "python.exe", "pid": 1}),
        SimpleNamespace(info={"name": "chrome.exe", "pid": 2}),
    ]
    monkeypatch.setattr(os_tools, "psutil", SimpleNamespace(process_iter=lambda attrs: processes))

    result = os_tools.list_running_apps()

    assert result.success is True
    assert result.data == [{"name": "python.exe", "pid": 1}, {"name": "chrome.exe", "pid": 2}]


def test_send_notification(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        os_tools,
        "notification",
        SimpleNamespace(notify=lambda title, message: sent.update({"title": title, "message": message})),
    )

    result = os_tools.send_notification("Hi", "Done")

    assert result.success is True
    assert sent == {"title": "Hi", "message": "Done"}


def test_open_with_default_app(monkeypatch):
    opened = {}
    monkeypatch.setattr(os_tools.os, "startfile", lambda path: opened.update({"path": path}), raising=False)

    result = os_tools.open_with_default_app("settings.json")

    assert result.success is True
    assert opened == {"path": "settings.json"}
