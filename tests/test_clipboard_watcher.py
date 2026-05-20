from __future__ import annotations

from queue import Empty, Queue

from src.proactivity import clipboard_watcher
from src.proactivity.clipboard_watcher import ClipboardWatcher


class FakeClipboard:
    def __init__(self, value):
        self.value = value

    def paste(self):
        return self.value


class FakeOrchestrator:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_high_score_triggers_suggestion(monkeypatch):
    monkeypatch.setattr(clipboard_watcher, "pyperclip", FakeClipboard("https://example.com"))
    orchestrator = FakeOrchestrator('{"score": 8, "action": "Open this URL?", "reason": "URL"}')
    suggestion_queue = Queue()
    watcher = ClipboardWatcher(orchestrator, suggestion_queue=suggestion_queue)

    watcher.poll_once()

    assert suggestion_queue.get_nowait() == {
        "type": "suggestion",
        "action": "Open this URL?",
        "content": "https://example.com",
    }
    assert "Content: https://example.com" in orchestrator.prompts[0]


def test_low_score_produces_nothing(monkeypatch):
    monkeypatch.setattr(clipboard_watcher, "pyperclip", FakeClipboard("plain note"))
    orchestrator = FakeOrchestrator('{"score": 3, "action": null, "reason": "not actionable"}')
    suggestion_queue = Queue()
    watcher = ClipboardWatcher(orchestrator, suggestion_queue=suggestion_queue)

    watcher.poll_once()

    try:
        suggestion_queue.get_nowait()
    except Empty:
        pass
    else:
        raise AssertionError("low score should not enqueue a suggestion")


def test_non_text_clipboard_does_not_crash(monkeypatch):
    monkeypatch.setattr(clipboard_watcher, "pyperclip", FakeClipboard(object()))
    orchestrator = FakeOrchestrator('{"score": 10, "action": "Summarise this?", "reason": "text"}')
    suggestion_queue = Queue()
    watcher = ClipboardWatcher(orchestrator, suggestion_queue=suggestion_queue)

    watcher.poll_once()

    assert orchestrator.prompts == []
