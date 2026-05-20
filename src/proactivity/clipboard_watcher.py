"""Clipboard proactivity watcher for surfacing high-confidence suggestions."""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from multiprocessing import Queue as MultiprocessingQueue
from queue import Queue as LocalQueue
from typing import Any

try:
    import pyperclip
except ImportError:  # pragma: no cover - tests can monkeypatch this symbol.
    pyperclip = None  # type: ignore[assignment]


PROMPT_TEMPLATE = """Rate relevance 0-10. Is this actionable?
Content: {content}
Return only JSON {{score: int, action: str | null, reason: str}}"""


class ClipboardWatcher:
    """Poll the text clipboard and ask the orchestrator whether to suggest an action."""

    def __init__(
        self,
        orchestrator: Any,
        suggestion_queue: Any | None = None,
        poll_interval: float = 1.0,
    ):
        self.orchestrator = orchestrator
        self.suggestion_queue = suggestion_queue or self._create_suggestion_queue()
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_content: str | None = None

    def start(self) -> None:
        """Start polling in a daemon background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_content = self._read_clipboard_text()
        self._thread = threading.Thread(target=self._run, name="ARIAClipboardWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and wait briefly for the background thread to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.poll_interval + 0.25))
            self._thread = None

    def poll_once(self) -> None:
        """Run one clipboard check; intended for tests and manual integration checks."""
        content = self._read_clipboard_text()
        if content is None:
            return
        if content == self._last_content:
            return
        self._last_content = content
        self._evaluate_content(content)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval)

    def _evaluate_content(self, content: str) -> None:
        prompt = PROMPT_TEMPLATE.format(content=content[:200])
        try:
            raw_result = self.orchestrator.generate(prompt)
            if inspect.isawaitable(raw_result):
                raw_result = asyncio.run(raw_result)
            decision = self._parse_decision(str(raw_result))
        except Exception:
            return

        score = decision.get("score", 0)
        action = decision.get("action")
        try:
            score_value = int(score)
        except (TypeError, ValueError):
            return
        if score_value >= 7 and action:
            self.suggestion_queue.put(
                {
                    "type": "suggestion",
                    "action": str(action),
                    "content": content,
                }
            )

    def _read_clipboard_text(self) -> str | None:
        if pyperclip is None:
            return None
        try:
            content = pyperclip.paste()
        except Exception:
            return None
        if not isinstance(content, str):
            return None
        return content

    @staticmethod
    def _parse_decision(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return json.loads(stripped)

    @staticmethod
    def _create_suggestion_queue() -> Any:
        try:
            return MultiprocessingQueue()
        except PermissionError:
            return LocalQueue()
