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


def playbook_release_date(year: int, month: str | int) -> str:
    """回傳 playbook 月份對應的 canonical 公告日（YYYY-MM-DD）。

    5/8/11 月 = 季報公告月（15 號）；其他月份 = 月營收公告（10 號）。
    與 strategies/step1_prepare_data.py::model_release_date 同公式。
    """
    m = str(month).zfill(2)
    if m not in MONTH_TO_TARGET_QNUM:
        raise ValueError(f"Unsupported month: {m}")
    day = 15 if m in {"05", "08", "11"} else 10
    return f"{int(year):04d}-{m}-{day:02d}"


def parse_playbook_date(date_str: str) -> tuple[int, str]:
    """解析 --date YYYY-MM-DD 並回傳 (year, month_str)。

    嚴格驗證該日期必須是該 (year, month) 的 canonical playbook release date；
    若使用者誤傳非正規日（例如 2026-03-15），會直接報錯並提示正確值，
    避免 silent off-cycle 跑壞 walk-forward 對齊。
    """
    try:
        dt = datetime.date.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(f"--date 必須是 YYYY-MM-DD 格式，收到：{date_str!r}") from e
    year = dt.year
    month = f"{dt.month:02d}"
    expected = playbook_release_date(year, month)
    if date_str != expected:
        raise ValueError(
            f"--date {date_str} 不是 {year}/{month} 的 canonical playbook release date。"
            f" 預期：{expected}。"
            f" 公式：5/8/11 月為 15 號，其餘月份為 10 號。"
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
