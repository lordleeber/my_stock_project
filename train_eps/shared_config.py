from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"

# Playbook：每個 calendar month 訓練/預測哪一季的 EPS。
# 01 月對應上一年的 Q4（target_year 會在 target_quarter_for_playbook 內被往前推一年）；
# 其他月份對應當年的 Q1/Q2/Q3/Q4。此 dict 是兩個 step（step1 build_quarter_context、
# step4 predictions_results 寫出）共用的唯一 source of truth — 改動 playbook 只需改這裡。
MONTH_TO_TARGET_QNUM: dict[str, int] = {
    "01": 4,
    "02": 1,
    "03": 1,
    "04": 1,
    "05": 2,
    "06": 2,
    "07": 2,
    "08": 3,
    "09": 3,
    "10": 3,
    "11": 4,
    "12": 4,
}


def target_quarter_for_playbook(execution_year: int, month: str) -> tuple[int, int]:
    """根據 playbook 月份回傳 (target_year, target_qnum)。

    - January 預測上一年 Q4，因此 target_year = execution_year - 1。
    - 其他月份 target_year = execution_year。
    - target_qnum 直接取 MONTH_TO_TARGET_QNUM。
    """
    m = str(month).zfill(2)
    if m not in MONTH_TO_TARGET_QNUM:
        raise ValueError(f"Unsupported month: {m}")
    qnum = MONTH_TO_TARGET_QNUM[m]
    target_year = execution_year - 1 if m == "01" else execution_year
    return target_year, qnum


def playbook_run_date(year: int, month: str | int) -> str:
    """回傳 playbook 月份對應的 canonical 訓練執行日（YYYY-MM-DD）。

    語意：cutoff（公告日）的「**隔天**」——也就是 train_eps 實際跑訓練那天。
    cutoff 由本檔 cutoff_date_from_playbook 反推（5/8/11 月 = 15 號，其他 = 10 號）；
    這裡再 +1：5/8/11 月 = 16 號，其他月份 = 11 號。

    這跟 strategies 的 `cutoff_date` 概念不同：
      - strategies cutoff_date = PIT 資料截斷日（公告日）
      - train_eps playbook_run_date = 訓練實際執行日（公告日 +1）

    要從 cutoff_date 推 playbook_run_date，記得 +1；反之 -1。
    """
    m = str(month).zfill(2)
    if m not in MONTH_TO_TARGET_QNUM:
        raise ValueError(f"Unsupported month: {m}")
    day = 16 if m in {"05", "08", "11"} else 11
    return f"{int(year):04d}-{m}-{day:02d}"


def cutoff_date_from_playbook(playbook_date: str) -> str:
    """從 playbook run date（YYYY-MM-DD）推回 cutoff_date（公告日）。

    cutoff_date = playbook_date − 1 calendar day。
    例：playbook 2026-05-16 → cutoff 2026-05-15；2026-04-11 → 2026-04-10。

    輸入會先用 `parse_playbook_date` 嚴格驗證是合法 canonical playbook date，
    避免 off-cycle 日期 silent 推出錯誤的 cutoff_date。

    （原定義在 strategies/shared_config.py；依「playbook 日期公式唯一定義於本檔」
    規則移入，strategies 端改為 re-export，呼叫方 API 不變。）
    """
    parse_playbook_date(playbook_date)
    dt = datetime.date.fromisoformat(playbook_date)
    return (dt - datetime.timedelta(days=1)).isoformat()


def latest_playbook_date(today: datetime.date | None = None) -> str:
    """回傳 today 當下最新的 canonical playbook run date（YYYY-MM-DD）。

    語意：找出 `playbook_run_date(y, m) <= today` 的最大值。
    例如 today=2026-05-20 → 回傳 '2026-05-16'；today=2026-05-15 → 回傳 '2026-04-11'（5月還沒到 canonical）。

    這支用來讓 step1~4 / run_pipeline 在 --date 沒給時自動鎖到「最新可訓練日」。
    """
    if today is None:
        today = datetime.date.today()
    y, m = today.year, today.month
    candidate = datetime.date.fromisoformat(playbook_run_date(y, f"{m:02d}"))
    if candidate <= today:
        return candidate.isoformat()
    if m == 1:
        y, m = y - 1, 12
    else:
        m -= 1
    return playbook_run_date(y, f"{m:02d}")


def parse_playbook_date(date_str: str) -> tuple[int, str]:
    """解析 --date YYYY-MM-DD 並回傳 (year, month_str)。

    嚴格驗證該日期必須是該 (year, month) 的 canonical playbook run date；
    若使用者誤傳非正規日（例如 2026-05-15 — 那是 cutoff_date，不是 playbook 執行日），
    會直接報錯並提示正確值，避免 silent off-cycle 跑壞 walk-forward 對齊。
    """
    try:
        dt = datetime.date.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(f"--date 必須是 YYYY-MM-DD 格式，收到：{date_str!r}") from e
    year = dt.year
    month = f"{dt.month:02d}"
    expected = playbook_run_date(year, month)
    if date_str != expected:
        raise ValueError(
            f"--date {date_str} 不是 {year}/{month} 的 canonical playbook run date。"
            f" 預期：{expected}（公告日的隔天）。"
            f" 公式：5/8/11 月為 16 號，其餘月份為 11 號。"
        )
    return year, month


def shift_quarter(year: int, qnum: int, delta: int) -> tuple[int, int]:
    """把 (year, qnum) 往前/後位移 delta 季，回傳 (new_year, new_qnum)。
    qnum 範圍 1..4，跨年自動處理。delta 為負代表往過去推。
    """
    if qnum < 1 or qnum > 4:
        raise ValueError(f"qnum must be in 1..4, got {qnum}")
    total = year * 4 + (qnum - 1) + delta
    return total // 4, (total % 4) + 1


def format_quarter(year: int, qnum: int) -> str:
    """格式化成 'YYYYQX' 字串，例如 (2025, 3) → '2025Q3'。"""
    if qnum < 1 or qnum > 4:
        raise ValueError(f"qnum must be in 1..4, got {qnum}")
    return f"{year}Q{qnum}"


def _as_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid config format: '{name}' must be a mapping")
    return value


def load_shared_config() -> tuple[dict[str, dict[str, Any]], Path]:
    resolved_path = DEFAULT_CONFIG_PATH.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")

    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    root = _as_mapping(raw, "root")
    required_sections = ("common", "lightgbm-train", "lightgbm-evaluate")
    for section in required_sections:
        if section not in root:
            raise ValueError(f"Missing required config section: '{section}'")

    config = {
        section: _as_mapping(root[section], section) for section in required_sections
    }
    return config, resolved_path
