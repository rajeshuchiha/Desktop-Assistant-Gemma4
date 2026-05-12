import asyncio
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from src.input import stt


class FakeWhisperModel:
    def __init__(self, model_name, device):
        self.model_name = model_name
        self.device = device

    def transcribe(self, audio):
        return [SimpleNamespace(text=" hello "), SimpleNamespace(text="world")], None


class FakeInputStream:
    def __init__(self, samplerate, channels, dtype, callback):
        self.callback = callback
        self.closed = False
        self.stopped = False

    def start(self):
        self.callback(np.ones((4, 1), dtype=np.float32) * np.float32(0.25), 4, None, None)

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeListener:
    instances = []

    def __init__(self, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release
        self.stopped = threading.Event()
        FakeListener.instances.append(self)

    def start(self):
        pass

    def join(self):
        self.stopped.wait(timeout=2.0)

    def stop(self):
        self.stopped.set()


def install_fakes(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(stt, "WhisperModel", FakeWhisperModel)
    monkeypatch.setattr(stt, "sd", SimpleNamespace(InputStream=FakeInputStream))
    monkeypatch.setattr(
        stt,
        "keyboard",
        SimpleNamespace(Key=SimpleNamespace(shift_r="shift_r"), Listener=FakeListener),
    )


@pytest.mark.asyncio
async def test_transcribe_returns_string(monkeypatch):
    install_fakes(monkeypatch)
    speech = stt.SpeechInput()

    result = await speech.transcribe(b"fake wav")

    assert speech.model_name == "small.en"
    assert speech.device == "cpu"
    assert result == "hello world"


@pytest.mark.asyncio
async def test_result_queue_receives_transcription_after_recording(monkeypatch):
    install_fakes(monkeypatch)
    speech = stt.SpeechInput()
    speech._loop = asyncio.get_running_loop()

    speech._on_press(stt.keyboard.Key.shift_r)
    speech._on_release(stt.keyboard.Key.shift_r)

    result = await asyncio.wait_for(speech.result_queue.get(), timeout=2.0)
    assert result == "hello world"


def test_stop_cleans_up_thread(monkeypatch):
    install_fakes(monkeypatch)
    speech = stt.SpeechInput()

    speech.start()
    assert speech._listener_thread is not None
    assert speech._listener_thread.is_alive()

    speech.stop()

    assert speech._listener_thread.is_alive() is False
    assert FakeListener.instances[0].stopped.is_set()
