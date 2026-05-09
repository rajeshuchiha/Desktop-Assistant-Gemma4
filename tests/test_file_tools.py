from pathlib import Path

from src.core.types import ToolResult
from src.tools import file_tools


def test_list_dir_returns_structured_entries(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": True})

    result = file_tools.list_dir("src/tools")

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert any(entry["name"] == "file_tools.py" and entry["type"] == "file" for entry in result.data)
    assert all({"name", "type", "size_bytes", "modified"} <= set(entry) for entry in result.data)


def test_read_file_returns_content_metadata(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": True})

    result = file_tools.read_file("settings.json")

    assert result.success is True
    assert result.data["encoding"] == "utf-8"
    assert result.data["size_bytes"] > 0
    assert "allowed_zones" in result.data["content"]


def test_read_file_rejects_binary_gracefully(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": True})
    binary_path = Path("benchmarks/test_binary.log")
    binary_path.write_bytes(b"abc\x00def")

    result = file_tools.read_file(str(binary_path))

    assert result.success is False
    assert result.error is not None
    assert "binary" in result.error


def test_search_files_recursive_glob(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": True})

    result = file_tools.search_files("src", "file_tools.py")

    assert result.success is True
    assert any(item["path"].endswith("file_tools.py") for item in result.data)
    assert all({"path", "size_bytes", "modified"} <= set(item) for item in result.data)


def test_get_file_info(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": True})

    result = file_tools.get_file_info("settings.json")

    assert result.success is True
    assert result.data["name"] == "settings.json"
    assert result.data["extension"] == ".json"
    assert result.data["is_binary"] is False


def test_file_read_capability_blocks_reads(monkeypatch):
    monkeypatch.setattr(file_tools, "load_capabilities", lambda: {"file_read": False})

    result = file_tools.read_file("settings.json")

    assert result.success is False
    assert result.error is not None
    assert "CAPABILITY_DISABLED: file_read" in result.error


def test_write_functions_return_file_write_blocked():
    for func, args in [
        (file_tools.write_file, ("settings.json", "content")),
        (file_tools.delete_file, ("settings.json",)),
        (file_tools.move_file, ("settings.json", "settings-copy.json")),
        (file_tools.create_dir, ("new-dir",)),
    ]:
        result = func(*args)

        assert result.success is False
        assert "CAPABILITY_DISABLED: file_write" in result.error
