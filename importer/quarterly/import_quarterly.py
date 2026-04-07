from import_common import import_period_category

QUARTERLY_CATEGORIES = (
    "income_statement",
    "balance_sheet",
    "cash_flow",
)


def run(engine, config, import_category=None):
    if import_category and import_category not in QUARTERLY_CATEGORIES:
        return False

    imported_any = False
    for category in QUARTERLY_CATEGORIES:
        if import_category and import_category != category:
            continue
        imported_any |= import_period_category(
            engine=engine,
            category=category,
            table_name=category,
            config=config,
            apply_etf_filter=True,
            chunksize=2000,
        )

    return imported_any
