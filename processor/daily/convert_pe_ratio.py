import os
from .convert_category_base import process_generic_category_date

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"
CATEGORY = "pe_ratio"


def process_date(
    date_str,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
    force_reprocess=FORCE_REPROCESS,
):
    process_generic_category_date(
        CATEGORY, date_str, raw_dir, processed_dir, force_reprocess
    )
