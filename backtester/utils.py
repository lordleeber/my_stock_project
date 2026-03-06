from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
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


def month_iter(start_year: int, start_month: int, end_year: int, end_month: int) -> Iterator[tuple[int, int]]:
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def resolve_candidates_path(base_dir: Path, year: int, month: int) -> Path:
    ymd = release_yyyymmdd(year, month)
    return (
        base_dir
        / f"{year:04d}"
        / normalize_month(month)
        / "results_candidates"
        / f"trade_candidates_{ymd}.csv"
    )


def resolve_best_strategy_path(base_dir: Path, year: int, month: int) -> Path:
    return base_dir / f"{year:04d}" / normalize_month(month) / "results_optimize" / "best_strategy.json"


def output_dir(base_dir: Path, year: int, month: int) -> Path:
    return base_dir / f"{year:04d}" / normalize_month(month)


@dataclass
class ParsedStrategy:
    raw: dict
    strategy_name: str
    entry_rule: dict
    take_profit_rule: dict
    exit_rule: dict


def parse_strategy_json(path: Path) -> ParsedStrategy:
    if not path.exists():
        raise FileNotFoundError(f"best_strategy not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    entry_rule = raw.get("entry_rule", {})
    take_profit_rule = raw.get("take_profit_rule", {})
    exit_rule = raw.get("exit_rule", {})

    if isinstance(entry_rule, str):
        entry_rule = json.loads(entry_rule)
    if isinstance(take_profit_rule, str):
        take_profit_rule = json.loads(take_profit_rule)
    if isinstance(exit_rule, str):
        exit_rule = json.loads(exit_rule)

    return ParsedStrategy(
        raw=raw,
        strategy_name=str(raw.get("strategy_name", "unknown_strategy")),
        entry_rule=entry_rule,
        take_profit_rule=take_profit_rule,
        exit_rule=exit_rule,
    )
