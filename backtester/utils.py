from __future__ import annotations

from datetime import date
from typing import Iterator


def normalize_month(month: int | str) -> str:
    m = int(month)
    if m < 1 or m > 12:
        raise ValueError("month must be 1..12")
    return f"{m:02d}"


def release_day(month: int) -> int:
    return 15 if month in {5, 8, 11} else 10


def release_date(year: int, month: int) -> date:
    return date(year, month, release_day(month))


def release_yyyymmdd(year: int, month: int) -> str:
    return release_date(year, month).strftime("%Y%m%d")


def month_iter(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> Iterator[tuple[int, int]]:
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
