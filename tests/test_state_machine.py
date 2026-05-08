import pytest

from src.overlay.state_machine import OverlayFSM, State


@pytest.mark.parametrize(
    ("start_state", "event", "expected_state"),
    [
        (State.HIDDEN, "mouse_near", State.PEEK),
        (State.PEEK, "hover", State.ACTIVE),
        (State.PEEK, "hotkey", State.ACTIVE),
        (State.ACTIVE, "push_to_talk", State.LISTENING),
        (State.ACTIVE, "task_start", State.WORKING),
        (State.WORKING, "task_complete", State.RESULT),
        (State.RESULT, "timeout", State.HIDDEN),
        (State.RESULT, "dismiss", State.HIDDEN),
    ],
)
def test_valid_transitions(start_state, event, expected_state):
    fsm = OverlayFSM()
    fsm.current_state = start_state

    assert fsm.transition(event) == expected_state
    assert fsm.current_state == expected_state


@pytest.mark.parametrize("start_state", list(State))
def test_inactivity_always_transitions_to_hidden(start_state):
    fsm = OverlayFSM()
    fsm.current_state = start_state

    assert fsm.transition("inactivity") == State.HIDDEN


def test_invalid_transition_raises_value_error():
    fsm = OverlayFSM()

    with pytest.raises(ValueError):
        fsm.transition("task_complete")


def test_queue_put_get_works_correctly():
    fsm = OverlayFSM()
    message = {"type": "status", "data": {"state": "ready"}}

    fsm.message_queue.put(message)

    assert fsm.receive_message(timeout=1.0) == message


def test_send_message_uses_ipc_message_format():
    fsm = OverlayFSM()

    fsm.send_message("result", {"text": "done"})

    assert fsm.receive_message(timeout=1.0) == {"type": "result", "data": {"text": "done"}}
