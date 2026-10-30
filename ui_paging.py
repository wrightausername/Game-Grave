"""M4 bounded page windows for existing inventory records.

Pagination only affects how many rows the UI draws at once; it never
truncates the actual scan result, modifies files or grants cleanup rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")
DEFAULT_PAGE_SIZE = 160


@dataclass(frozen=True)
class PageWindow(Generic[T]):
    items: tuple[T, ...]
    page: int
    pages: int
    total: int
    start: int
    end: int

    @property
    def label(self) -> str:
        if self.total == 0:
            return "0 of 0 findings"
        return (f"{self.start + 1}–{self.end} of {self.total} findings "
                f"· page {self.page + 1}/{self.pages}")


def page_window(records: Sequence[T], requested_page: int,
                size: int = DEFAULT_PAGE_SIZE) -> PageWindow[T]:
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 2000:
        raise ValueError("Page size must be between 1 and 2000.")
    if not isinstance(requested_page, int) or isinstance(requested_page, bool):
        raise ValueError("Page index must be an integer.")
    total = len(records)
    pages = max(1, (total + size - 1) // size)
    page = min(max(0, requested_page), pages - 1)
    start = page * size
    stop = min(total, start + size)
    return PageWindow(tuple(records[start:stop]), page, pages, total, start, stop)
