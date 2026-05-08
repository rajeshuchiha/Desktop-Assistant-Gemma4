from pydantic import BaseModel
from typing import Any
import json
from pathlib import Path

class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    retried: bool = False

class ToolCall(BaseModel):
    tool: str
    params: dict

def load_capabilities() -> dict:
    settings_path = Path("settings.json")
    if settings_path.exists():
        return json.loads(settings_path.read_text())["capabilities"]
    return {}

def capability_blocked(cap: str) -> ToolResult:
    return ToolResult(
        success=False,
        error=f"CAPABILITY_DISABLED: {cap} is disabled. "
              f"Enable it in settings.json to use this feature."
    )