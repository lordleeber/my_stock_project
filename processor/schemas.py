import sys
import os
# 加入 common 目錄到搜尋路徑，以便在容器中引用
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import SCHEMA_COLS as COMMON_SCHEMA_COLS


def _to_processor_schema_cols(common_schema_cols):
    """Processor keeps lineage as src_* even if DB schema uses pced_*."""
    lineage_map = {
        "pced_file": "src_file",
        "pced_row": "src_row",
        "pced_col": "src_col",
    }
    out = {}
    for category, cols in common_schema_cols.items():
        out[category] = [lineage_map.get(col, col) for col in cols]
    return out


SCHEMA_COLS = _to_processor_schema_cols(COMMON_SCHEMA_COLS)
