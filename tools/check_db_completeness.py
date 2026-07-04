#!/usr/bin/env python3
"""檢查最近 N 個交易日的 DB 完整性（每日表 + calculator 衍生表）。

設計重點：以 daily_quotes 實際存在的「最近 N 個 distinct 日期」為錨點，
非交易日（週末、端午等國定假日）自然被排除 —— 我們只斷言「有開盤的那幾天，
每張表是否都進了資料」，不靠寫死的交易日曆。

對齊關係：核心每日表清單 + 「零列即缺漏」規則，與 schedules/daily_retry.sh
的第三層 DB 檢查同口徑。**若在此處增減每日表，請同步改 daily_retry.sh**
（兩份來源，需手動保持一致）。

執行（host venv，經 common/db.py 打 localhost:5419）：
    venv/bin/python3 tools/check_db_completeness.py
    venv/bin/python3 tools/check_db_completeness.py --days 20
    venv/bin/python3 tools/check_db_completeness.py --strict     # 有 warning 也回非零

Exit code：0 = 齊全；1 = 有缺漏（或 --strict 下有 warning）；2 = 查詢/連線錯誤。
"""

import argparse
import statistics
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# 直接以 `venv/bin/python3 tools/check_db_completeness.py` 執行時，sys.path[0]
# 是 tools/，repo root 不在 path 上 —— 補進去才 import 得到 common（與 train_eps 同 pattern）。
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url  # noqa: E402  (sys.path 補完後才能 import)

# 市場分流的每日表：每個 (date, market) 都必須有列。
# 與 schedules/daily_retry.sh 的 DB 檢查清單保持一致。
MARKET_TABLES = [
    "daily_quotes",
    "institutional_investors",
    "foreign_holding",
    "margin_trading",
    "margin_sbl",
    "pe_ratio",
    "institutional_summary",
    "margin_summary",
]
MARKETS = ["sii", "otc"]

# calculator 衍生的每日表（不分市場）：每個 date 都必須有列。
CALC_TABLES = [
    "technical_indicators",
    "valuation_daily",
    "trust_holding",
    "dealer_holding",
    "market_indices",
]

# 週更 / 本來就會落後的表：只報最新日期當參考，永遠不以「逐日缺漏」判 fail。
LAGGING_TABLES = [
    ("shareholding_concentration", "TDCC 週更，預期落後"),
]


def fetch_all(engine, sql, **params):
    """每次開短連線執行，避免單一語句失敗汙染交易（例如表不存在）。"""
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def window_dates(engine, days):
    """以 daily_quotes 最近 N 個 distinct 日期為基準，回傳 (start_date, [dates])。

    再取所有受檢表在 >= start_date 範圍內的 distinct 日期 union，
    這樣「某天 daily_quotes 缺但其他表有（或反之）」也會被攤出來檢查。
    """
    rows = fetch_all(
        engine,
        "SELECT DISTINCT date FROM daily_quotes ORDER BY date DESC LIMIT :days",
        days=days,
    )
    if not rows:
        return None, []
    start = min(r[0] for r in rows)

    union_parts = [
        f"SELECT date FROM {t} WHERE date >= :start"
        for t in MARKET_TABLES + CALC_TABLES
    ]
    union_sql = (
        "SELECT DISTINCT date FROM (\n  "
        + "\n  UNION ".join(union_parts)
        + "\n) u ORDER BY date"
    )
    dates = [r[0] for r in fetch_all(engine, union_sql, start=start)]
    return start, dates


def collect_counts(engine, start):
    """回傳 (market_counts, calc_counts, errors)。

    market_counts[(table, date, market)] = n
    calc_counts[(table, date)] = n
    errors: list[(table, message)] —— 表不存在等查詢失敗
    """
    market_counts = {}
    calc_counts = {}
    errors = []

    for tbl in MARKET_TABLES:
        try:
            rows = fetch_all(
                engine,
                f"SELECT date, lower(market) AS mkt, count(*) "
                f"FROM {tbl} WHERE date >= :start GROUP BY date, lower(market)",
                start=start,
            )
            for d, mkt, n in rows:
                market_counts[(tbl, d, mkt)] = n
        except SQLAlchemyError as e:
            errors.append((tbl, str(e.__cause__ or e).splitlines()[0]))

    for tbl in CALC_TABLES:
        try:
            rows = fetch_all(
                engine,
                f"SELECT date, count(*) FROM {tbl} WHERE date >= :start GROUP BY date",
                start=start,
            )
            for d, n in rows:
                calc_counts[(tbl, d)] = n
        except SQLAlchemyError as e:
            errors.append((tbl, str(e.__cause__ or e).splitlines()[0]))

    return market_counts, calc_counts, errors


def main():
    parser = argparse.ArgumentParser(
        description="檢查最近 N 個交易日的 DB 資料完整性。"
    )
    parser.add_argument(
        "--days", type=int, default=10, help="檢查最近幾個交易日（預設 10）"
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=0.5,
        help="某日列數 < 該 cell 中位數 * ratio 時發 WARN（預設 0.5）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="有 WARN 也回非零 exit code（給告警用）",
    )
    args = parser.parse_args()

    try:
        engine = create_engine(get_db_url())
        start, dates = window_dates(engine, args.days)
    except SQLAlchemyError as e:
        print(f"ERROR: 無法連線 / 查詢 DB：{e}", file=sys.stderr)
        return 2

    if not dates:
        print("ERROR: daily_quotes 沒有任何資料，無法判斷檢查窗口。", file=sys.stderr)
        return 2

    market_counts, calc_counts, errors = collect_counts(engine, start)

    missing = []  # (date, "table/market")
    warnings = []  # (date, label, n, median)

    # 市場分流表
    for tbl in MARKET_TABLES:
        for mkt in MARKETS:
            series = [market_counts.get((tbl, d, mkt), 0) for d in dates]
            med = statistics.median(series) if series else 0
            for d, n in zip(dates, series):
                label = f"{tbl}/{mkt}"
                if n == 0:
                    missing.append((d, label))
                elif med > 0 and n < args.min_ratio * med:
                    warnings.append((d, label, n, med))

    # calculator 衍生表
    for tbl in CALC_TABLES:
        series = [calc_counts.get((tbl, d), 0) for d in dates]
        med = statistics.median(series) if series else 0
        for d, n in zip(dates, series):
            if n == 0:
                missing.append((d, tbl))
            elif med > 0 and n < args.min_ratio * med:
                warnings.append((d, tbl, n, med))

    # ---- 輸出 ----
    print(f"DB completeness check — {len(dates)} 個交易日：{dates[0]} → {dates[-1]}")
    print("(以 daily_quotes distinct 日期為錨點，非交易日自動排除)\n")

    missing_by_date = {}
    for d, label in missing:
        missing_by_date.setdefault(d, []).append(label)

    print("逐日狀態：")
    for d in dates:
        if d in missing_by_date:
            print(f"  {d}  ✗ 缺：{', '.join(sorted(missing_by_date[d]))}")
        else:
            print(f"  {d}  ✓ OK")

    print("\n各表列數（窗口內 min / median / max）：")
    for tbl in MARKET_TABLES:
        cells = []
        for mkt in MARKETS:
            series = [market_counts.get((tbl, d, mkt), 0) for d in dates]
            cells.append(
                f"{mkt} {min(series)}/{int(statistics.median(series))}/{max(series)}"
            )
        print(f"  [market] {tbl:<24} {'   '.join(cells)}")
    for tbl in CALC_TABLES:
        series = [calc_counts.get((tbl, d), 0) for d in dates]
        print(
            f"  [calc]   {tbl:<24} "
            f"{min(series)}/{int(statistics.median(series))}/{max(series)}"
        )

    # 落後表：只報最新日期
    print("\n落後表（僅供參考，不計入 fail）：")
    for tbl, note in LAGGING_TABLES:
        try:
            row = fetch_all(engine, f"SELECT max(date) FROM {tbl}")
            latest = row[0][0] if row else None
        except SQLAlchemyError:
            latest = "ERROR"
        print(f"  {tbl:<28} latest={latest}  ({note})")

    if warnings:
        print(f"\n⚠ 列數偏低 WARN（{len(warnings)}）：")
        for d, label, n, med in sorted(warnings):
            print(f"  {d}  {label}  n={n} (median={int(med)})")

    if errors:
        print(f"\n❗ 表查詢失敗（{len(errors)}）：")
        for tbl, msg in errors:
            print(f"  {tbl}: {msg}")

    print()
    if missing or errors:
        print(f"RESULT: FAIL — 缺 {len(missing)} 個 cell、{len(errors)} 個表查詢失敗。")
        return 1
    if warnings and args.strict:
        print(f"RESULT: FAIL(strict) — {len(warnings)} 個列數偏低 WARN。")
        return 1
    tail = f"，但有 {len(warnings)} 個 WARN。" if warnings else "。"
    print(f"RESULT: PASS — 所有 (date × table × market) cell 皆有資料{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
