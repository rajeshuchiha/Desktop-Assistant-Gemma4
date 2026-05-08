"""Path helpers for the ARIA project."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(*parts: str) -> Path:
    """Return a path relative to the project root."""
    return PROJECT_ROOT.joinpath(*parts)
