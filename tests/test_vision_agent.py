from types import SimpleNamespace

import pytest
from PIL import Image

from src.core.types import ToolResult
from src.tools import vision_agent


class FakeMSS:
    monitors = [None, {"top": 0, "left": 0, "width": 2, "height": 2}]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def grab(self, monitor):
        return SimpleNamespace(size=(2, 2), rgb=b"\xff\x00\x00" * 4)


def test_capture_screen_resizes(monkeypatch):
    monkeypatch.setattr(vision_agent, "load_capabilities", lambda: {"screen_read": True})
    monkeypatch.setattr(vision_agent, "mss", SimpleNamespace(mss=lambda: FakeMSS()))

    image = vision_agent.capture_screen()

    assert isinstance(image, Image.Image)
    assert image.size == (1280, 720)


def test_capture_screen_capability_blocked(monkeypatch):
    monkeypatch.setattr(vision_agent, "load_capabilities", lambda: {"screen_read": False})

    result = vision_agent.capture_screen()

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "CAPABILITY_DISABLED: screen_read" in (result.error or "")


@pytest.mark.asyncio
async def test_read_screen_uses_orchestrator(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        async def generate(self, question, image=None):
            captured["question"] = question
            captured["image"] = image
            return "The editor is open."

    monkeypatch.setattr(vision_agent, "load_capabilities", lambda: {"screen_read": True})
    monkeypatch.setattr(vision_agent, "capture_screen", lambda: Image.new("RGB", (1280, 720)))
    monkeypatch.setattr(vision_agent, "_orchestrator", FakeOrchestrator())

    result = await vision_agent.read_screen("What is visible?")

    assert result.success is True
    assert result.data == "The editor is open."
    assert captured["question"] == "What is visible?"
    assert isinstance(captured["image"], Image.Image)


@pytest.mark.asyncio
async def test_click_element_is_blocked():
    result = await vision_agent.click_element("button")

    assert result.success is False
    assert "CAPABILITY_DISABLED: screen_click" in (result.error or "")
