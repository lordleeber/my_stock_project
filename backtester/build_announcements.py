import argparse
import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build announcements.csv from trade_candidates.csv and best_strategy.json")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    return parser.parse_args()


def month_dates(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def parse_entry_rule(best_cfg: dict) -> dict:
    raw = best_cfg.get("entry_rule", {})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"type": "all"}
        except json.JSONDecodeError:
            return {"type": "all"}
    return {"type": "all"}


def load_quotes(quotes_path: Path) -> pd.DataFrame:
    q = pd.read_csv(quotes_path)
    q["symbol"] = q["symbol"].astype(str).str.strip()
    q["date"] = pd.to_datetime(q["date"], errors="coerce")
    q["open"] = pd.to_numeric(q.get("open"), errors="coerce")
    q = q.dropna(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    return q


def build_next_open_map(quotes: pd.DataFrame) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for symbol, g in quotes.groupby("symbol", sort=False):
        dates = g["date"].tolist()
        opens = g["open"].tolist()
        for i in range(len(g) - 1):
            key = (str(symbol), pd.Timestamp(dates[i]).strftime("%Y-%m-%d"))
            out[key] = float(opens[i + 1]) if pd.notna(opens[i + 1]) else np.nan
    return out


def decide_action(entry_rule: dict, close_ref: float, target_price: float, next_open: float) -> tuple[str, str]:
    rule_type = str(entry_rule.get("type", "all")).strip().lower()
    ratio = float(entry_rule.get("ratio", 1.0)) if "ratio" in entry_rule else 1.0

    if rule_type == "all":
        return "buy", "entry_all"

    if np.isnan(next_open):
        return "watch", "no_next_open"

    if rule_type == "target_above_entry_ratio":
        if np.isnan(target_price):
            return "watch", "no_target_price"
        ok = target_price >= next_open * ratio
        return ("buy", f"target_ge_open_x_{ratio:.2f}") if ok else ("watch", f"target_lt_open_x_{ratio:.2f}")

    if rule_type == "pullback_from_ref_close":
        if np.isnan(close_ref):
            return "watch", "no_ref_close"
        ok = next_open <= close_ref * ratio
        return ("buy", f"open_le_refclose_x_{ratio:.2f}") if ok else ("watch", f"open_gt_refclose_x_{ratio:.2f}")

    return "buy", "entry_rule_unknown_default_buy"


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = int(args.month)
    month_s = f"{month:02d}"
    _, end_date = month_dates(year, month)
    end_dd = end_date[-2:]

    base_dir = Path.cwd()
    candidates_path = (base_dir / "strategies" / market / f"{year:04d}" / month_s / "trade_candidates.csv").resolve()
    best_path = (base_dir / "strategies" / market / f"{year:04d}" / month_s / "best_strategy.json").resolve()
    quotes_path = (
        base_dir
        / "strategies"
        / market
        / f"{year:04d}"
        / month_s
        / f"daily_quotes_{year:04d}{month_s}01_{year:04d}{month_s}{end_dd}_{market}.csv"
    ).resolve()
    output_path = (base_dir / "backtester" / market / f"{year:04d}" / month_s / "announcements.csv").resolve()

    if not candidates_path.exists():
        raise FileNotFoundError(f"trade_candidates not found: {candidates_path}")
    if not best_path.exists():
        raise FileNotFoundError(f"best_strategy not found: {best_path}")
    if not quotes_path.exists():
        raise FileNotFoundError(f"quotes cache not found: {quotes_path}")

    best_cfg = json.loads(best_path.read_text(encoding="utf-8"))
    entry_rule = parse_entry_rule(best_cfg)

    df = pd.read_csv(candidates_path)
    if "symbol" not in df.columns:
        raise ValueError("trade_candidates.csv must contain symbol")

    if "feature_cutoff_date" in df.columns:
        announce_date = pd.to_datetime(df["feature_cutoff_date"], errors="coerce")
    elif "date" in df.columns:
        announce_date = pd.to_datetime(df["date"], errors="coerce")
    else:
        raise ValueError("trade_candidates.csv must contain feature_cutoff_date or date")

    close_ref = pd.to_numeric(df.get("close"), errors="coerce")
    target_price = pd.to_numeric(df.get("predict_target_price"), errors="coerce")
    score = np.where((~close_ref.isna()) & (close_ref > 0), (target_price / close_ref) - 1.0, np.nan)

    quotes = load_quotes(quotes_path)
    next_open_map = build_next_open_map(quotes)

    symbols = df["symbol"].astype(str).str.strip()
    announce_str = announce_date.dt.strftime("%Y-%m-%d")

    next_open_vals = []
    actions = []
    reasons = []
    for i in range(len(df)):
        sym = symbols.iloc[i]
        ann = announce_str.iloc[i]
        nxt_open = float(next_open_map.get((sym, ann), np.nan))
        act, reason = decide_action(
            entry_rule=entry_rule,
            close_ref=float(close_ref.iloc[i]) if pd.notna(close_ref.iloc[i]) else np.nan,
            target_price=float(target_price.iloc[i]) if pd.notna(target_price.iloc[i]) else np.nan,
            next_open=nxt_open,
        )
        next_open_vals.append(nxt_open)
        actions.append(act)
        reasons.append(reason)

    out = pd.DataFrame(
        {
            "symbol": symbols,
            "announce_date": announce_str,
            "model_action": actions,
            "score": score,
            "entry_open_next_day": next_open_vals,
            "entry_reason": reasons,
        }
    )
    out = out.dropna(subset=["symbol", "announce_date"]).copy()
    out["score"] = pd.to_numeric(out["score"], errors="coerce").fillna(0.0).round(6)
    out["entry_open_next_day"] = pd.to_numeric(out["entry_open_next_day"], errors="coerce").round(4)
    out = out.sort_values(["symbol", "announce_date"]).drop_duplicates(subset=["symbol", "announce_date"], keep="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    buy_count = int((out["model_action"] == "buy").sum())
    watch_count = int((out["model_action"] == "watch").sum())

    print("build_announcements done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month_s}")
    print(f"- candidates: {candidates_path}")
    print(f"- best_strategy: {best_path}")
    print(f"- quotes: {quotes_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")
    print(f"- buy: {buy_count}")
    print(f"- watch: {watch_count}")


if __name__ == "__main__":
    main()
