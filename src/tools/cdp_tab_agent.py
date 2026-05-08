"""Chrome DevTools Protocol tab automation tools."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from difflib import SequenceMatcher

from src.core.types import ToolResult


HISTORY_PATH = Path("~/AppData/Local/Google/Chrome/User Data/Default/History").expanduser()


async def get_open_tabs() -> ToolResult:
    started = time.perf_counter()
    try:
        browser = await _connect_browser()
        pages = _pages(browser)
        data = [
            {"index": index, "title": await page.title(), "url": page.url, "active": index == len(pages) - 1}
            for index, page in enumerate(pages)
        ]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def switch_to_tab(keyword: str) -> ToolResult:
    started = time.perf_counter()
    try:
        match = await _find_best_page(keyword)
        if match is None:
            return _result(started, False, error=f"tab not found: {keyword}")
        index, page = match
        await page.bring_to_front()
        return _result(started, True, data={"index": index, "title": await page.title(), "url": page.url})
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def find_tab_by_keyword(query: str) -> ToolResult:
    started = time.perf_counter()
    try:
        browser = await _connect_browser()
        matches = []
        for index, page in enumerate(_pages(browser)):
            title = await page.title()
            if _score(query, title, page.url) > 0:
                matches.append({"index": index, "title": title, "url": page.url})
        return _result(started, True, data=matches)
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def open_url_in_new_tab(url: str) -> ToolResult:
    started = time.perf_counter()
    try:
        browser = await _connect_browser()
        context = _context(browser)
        page = await context.new_page()
        await page.goto(url)
        return _result(started, True, data={"title": await page.title(), "url": page.url})
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def open_url_in_active_tab(url: str) -> ToolResult:
    started = time.perf_counter()
    try:
        browser = await _connect_browser()
        pages = _pages(browser)
        if not pages:
            return _result(started, False, error="no open tabs")
        page = pages[-1]
        await page.goto(url)
        return _result(started, True, data={"title": await page.title(), "url": page.url})
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def close_tab(index: int) -> ToolResult:
    started = time.perf_counter()
    try:
        browser = await _connect_browser()
        pages = _pages(browser)
        if index < 0 or index >= len(pages):
            return _result(started, False, error=f"tab index out of range: {index}")
        await pages[index].close()
        return _result(started, True, data={"index": index})
    except Exception as exc:
        return _result(started, False, error=str(exc))


async def get_recent_history(n: int) -> ToolResult:
    started = time.perf_counter()
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as temp_file:
            temp_path = temp_file.name
        shutil.copy2(HISTORY_PATH, temp_path)
        with sqlite3.connect(temp_path) as connection:
            rows = connection.execute(
                """
                SELECT urls.title, urls.url, visits.visit_time
                FROM visits
                JOIN urls ON urls.id = visits.url
                ORDER BY visits.visit_time DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
        data = [
            {"title": title, "url": url, "visit_time": _chrome_time_to_iso(visit_time)}
            for title, url, visit_time in rows
        ]
        return _result(started, True, data=data)
    except Exception as exc:
        return _result(started, False, error=str(exc))
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


async def _connect_browser():
    from playwright.async_api import async_playwright

    port = os.getenv("CHROME_DEBUG_PORT") or _env_file_value("CHROME_DEBUG_PORT") or "9222"
    playwright = await async_playwright().start()
    return await playwright.chromium.connect_over_cdp(f"http://localhost:{port}")


def _context(browser):
    if not browser.contexts:
        raise RuntimeError("no Chrome contexts available")
    return browser.contexts[0]


def _pages(browser):
    return list(_context(browser).pages)


async def _find_best_page(query: str):
    browser = await _connect_browser()
    best_match = None
    best_score = 0.0
    for index, page in enumerate(_pages(browser)):
        score = _score(query, await page.title(), page.url)
        if score > best_score:
            best_score = score
            best_match = (index, page)
    return best_match if best_score > 0 else None


def _score(query: str, title: str, url: str) -> float:
    needle = query.casefold().strip()
    haystack = f"{title} {url}".casefold()
    if not needle:
        return 0.0
    if needle in haystack:
        return 1.0
    return SequenceMatcher(None, needle, haystack).ratio() if SequenceMatcher(None, needle, haystack).ratio() >= 0.45 else 0.0


def _chrome_time_to_iso(value: int) -> str:
    chrome_epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return (chrome_epoch + timedelta(microseconds=value)).isoformat()


def _env_file_value(key: str) -> str | None:
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.strip()
    return None


def _result(started: float, success: bool, data=None, error: str | None = None) -> ToolResult:
    return ToolResult(
        success=success,
        data=data,
        error=error,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
