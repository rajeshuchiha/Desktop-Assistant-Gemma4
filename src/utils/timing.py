"""Timing utilities."""

from contextlib import contextmanager
from time import perf_counter
from typing import Callable, Iterator


@contextmanager
def timer() -> Iterator[Callable[[], float]]:
    """Yield a callable that returns elapsed seconds."""
    started_at = perf_counter()
    yield lambda: perf_counter() - started_at
