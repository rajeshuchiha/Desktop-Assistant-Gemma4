from pathlib import Path

from src.core.types import ToolResult
from src.tools import file_tools


def test_write_blocked_outside_zones(monkeypatch):
    monkeypatch.setattr(file_tools.zone_validator, "is_write_allowed", lambda path: (False, "outside allowed zones"))

    result = file_tools.write_file("C:/outside/file.txt", "content")

    assert result.success is False
    assert result.error == "outside allowed zones"


def test_write_allowed_inside_zones(monkeypatch):
    writes = {}
    monkeypatch.setattr(file_tools.zone_validator, "is_write_allowed", lambda path: (True, "ok"))
    monkeypatch.setattr(file_tools.zone_validator, "is_destructive", lambda path: False)
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda self, content, encoding=None: writes.update({"path": str(self), "content": content, "encoding": encoding}),
    )

    result = file_tools.write_file("C:/Users/me/Documents/new.txt", "hello")

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert writes["content"] == "hello"
    assert writes["encoding"] == "utf-8"


def test_overwrite_returns_confirm_required(monkeypatch):
    monkeypatch.setattr(file_tools.zone_validator, "is_write_allowed", lambda path: (True, "ok"))
    monkeypatch.setattr(file_tools.zone_validator, "is_destructive", lambda path: True)

    result = file_tools.write_file("C:/Users/me/Documents/existing.txt", "new")

    assert result.success is False
    assert result.error.startswith("CONFIRM_REQUIRED: overwrite")


def test_delete_returns_confirm_required():
    result = file_tools.delete_file("C:/Users/me/Documents/old.txt")

    assert result.success is False
    assert result.error == "CONFIRM_REQUIRED: delete C:/Users/me/Documents/old.txt"


def test_confirm_delete_uses_send2trash(monkeypatch):
    deleted = {}
    monkeypatch.setattr(file_tools, "send2trash", lambda path: deleted.update({"path": path}))

    result = file_tools.confirm_delete("C:/Users/me/Documents/old.txt")

    assert result.success is True
    assert deleted == {"path": "C:/Users/me/Documents/old.txt"}


def test_read_works_from_any_path():
    result = file_tools.read_file("settings.json")

    assert result.success is True
    assert "allowed_zones" in result.data


def test_list_dir_returns_filenames():
    result = file_tools.list_dir("src/tools")

    assert result.success is True
    assert "file_tools.py" in result.data


def test_search_files_uses_glob():
    result = file_tools.search_files("src/tools", "*.py")

    assert result.success is True
    assert any(path.endswith("file_tools.py") for path in result.data)


def test_source_never_uses_hard_delete_calls():
    source = Path("src/tools/file_tools.py").read_text(encoding="utf-8")

    assert "os.remove" not in source
    assert "os.unlink" not in source
    assert "shutil.rmtree" not in source
