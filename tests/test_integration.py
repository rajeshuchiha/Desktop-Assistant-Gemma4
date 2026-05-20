from __future__ import annotations

import asyncio
from queue import Empty, Queue

from src.core.types import ToolCall, ToolResult
from src.main import ARIAMainApp


class FakeOrchestrator:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FakeSpeech:
    def __init__(self):
        self.result_queue: asyncio.Queue[str] = asyncio.Queue()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeClipboardWatcher:
    def __init__(self):
        self.suggestion_queue: Queue = Queue()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def collect_queue(queue: Queue) -> list[dict]:
    messages = []
    while True:
        try:
            messages.append(queue.get_nowait())
        except Empty:
            return messages


def make_app(orchestrator: FakeOrchestrator):
    speech = FakeSpeech()
    clipboard = FakeClipboardWatcher()
    overlay_queue = Queue()
    dispatched: list[ToolCall] = []

    def dispatch(tool_call: ToolCall) -> ToolResult:
        dispatched.append(tool_call)
        return ToolResult(success=True, data={"tool": tool_call.tool, "params": tool_call.params})

    app = ARIAMainApp(
        speech=speech,
        orchestrator=orchestrator,
        clipboard_watcher=clipboard,
        ipc_queue=overlay_queue,
        tool_dispatcher=dispatch,
    )
    return app, speech, clipboard, overlay_queue, dispatched


def test_speech_input_calls_orchestrator_dispatches_tool_and_shows_result():
    orchestrator = FakeOrchestrator('{"tool": "fake_tool", "params": {"value": 7}}')
    app, speech, _clipboard, overlay_queue, dispatched = make_app(orchestrator)
    speech.result_queue.put_nowait("open the fake tool")

    assert app.process_once() is True

    assert orchestrator.prompts == ["open the fake tool"]
    assert dispatched[0].tool == "fake_tool"
    assert dispatched[0].params == {"value": 7}
    messages = collect_queue(overlay_queue)
    assert messages[0] == {"type": "listening"}
    assert messages[1]["type"] == "result"
    assert messages[1]["data"]["success"] is True
    assert messages[1]["data"]["data"]["tool"] == "fake_tool"


def test_text_input_calls_orchestrator_dispatches_tool_and_shows_result():
    orchestrator = FakeOrchestrator('{"tool": "fake_tool", "params": {"source": "overlay"}}')
    app, _speech, _clipboard, overlay_queue, dispatched = make_app(orchestrator)
    overlay_queue.put({"type": "text", "data": {"text": "run from overlay"}})

    assert app.process_once() is True

    assert orchestrator.prompts == ["run from overlay"]
    assert dispatched[0].params == {"source": "overlay"}
    messages = collect_queue(overlay_queue)
    assert messages[0] == {"type": "listening"}
    assert messages[1]["type"] == "result"
    assert messages[1]["data"]["data"]["params"] == {"source": "overlay"}


def test_clipboard_suggestion_is_forwarded_to_overlay_queue():
    orchestrator = FakeOrchestrator("plain response")
    app, _speech, clipboard, overlay_queue, _dispatched = make_app(orchestrator)
    suggestion = {"type": "suggestion", "action": "Open this URL?", "content": "https://example.com"}
    clipboard.suggestion_queue.put(suggestion)

    assert app.process_once() is True

    assert collect_queue(overlay_queue) == [suggestion]
    assert orchestrator.prompts == []
