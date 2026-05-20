"""ARIA application runner wiring speech, overlay, proactivity, and tools."""

from __future__ import annotations

import asyncio
import inspect
import multiprocessing
import time
from dataclasses import dataclass
from queue import Empty
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency declared, but keep startup graceful.
    load_dotenv = None  # type: ignore[assignment]

from src.core.orchestrator import Orchestrator, parse_tool_call
from src.core.types import ToolCall, ToolResult
from src.input.stt import SpeechInput
from src.overlay.state_machine import run_overlay
from src.proactivity.clipboard_watcher import ClipboardWatcher


@dataclass
class RuntimeHandles:
    speech: Any
    overlay_process: multiprocessing.Process | None
    clipboard_watcher: ClipboardWatcher
    orchestrator: Any
    ipc_queue: Any


class ARIAMainApp:
    """Small poll-based runtime that keeps the production loop testable."""

    def __init__(
        self,
        speech: Any,
        orchestrator: Any,
        clipboard_watcher: ClipboardWatcher,
        ipc_queue: Any,
        tool_dispatcher: Callable[[ToolCall], Any] | None = None,
    ):
        self.speech = speech
        self.orchestrator = orchestrator
        self.clipboard_watcher = clipboard_watcher
        self.ipc_queue = ipc_queue
        self.tool_dispatcher = tool_dispatcher or dispatch_tool_call

    def process_once(self) -> bool:
        """Process at most one input or suggestion. Returns True when work happened."""
        suggestion = self._get_nowait(self.clipboard_watcher.suggestion_queue)
        if suggestion is not None:
            self.ipc_queue.put(suggestion)
            return True

        speech_text = self._get_speech_nowait()
        if speech_text:
            self._handle_user_input(str(speech_text))
            return True

        overlay_text = self._get_overlay_text_nowait()
        if overlay_text:
            self._handle_user_input(overlay_text)
            return True

        return False

    def run_forever(self, poll_interval: float = 0.05) -> None:
        try:
            while True:
                did_work = self.process_once()
                if not did_work:
                    time.sleep(poll_interval)
        finally:
            self.stop()

    def stop(self) -> None:
        stop = getattr(self.speech, "stop", None)
        if callable(stop):
            stop()
        self.clipboard_watcher.stop()

    def _handle_user_input(self, text: str) -> None:
        self.ipc_queue.put({"type": "listening"})
        response = self._call_generate(text)
        tool_call = parse_tool_call(response)
        if tool_call is not None:
            result = self.tool_dispatcher(tool_call)
        else:
            result = response
        self.ipc_queue.put({"type": "result", "data": _result_payload(result)})

    def _call_generate(self, text: str) -> str:
        generated = self.orchestrator.generate(text)
        if inspect.isawaitable(generated):
            generated = _run_awaitable(generated)
        return str(generated)

    def _get_speech_nowait(self) -> str | None:
        queue = getattr(self.speech, "result_queue", None)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except (asyncio.QueueEmpty, Empty):
            return None

    def _get_overlay_text_nowait(self) -> str | None:
        message = self._get_nowait(self.ipc_queue)
        if message is None:
            return None
        text = _extract_text_input(message)
        if text:
            return text
        self.ipc_queue.put(message)
        return None

    @staticmethod
    def _get_nowait(queue: Any) -> Any | None:
        try:
            return queue.get_nowait()
        except (asyncio.QueueEmpty, Empty):
            return None


def create_runtime() -> tuple[ARIAMainApp, RuntimeHandles]:
    if load_dotenv is not None:
        load_dotenv()

    ipc_queue = multiprocessing.Queue()
    orchestrator = Orchestrator()
    speech = SpeechInput()
    speech.start()

    overlay_process = multiprocessing.Process(target=run_overlay, args=(ipc_queue,), daemon=True)
    overlay_process.start()

    clipboard_watcher = ClipboardWatcher(orchestrator)
    clipboard_watcher.start()

    app = ARIAMainApp(
        speech=speech,
        orchestrator=orchestrator,
        clipboard_watcher=clipboard_watcher,
        ipc_queue=ipc_queue,
    )
    handles = RuntimeHandles(
        speech=speech,
        overlay_process=overlay_process,
        clipboard_watcher=clipboard_watcher,
        orchestrator=orchestrator,
        ipc_queue=ipc_queue,
    )
    return app, handles


def dispatch_tool_call(tool_call: ToolCall) -> Any:
    tool = tool_call.tool
    params = tool_call.params or {}
    module_name = _TOOL_MODULES.get(tool)
    if module_name is None:
        return ToolResult(success=False, error=f"Unknown tool: {tool}")

    module = __import__(module_name, fromlist=[tool])
    function = getattr(module, tool, None)
    if not callable(function):
        return ToolResult(success=False, error=f"Tool is not callable: {tool}")

    result = function(**params)
    if inspect.isawaitable(result):
        result = _run_awaitable(result)
    return result


def _extract_text_input(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    message_type = message.get("type")
    if message_type not in {"text", "input", "prompt"}:
        return None
    data = message.get("data") or {}
    if isinstance(data, dict):
        text = data.get("text") or data.get("prompt")
        return str(text) if text else None
    return None


def _result_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, ToolResult):
        return result.model_dump()
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {"text": str(result)}


def _run_awaitable(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("Cannot synchronously wait for an awaitable while an event loop is running")


_TOOL_MODULES = {
    "get_open_tabs": "src.tools.cdp_tab_agent",
    "switch_to_tab": "src.tools.cdp_tab_agent",
    "find_tab_by_keyword": "src.tools.cdp_tab_agent",
    "open_url_in_new_tab": "src.tools.cdp_tab_agent",
    "open_url_in_active_tab": "src.tools.cdp_tab_agent",
    "close_tab": "src.tools.cdp_tab_agent",
    "get_recent_history": "src.tools.cdp_tab_agent",
    "list_dir": "src.tools.file_tools",
    "read_file": "src.tools.file_tools",
    "search_files": "src.tools.file_tools",
    "get_file_info": "src.tools.file_tools",
    "write_file": "src.tools.file_tools",
    "delete_file": "src.tools.file_tools",
    "move_file": "src.tools.file_tools",
    "create_dir": "src.tools.file_tools",
    "get_clipboard": "src.tools.os_tools",
    "get_active_window": "src.tools.os_tools",
    "list_running_apps": "src.tools.os_tools",
    "set_clipboard": "src.tools.os_tools",
    "send_notification": "src.tools.os_tools",
    "open_with_default_app": "src.tools.os_tools",
    "read_screen": "src.tools.vision_agent",
    "click_element": "src.tools.vision_agent",
}


def main() -> None:
    app, _handles = create_runtime()
    app.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
