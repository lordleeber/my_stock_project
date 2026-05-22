"""Strategies 模組共用的 date helper。

統一向 train_eps.shared_config 看齊 — CLI 一律收 `--date YYYY-MM-DD`，
語意是 **playbook run date**（cutoff +1 = 公告日的隔天）：
5/8/11 月為 16 號，其餘月份為 11 號。

兩個 date 概念差一天：
  - playbook run date = 訓練/評分實際執行那天（CLI 顯式日期、目錄名）
  - cutoff_date           = PIT 截斷日（公告日，SQL 用）

要從 CLI date 推 cutoff_date，呼叫 `cutoff_date_from_playbook`，
它等於 playbook date 減一個 calendar day（不是交易日；
daily_quotes 的查詢用 `date <= cutoff_date` 會自動退到最近交易日）。
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from train_eps.shared_config import (  # noqa: E402, F401  — re-export
    MONTH_TO_TARGET_QNUM,
    latest_playbook_date,
    parse_playbook_date,
    playbook_run_date,
)


def cutoff_date_from_playbook(playbook_date: str) -> str:
    """從 `--date YYYY-MM-DD`（playbook）推回 cutoff_date（公告日）。

    cutoff_date = playbook_date − 1 calendar day。
    例：playbook 2026-05-16 → cutoff 2026-05-15；2026-04-11 → 2026-04-10。

    輸入會先用 `parse_playbook_date` 嚴格驗證是合法 canonical playbook date，
    避免 off-cycle 日期 silent 推出錯誤的 cutoff_date。
    """
    parse_playbook_date(playbook_date)
    dt = datetime.date.fromisoformat(playbook_date)
    return (dt - datetime.timedelta(days=1)).isoformat()


def year_month_from_playbook(playbook_date: str) -> tuple[int, str]:
    """從 `--date YYYY-MM-DD` 拆出 (year, month_str) — 嚴格驗證後直接 delegate parse_playbook_date。

    回傳 month 是 zero-padded 字串 "01"~"12"，跟 step1/2/5 內部既有的 month 變數型別一致。
    """
    return parse_playbook_date(playbook_date)
