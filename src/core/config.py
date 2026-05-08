"""Configuration loading for ARIA."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration values."""

    settings_path: Path = Path("settings.json")
    log_level: str = "INFO"


def load_config(settings_path: str | Path = "settings.json") -> AppConfig:
    """Load configuration defaults for the scaffold."""
    return AppConfig(settings_path=Path(settings_path))
