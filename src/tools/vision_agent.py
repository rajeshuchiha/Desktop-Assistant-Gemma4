"""Read-only vision tools backed by the Gemma orchestrator."""

from __future__ import annotations

import time
from typing import Any

from PIL import Image

from src.core.orchestrator import Orchestrator
from src.core.types import ToolResult, capability_blocked, load_capabilities

import mss


_MAX_SCREEN_SIZE = (1280, 720)
_orchestrator: Orchestrator | None = None


def capture_screen(region: dict | None = None) -> Image.Image | ToolResult:
    """Capture the screen or a region and resize it to 1280x720."""
    if not load_capabilities().get("screen_read", False):
        return capability_blocked("screen_read")
    if mss is None:
        return ToolResult(success=False, error="mss is not installed")

    with mss.mss() as screen_capture:
        monitor = region or screen_capture.monitors[1]
        raw = screen_capture.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.rgb)
    return image.resize(_MAX_SCREEN_SIZE)


async def read_screen(question: str) -> ToolResult:
    """Ask the orchestrator to answer a question about the current screen."""
    started = time.perf_counter()
    if not load_capabilities().get("screen_read", False):
        return capability_blocked("screen_read")

    image = capture_screen()
    if isinstance(image, ToolResult):
        return image

    response = await _get_orchestrator().generate(question, image=image)
    return ToolResult(
        success=True,
        data=response,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


async def click_element(description: str) -> ToolResult:
    """Clicking is intentionally unavailable in the read-only version."""
    return capability_blocked("screen_click")


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
