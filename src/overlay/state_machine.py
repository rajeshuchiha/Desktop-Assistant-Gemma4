"""Overlay finite-state machine and PySide6 sidebar UI."""

from __future__ import annotations

import sys
from enum import StrEnum
from multiprocessing import Queue as MultiprocessingQueue
from queue import Empty
from queue import Queue as LocalQueue
from typing import Any

try:
    from PySide6.QtCore import QObject, QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, QTimer, Qt, Signal
    from PySide6.QtGui import QAction, QCursor, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - allows pure FSM tests without GUI deps.
    QApplication = None  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment,misc]
    QMainWindow = object  # type: ignore[assignment,misc]
    QWidget = object  # type: ignore[assignment,misc]


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
        State.PEEK: {"hover": State.ACTIVE, "hotkey": State.ACTIVE, "inactivity": State.HIDDEN},
        State.ACTIVE: {
            "push_to_talk": State.LISTENING,
            "task_start": State.WORKING,
            "result": State.RESULT,
            "hide": State.HIDDEN,
        },
        State.LISTENING: {"task_start": State.WORKING, "hide": State.HIDDEN},
        State.WORKING: {"task_complete": State.RESULT, "hide": State.HIDDEN},
        State.RESULT: {"timeout": State.HIDDEN, "dismiss": State.HIDDEN, "hide": State.HIDDEN},
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
        if "data" in message and not isinstance(message.get("data"), dict):
            raise ValueError("IPC message data must be a dict")

    @staticmethod
    def _create_message_queue() -> Any:
        try:
            return MultiprocessingQueue()
        except PermissionError:
            return LocalQueue()


OverlayState = State


class _HotkeyBridge(QObject):  # type: ignore[misc]
    activated = Signal()


class _Spinner(QLabel):  # type: ignore[misc]
    _FRAMES = ("|", "/", "-", "\\")

    def __init__(self) -> None:
        super().__init__(self._FRAMES[0])
        self._index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setObjectName("spinner")

    def start(self) -> None:
        self._timer.start(100)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._index = (self._index + 1) % len(self._FRAMES)
        self.setText(self._FRAMES[self._index])


class _MicIndicator(QFrame):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(20, 20)
        self._bright = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._pulse()

    def start(self) -> None:
        self._timer.start(250)

    def stop(self) -> None:
        self._timer.stop()

    def _pulse(self) -> None:
        color = "#1A56DB" if self._bright else "#7aa2ff"
        self.setStyleSheet(f"border-radius: 10px; background: {color};")
        self._bright = not self._bright


class ARIAOverlay(QMainWindow):  # type: ignore[misc]
    """Frameless right-edge ARIA overlay driven by IPC queue messages."""

    WIDTH = 280
    PEEK_WIDTH = 8
    EDGE_TRIGGER_PX = 40
    ANIMATION_MS = 120

    def __init__(self, ipc_queue: Any | None = None):
        if QApplication is None:
            raise RuntimeError("PySide6 is required to run ARIAOverlay")
        super().__init__()
        self.fsm = OverlayFSM(ipc_queue)
        self.ipc_queue = self.fsm.message_queue
        self._current_animation: QParallelAnimationGroup | None = None
        self._hotkey_listener: Any | None = None
        self._hotkey_bridge = _HotkeyBridge()
        self._hotkey_bridge.activated.connect(lambda: self.apply_state(State.ACTIVE))
        self._last_status = "Working..."
        self._build_window()
        self._build_ui()
        self._build_timers()
        self._install_hotkey()
        self.apply_state(State.HIDDEN, animate=False)

    def apply_state(self, state: State, animate: bool = True) -> None:
        self.fsm.current_state = state
        self._reset_inactivity()
        self._result_timer.stop()
        self._mic.stop()
        self._spinner.stop()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, state == State.HIDDEN)

        if state == State.HIDDEN:
            self._stack.setCurrentWidget(self._hidden_page)
            self._animate_to(self._edge_geometry(self.PEEK_WIDTH), 0.0, animate)
            return
        if state == State.PEEK:
            self._stack.setCurrentWidget(self._peek_page)
            self._animate_to(self._edge_geometry(self.PEEK_WIDTH), 0.7, animate)
            return

        self._animate_to(self._edge_geometry(self.WIDTH), 0.9, animate)
        if state == State.LISTENING:
            self._stack.setCurrentWidget(self._listening_page)
            self._mic.start()
        elif state == State.WORKING:
            self._stack.setCurrentWidget(self._working_page)
            self._spinner.start()
        elif state == State.RESULT:
            self._stack.setCurrentWidget(self._result_page)
            self._result_timer.start(5000)
        else:
            self._stack.setCurrentWidget(self._active_page)

    def show_status(self, text: str) -> None:
        self._last_status = text or "Working..."
        self._status_label.setText(self._last_status)
        self.apply_state(State.WORKING)

    def show_result(self, text: str) -> None:
        self._result_text.setText(text or "Done")
        self.apply_state(State.RESULT)

    def show_suggestion(self, action: str, content: str) -> None:
        label = action or "Suggested action"
        self._suggestion_chip.setText(label)
        self._suggestion_chip.setToolTip(content)
        self._suggestion_chip.show()
        self.apply_state(State.ACTIVE)

    def hide_overlay(self) -> None:
        self.apply_state(State.HIDDEN)

    def _build_window(self) -> None:
        self.setWindowTitle("ARIA")
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(self.WIDTH, self._screen_geometry().height())

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet(
            """
            #root, QStackedWidget { background: #1a1a2e; color: #e0e0e0; }
            QLabel { color: #e0e0e0; font-size: 13px; }
            QPushButton {
                background: #1A56DB; color: #ffffff; border: 0;
                border-radius: 6px; padding: 8px 10px;
            }
            QPushButton:hover { background: #2b6af0; }
            #peek { background: #1A56DB; }
            #card { background: #252542; border: 1px solid #34345a; border-radius: 8px; }
            #suggestion { background: #24365f; border: 1px solid #1A56DB; }
            #spinner { color: #1A56DB; font-size: 24px; font-weight: 700; }
            """
        )
        self._stack = QStackedWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self.setCentralWidget(root)

        self._hidden_page = QWidget()
        self._peek_page = QFrame()
        self._peek_page.setObjectName("peek")
        self._active_page = self._active_content("Ready")
        self._listening_page = self._listening_content()
        self._working_page = self._working_content()
        self._result_page = self._result_content()
        for page in (
            self._hidden_page,
            self._peek_page,
            self._active_page,
            self._listening_page,
            self._working_page,
            self._result_page,
        ):
            self._stack.addWidget(page)

    def _active_content(self, title: str) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        status = QLabel("ARIA")
        status.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(status)
        layout.addWidget(QLabel(title))
        self._suggestion_chip = QPushButton("")
        self._suggestion_chip.setObjectName("suggestion")
        self._suggestion_chip.hide()
        layout.addWidget(self._suggestion_chip)
        layout.addStretch(1)
        return page

    def _listening_content(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        row = QHBoxLayout()
        self._mic = _MicIndicator()
        row.addWidget(self._mic)
        row.addWidget(QLabel("Listening"))
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _working_content(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        self._spinner = _Spinner()
        self._status_label = QLabel(self._last_status)
        self._status_label.setWordWrap(True)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.hide_overlay)
        layout.addWidget(self._spinner)
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        layout.addWidget(cancel)
        return page

    def _result_content(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        self._result_text = QLabel("")
        self._result_text.setWordWrap(True)
        card_layout.addWidget(self._result_text)
        buttons = QHBoxLayout()
        copy = QPushButton("Copy")
        retry = QPushButton("Retry")
        dismiss = QPushButton("Dismiss")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self._result_text.text()))
        retry.clicked.connect(lambda: self.ipc_queue.put({"type": "retry", "data": {}}))
        dismiss.clicked.connect(self.hide_overlay)
        buttons.addWidget(copy)
        buttons.addWidget(retry)
        buttons.addWidget(dismiss)
        card_layout.addLayout(buttons)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _page_layout(self, page: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 20, 18, 20)
        layout.setSpacing(14)
        return layout

    def _build_timers(self) -> None:
        self._ipc_timer = QTimer(self)
        self._ipc_timer.timeout.connect(self._poll_ipc)
        self._ipc_timer.start(50)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._cursor_timer.start(100)
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(lambda: self.apply_state(State.HIDDEN))
        self._result_timer = QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(lambda: self.apply_state(State.HIDDEN))

    def _install_hotkey(self) -> None:
        shortcut = QShortcut(QKeySequence("Alt+Space"), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(lambda: self._hotkey_bridge.activated.emit())
        action = QAction(self)
        action.setShortcut(QKeySequence("Alt+Space"))
        action.triggered.connect(lambda: self._hotkey_bridge.activated.emit())
        self.addAction(action)
        try:
            from pynput import keyboard

            self._hotkey_listener = keyboard.GlobalHotKeys(
                {"<alt>+<space>": lambda: self._hotkey_bridge.activated.emit()}
            )
            self._hotkey_listener.start()
        except Exception:
            self._hotkey_listener = None

    def _poll_ipc(self) -> None:
        while True:
            try:
                message = self.ipc_queue.get_nowait()
            except Empty:
                return
            except Exception:
                return
            try:
                self._handle_message(message)
            except ValueError:
                continue

    def _handle_message(self, message: dict[str, Any]) -> None:
        self.fsm._validate_message({"type": message.get("type"), "data": message.get("data", {})})
        message_type = message["type"]
        data = message.get("data") or {}
        if message_type == "status":
            self.show_status(str(data.get("text", "")))
        elif message_type == "result":
            self.show_result(str(data.get("text", "")))
        elif message_type == "listening":
            self.apply_state(State.LISTENING)
        elif message_type == "hide":
            self.apply_state(State.HIDDEN)
        elif message_type == "suggestion":
            self.show_suggestion(str(message.get("action", "")), str(message.get("content", "")))

    def _poll_cursor(self) -> None:
        if self.fsm.current_state != State.HIDDEN:
            return
        screen = self._screen_geometry()
        cursor = QCursor.pos()
        if cursor.x() >= screen.right() - self.EDGE_TRIGGER_PX:
            self.apply_state(State.PEEK)

    def _reset_inactivity(self) -> None:
        if self.fsm.current_state == State.HIDDEN:
            self._inactivity_timer.stop()
        else:
            self._inactivity_timer.start(8000)

    def _animate_to(self, geometry: QRect, opacity: float, animate: bool) -> None:
        self.show()
        if self._current_animation is not None:
            self._current_animation.stop()
        if not animate:
            self.setGeometry(geometry)
            self.setWindowOpacity(opacity)
            return
        group = QParallelAnimationGroup(self)
        geometry_animation = QPropertyAnimation(self, b"geometry", group)
        geometry_animation.setDuration(self.ANIMATION_MS)
        geometry_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        geometry_animation.setStartValue(self.geometry())
        geometry_animation.setEndValue(geometry)
        opacity_animation = QPropertyAnimation(self, b"windowOpacity", group)
        opacity_animation.setDuration(self.ANIMATION_MS)
        opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        opacity_animation.setStartValue(self.windowOpacity())
        opacity_animation.setEndValue(opacity)
        group.addAnimation(geometry_animation)
        group.addAnimation(opacity_animation)
        self._current_animation = group
        group.start()

    def _edge_geometry(self, width: int) -> QRect:
        screen = self._screen_geometry()
        return QRect(screen.right() - width + 1, screen.top(), width, screen.height())

    def _screen_geometry(self) -> QRect:
        screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

    def closeEvent(self, event: Any) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        super().closeEvent(event)


def run_overlay(ipc_queue: Any | None = None) -> int:
    if QApplication is None:
        raise RuntimeError("PySide6 is required to run the overlay")
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = ARIAOverlay(ipc_queue)
    overlay.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_overlay())
