"""
SPEC: Filesystem safety gate. Every write in file_tools.py
calls this first.

HARDCODED BLOCKS (never overridable):
  C:/Windows, C:/Program Files, C:/Program Files (x86)
  extensions: .exe .dll .sys .bat .ps1 .msi .reg

INTERFACE:
  is_write_allowed(path: Path) -> tuple[bool, str]
    - resolve path to absolute before checking
    - check hardcoded blocks first
    - check blocked extensions
    - check allowed_zones from settings.json
      default zones: ~/Documents, ~/Downloads, ~/Desktop
    - return (False, reason) or (True, "ok")

  is_destructive(path: Path) -> bool
    - returns True if path exists (overwrite = destructive)

SETTINGS: reads allowed_zones list from settings.json
DO NOT: allow any override of hardcoded blocks
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.types import ToolResult


HARDCODED_BLOCKED_PATHS = (
    Path("C:/Windows"),
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
)
BLOCKED_EXTENSIONS = {".exe", ".dll", ".sys", ".bat", ".ps1", ".msi", ".reg"}
SETTINGS_PATH = Path("settings.json")
DEFAULT_ALLOWED_ZONES = ("~/Documents", "~/Downloads", "~/Desktop")


def is_write_allowed(path: Path) -> tuple[bool, str]:
    """Return whether a write target is inside an allowed zone."""
    resolved_path = _resolve(path)

    for blocked_path in HARDCODED_BLOCKED_PATHS:
        blocked_resolved = _resolve(blocked_path)
        if _is_inside(resolved_path, blocked_resolved):
            return False, f"blocked hardcoded path: {blocked_path}"

    if resolved_path.suffix.lower() in BLOCKED_EXTENSIONS:
        return False, f"blocked extension: {resolved_path.suffix.lower()}"

    for zone in _load_allowed_zones():
        if _is_inside(resolved_path, zone):
            return True, "ok"

    return False, f"path outside allowed zones: {resolved_path}"


def is_destructive(path: Path) -> bool:
    """Existing paths are destructive because writes would overwrite them."""
    return path.exists()


def _load_allowed_zones() -> list[Path]:
    settings_path = SETTINGS_PATH
    zones = list(DEFAULT_ALLOWED_ZONES)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = {}
        configured_zones = settings.get("allowed_zones")
        if isinstance(configured_zones, list):
            zones = [zone for zone in configured_zones if isinstance(zone, str)]

    return [_resolve(Path(zone).expanduser()) for zone in zones]


def _resolve(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_inside(path: Path, zone: Path) -> bool:
    path_text = str(path).casefold()
    zone_text = str(zone).rstrip("\\/").casefold()
    return path_text == zone_text or path_text.startswith(zone_text + "\\") or path_text.startswith(zone_text + "/")
