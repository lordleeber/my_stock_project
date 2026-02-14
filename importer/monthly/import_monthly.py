import polars as pl

from import_common import import_period_category, import_static_all_csv

MONTHLY_CATEGORIES = {"monthly_revenue", "stock_info", "stock_tags"}


def run(engine, config, import_category=None):
    if import_category and import_category not in MONTHLY_CATEGORIES:
        return False

    imported_any = False

    if not import_category or import_category == "monthly_revenue":
        imported_any |= import_period_category(
            engine=engine,
            category="monthly_revenue",
            table_name="monthly_revenue",
            config=config,
            apply_etf_filter=True,
            chunksize=2000,
        )

    if not import_category or import_category == "stock_info":
        imported_any |= import_static_all_csv(
            engine=engine,
            category="stock_info",
            table_name="stock_info",
            schema_overrides={"symbol": pl.Utf8},
        )

    if not import_category or import_category == "stock_tags":
        imported_any |= import_static_all_csv(
            engine=engine,
            category="stock_tags",
            table_name="stock_tags",
            schema_overrides={"symbol": pl.Utf8},
        )

    return imported_any
