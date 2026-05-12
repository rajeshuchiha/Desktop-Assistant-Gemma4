"""Push-to-talk speech input using faster-whisper on CPU."""

from __future__ import annotations

import asyncio
import io
import threading
import wave
from typing import Any

import numpy as np

import sounddevice as sd

from faster_whisper import WhisperModel

from pynput import keyboard



class SpeechInput:
    """Right-Shift push-to-talk speech input.

    The keyboard listener and audio capture live on a background thread. Whisper
    transcription runs through ``asyncio.to_thread`` so the main event loop stays
    free for orchestration.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed")
        
        self.model_name = "small.en"
        self.device = "cpu"
        self.model = WhisperModel(
                        self.model_name,
                        self.device
                    )
        self.sample_rate = sample_rate
        self.channels = channels
        self.result_queue: asyncio.Queue[str] = asyncio.Queue()

        self._loop: asyncio.AbstractEventLoop | None = None
        self._listener: Any | None = None
        self._listener_thread: threading.Thread | None = None
        self._stream: Any | None = None
        self._frames: list[Any] = []
        self._recording = False
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background Right-Shift push-to-talk listener."""
        if keyboard is None:
            raise RuntimeError("pynput is not installed")
        if sd is None:
            raise RuntimeError("sounddevice is not installed")
        if self._running:
            return

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.get_event_loop()

        self._running = True
        self._listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self._listener_thread.start()

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe WAV audio bytes without blocking the event loop."""
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes)

    def stop(self) -> None:
        """Stop recording/listening and join the listener thread."""
        self._running = False
        self._stop_recording()
        if self._listener is not None:
            self._listener.stop()
        if self._listener_thread is not None and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)

    def _run_listener(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        self._listener.join()

    def _on_press(self, key: Any) -> None:
        if key == keyboard.Key.shift_r:
            self._start_recording()

    def _on_release(self, key: Any) -> None:
        if key != keyboard.Key.shift_r:
            return
        audio_bytes = self._stop_recording()
        if audio_bytes:
            self._submit_transcription(audio_bytes)

    def _start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._recording = True

    def _stop_recording(self) -> bytes:
        with self._lock:
            if not self._recording:
                return b""
            stream = self._stream
            frames = self._frames
            self._stream = None
            self._frames = []
            self._recording = False

        if stream is not None:
            stream.stop()
            stream.close()
        return _frames_to_wav_bytes(frames, self.sample_rate)

    def _audio_callback(
        self,
        indata: Any,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        if status:
            return
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())

    def _submit_transcription(self, audio_bytes: bytes) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            text = asyncio.run(self.transcribe(audio_bytes))
            self.result_queue.put_nowait(text)
            return

        future = asyncio.run_coroutine_threadsafe(self.transcribe(audio_bytes), loop)
        future.add_done_callback(
            lambda done: loop.call_soon_threadsafe(
                self.result_queue.put_nowait,
                done.result(),
            )
        )

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        segments, _info = self.model.transcribe(io.BytesIO(audio_bytes))
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


def _frames_to_wav_bytes(frames: list[Any], sample_rate: int) -> bytes:
    if not frames:
        return b""

    audio = np.concatenate(frames, axis=0)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buffer.getvalue()
