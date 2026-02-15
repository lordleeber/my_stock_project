import polars as pl
from import_common import (
    import_daily_all_category,
    import_daily_market_category,
)

DAILY_MARKET_CATEGORIES = (
    "daily_quotes",
    "market_indices",
    "institutional_investors",
    "foreign_holding",
    "margin_trading",
    "margin_sbl",
    "pe_ratio",
)

DAILY_ALL_CATEGORIES = (
    "institutional_summary",
    "margin_summary",
)

DAILY_CATEGORIES = set(DAILY_MARKET_CATEGORIES + DAILY_ALL_CATEGORIES)


def run(engine, config, import_category=None):
    if import_category and import_category not in DAILY_CATEGORIES:
        return False

    imported_any = False
    # 強制指定 symbol 為字串型態，避免資料庫自動推斷為 bigint
    daily_schema_overrides = {"symbol": pl.Utf8}

    for category in DAILY_MARKET_CATEGORIES:
        if import_category and import_category != category:
            continue
        imported_any |= import_daily_market_category(
            engine=engine,
            category=category,
            table_name=category,
            config=config,
            schema_overrides=daily_schema_overrides,
        )

    for category in DAILY_ALL_CATEGORIES:
        if import_category and import_category != category:
            continue
        imported_any |= import_daily_all_category(
            engine=engine,
            category=category,
            table_name=category,
            config=config,
            apply_etf_filter=False,
        )

    return imported_any
