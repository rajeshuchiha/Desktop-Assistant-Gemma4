"""Overlay finite-state machine and IPC queue skeleton."""

from __future__ import annotations

from enum import StrEnum
from multiprocessing import Queue as MultiprocessingQueue
from queue import Queue as LocalQueue
from typing import Any


class State(StrEnum):
    """Overlay visibility and task states."""

    HIDDEN = "hidden"
    PEEK = "peek"
    ACTIVE = "active"
    LISTENING = "listening"
    WORKING = "working"
    RESULT = "result"


class OverlayFSM:
    """Pure FSM for overlay behavior, with a simple multiprocessing IPC queue."""

    _TRANSITIONS: dict[State, dict[str, State]] = {
        State.HIDDEN: {"mouse_near": State.PEEK},
        State.PEEK: {"hover": State.ACTIVE, "hotkey": State.ACTIVE},
        State.ACTIVE: {
            "push_to_talk": State.LISTENING,
            "task_start": State.WORKING,
        },
        State.WORKING: {"task_complete": State.RESULT},
        State.RESULT: {"timeout": State.HIDDEN, "dismiss": State.HIDDEN},
    }

    def __init__(self, message_queue: Any | None = None):
        self.current_state = State.HIDDEN
        self.message_queue = message_queue or self._create_message_queue()

    def transition(self, event: str) -> State:
        if event == "inactivity":
            self.current_state = State.HIDDEN
            return self.current_state

        next_state = self._TRANSITIONS.get(self.current_state, {}).get(event)
        if next_state is None:
            raise ValueError(f"Invalid transition from {self.current_state.value} on {event!r}")

        self.current_state = next_state
        return self.current_state

    def send_message(self, message_type: str, data: dict[str, Any] | None = None) -> None:
        self.message_queue.put({"type": message_type, "data": data or {}})

    def receive_message(self, timeout: float | None = None) -> dict[str, Any]:
        message = self.message_queue.get(timeout=timeout)
        self._validate_message(message)
        return message

    @staticmethod
    def _validate_message(message: Any) -> None:
        if not isinstance(message, dict):
            raise ValueError("IPC message must be a dict")
        if not isinstance(message.get("type"), str):
            raise ValueError("IPC message type must be a string")
        if not isinstance(message.get("data"), dict):
            raise ValueError("IPC message data must be a dict")

    @staticmethod
    def _create_message_queue() -> Any:
        try:
            return MultiprocessingQueue()
        except PermissionError:
            return LocalQueue()


OverlayState = State
