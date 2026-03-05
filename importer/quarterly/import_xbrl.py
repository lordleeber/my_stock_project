from import_common import import_xbrl_codebook, import_xbrl_period_category


XBRL_CATEGORIES = {
    "balance_sheet_xbrl": (("all.csv", "as_of"),),
    "income_statement_xbrl": (
        ("all_quarter.csv", "quarter"),
        ("all_accumulated.csv", "accumulated"),
    ),
    "cash_flow_xbrl": (("all_accumulated.csv", "accumulated"),),
}


def run(engine, config, import_category=None):
    supported_categories = tuple(XBRL_CATEGORIES.keys())
    if import_category and import_category not in supported_categories:
        return False

    imported_any = import_xbrl_codebook(engine)
    for category, file_period_types in XBRL_CATEGORIES.items():
        if import_category and import_category != category:
            continue
        imported_any |= import_xbrl_period_category(
            engine=engine,
            category=category,
            table_name=category,
            config=config,
            file_period_types=file_period_types,
            apply_etf_filter=True,
            chunksize=5000,
        )
    return imported_any
