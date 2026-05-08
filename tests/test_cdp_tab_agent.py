from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.types import ToolResult
from src.tools import cdp_tab_agent


class FakePage:
    def __init__(self, title, url):
        self._title = title
        self.url = url
        self.fronted = False
        self.closed = False

    async def title(self):
        return self._title

    async def bring_to_front(self):
        self.fronted = True

    async def goto(self, url):
        self.url = url

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, pages):
        self.pages = pages

    async def new_page(self):
        page = FakePage("New", "about:blank")
        self.pages.append(page)
        return page


def fake_browser():
    pages = [
        FakePage("Docs", "https://example.com/docs"),
        FakePage("Mail", "https://mail.example.com"),
    ]
    return SimpleNamespace(contexts=[FakeContext(pages)])


async def fake_connect():
    return fake_browser()


@pytest.mark.asyncio
async def test_get_open_tabs(monkeypatch):
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", fake_connect)

    result = await cdp_tab_agent.get_open_tabs()

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == [
        {"index": 0, "title": "Docs", "url": "https://example.com/docs", "active": False},
        {"index": 1, "title": "Mail", "url": "https://mail.example.com", "active": True},
    ]
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_switch_to_tab_fuzzy_matches_title_and_url(monkeypatch):
    browser = fake_browser()
    async def connect():
        return browser
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", connect)

    result = await cdp_tab_agent.switch_to_tab("mail")

    assert result.success is True
    assert result.data["index"] == 1
    assert browser.contexts[0].pages[1].fronted is True


@pytest.mark.asyncio
async def test_find_tab_by_keyword(monkeypatch):
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", fake_connect)

    result = await cdp_tab_agent.find_tab_by_keyword("docs")

    assert result.success is True
    assert result.data == [{"index": 0, "title": "Docs", "url": "https://example.com/docs"}]


@pytest.mark.asyncio
async def test_open_url_in_new_tab(monkeypatch):
    browser = fake_browser()
    async def connect():
        return browser
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", connect)

    result = await cdp_tab_agent.open_url_in_new_tab("https://open.example")

    assert result.success is True
    assert result.data["url"] == "https://open.example"
    assert len(browser.contexts[0].pages) == 3


@pytest.mark.asyncio
async def test_open_url_in_active_tab(monkeypatch):
    browser = fake_browser()
    async def connect():
        return browser
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", connect)

    result = await cdp_tab_agent.open_url_in_active_tab("https://active.example")

    assert result.success is True
    assert browser.contexts[0].pages[-1].url == "https://active.example"


@pytest.mark.asyncio
async def test_close_tab(monkeypatch):
    browser = fake_browser()
    async def connect():
        return browser
    monkeypatch.setattr(cdp_tab_agent, "_connect_browser", connect)

    result = await cdp_tab_agent.close_tab(0)

    assert result.success is True
    assert browser.contexts[0].pages[0].closed is True


@pytest.mark.asyncio
async def test_get_recent_history_uses_temp_copy(monkeypatch):
    copied = {}

    class FakeTempFile:
        name = "history-copy.sqlite"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            assert params == (2,)
            return self

        def fetchall(self):
            return [("Title", "https://example.com", 13217472000000000)]

    monkeypatch.setattr(cdp_tab_agent.tempfile, "NamedTemporaryFile", lambda **kwargs: FakeTempFile())
    monkeypatch.setattr(cdp_tab_agent.shutil, "copy2", lambda src, dst: copied.update({"src": src, "dst": dst}))
    monkeypatch.setattr(cdp_tab_agent.sqlite3, "connect", lambda path: FakeConnection())
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

    result = await cdp_tab_agent.get_recent_history(2)

    assert result.success is True
    assert copied == {"src": cdp_tab_agent.HISTORY_PATH, "dst": "history-copy.sqlite"}
    assert result.data[0]["url"] == "https://example.com"


def test_source_never_uses_browser_launch():
    source = Path("src/tools/cdp_tab_agent.py").read_text(encoding="utf-8")

    assert "chromium.launch" not in source
