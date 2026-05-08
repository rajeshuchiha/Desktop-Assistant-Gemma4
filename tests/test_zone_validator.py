from pathlib import Path

from src.tools import zone_validator


def test_hardcoded_block_rejected():
    allowed, reason = zone_validator.is_write_allowed(Path("C:/Windows/System32/test.txt"))

    assert allowed is False
    assert "hardcoded" in reason


def test_blocked_extension_rejected(monkeypatch):
    allowed_zone = Path.cwd()
    monkeypatch.setattr(zone_validator, "_load_allowed_zones", lambda: [allowed_zone])

    allowed, reason = zone_validator.is_write_allowed(allowed_zone / "script.ps1")

    assert allowed is False
    assert "extension" in reason


def test_allowed_zone_accepted(monkeypatch):
    allowed_zone = Path.cwd()
    monkeypatch.setattr(zone_validator, "_load_allowed_zones", lambda: [allowed_zone])

    allowed, reason = zone_validator.is_write_allowed(allowed_zone / "notes.txt")

    assert (allowed, reason) == (True, "ok")


def test_path_outside_zones_rejected(monkeypatch):
    allowed_zone = Path.cwd() / "allowed"
    outside_zone = Path.cwd() / "outside"
    monkeypatch.setattr(zone_validator, "_load_allowed_zones", lambda: [allowed_zone])

    allowed, reason = zone_validator.is_write_allowed(outside_zone / "notes.txt")

    assert allowed is False
    assert "outside allowed zones" in reason


def test_existing_file_flagged_as_destructive():
    assert zone_validator.is_destructive(Path("settings.json")) is True


def test_settings_json_missing_uses_defaults(monkeypatch):
    monkeypatch.setattr(zone_validator, "SETTINGS_PATH", Path("__missing_settings__.json"))
    default_target = Path("~/Documents/aria-test.txt").expanduser()

    allowed, reason = zone_validator.is_write_allowed(default_target)

    assert (allowed, reason) == (True, "ok")
