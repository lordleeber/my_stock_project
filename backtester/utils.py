from __future__ import annotations

from datetime import date
from typing import Iterator


def normalize_month(month: int | str) -> str:
    """將月份整數格式化為兩位數字串，例如 3 → '03'。"""
    m = int(month)
    if m < 1 or m > 12:
        raise ValueError("month must be 1..12")
    return f"{m:02d}"


def release_day(month: int) -> int:
    """回傳策略發布日的日期數字。

    台灣財報揭露時程：
      - 5 月（Q1 財報截止）、8 月（Q2）、11 月（Q3）→ 15 日
      - 其餘月份（月營收或 Q4 推算）→ 10 日
    候選股清單在該發布日之後才能使用，進場日為發布日後第一個交易日。
    """
    # 5/8/11 月為法定財報截止月，給額外 5 天緩衝，其餘月份用 10 日
    return 15 if month in {5, 8, 11} else 10


def release_date(year: int, month: int) -> date:
    """回傳指定年月的策略發布日（date 物件）。"""
    return date(year, month, release_day(month))


def release_yyyymmdd(year: int, month: int) -> str:
    """回傳策略發布日的 YYYYMMDD 字串，供路徑或資料庫查詢使用。"""
    return release_date(year, month).strftime("%Y%m%d")


def month_iter(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> Iterator[tuple[int, int]]:
    """依序產生 [start, end] 範圍內的所有 (year, month) 組合（含頭尾）。

    用於滾動回測的月份迭代，確保不跳過跨年的月份。
    """
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        # 月份遞增，12 月滾到隔年 1 月
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
