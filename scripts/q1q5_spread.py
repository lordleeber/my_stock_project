"""Compute Q1-Q5 spread (per-cohort, by ml_rank) for P1 baseline and P2."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def compute(label: str, models_root: Path, fra_path: Path) -> None:
    fra = pd.read_csv(fra_path)
    fra["playbook_date"] = fra["playbook_date"].astype(str)
    fra["symbol"] = fra["symbol"].astype(str).str.zfill(4)

    rows = []
    for d in sorted(models_root.iterdir()):
        if not d.is_dir() or d.name == "latest":
            continue
        cs = d / "candidates_scored.csv"
        if not cs.exists():
            continue
        df = pd.read_csv(cs)
        df["symbol"] = df["symbol"].astype(str).str.zfill(4)
        sub = fra[fra["playbook_date"] == d.name][["symbol", "fwd_return_pct"]]
        if sub.empty:
            continue
        m = df.merge(sub, on="symbol", how="inner")
        if m.empty or "ml_rank" not in m.columns or len(m) < 50:
            continue
        m = m.sort_values("ml_rank")
        try:
            m["q"] = pd.qcut(m["ml_rank"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
        except ValueError:
            continue
        q1 = m[m["q"] == "Q1"]["fwd_return_pct"].mean()
        q5 = m[m["q"] == "Q5"]["fwd_return_pct"].mean()
        rows.append({"d": d.name, "q1": q1, "q5": q5, "spread": q1 - q5})

    df = pd.DataFrame(rows)
    print(f"--- {label} ---  n_cohorts={len(df)}")
    print(f"  Q1 mean    : {df['q1'].mean():.4f}%")
    print(f"  Q5 mean    : {df['q5'].mean():.4f}%")
    print(f"  Q1-Q5 sprd : {df['spread'].mean():.4f}pp")


def main() -> int:
    # P1 candidates_scored.csv was overwritten by P2 step5 — only P2 current state is reachable.
    # For P1 we use rolling backup feature_return_analysis.csv (cohort fwd_return identical
    # since dataset_strategy.csv schema only changed by adding anchor_ocf_ratio).
    # Q1-Q5 for P1 must come from candidates_scored.csv backups — we don't have those.
    # So just compute current state (P2) and note.
    compute(
        "P2 (current, +anchor_ocf_ratio)",
        ROOT / "models_selection",
        ROOT / "strategies" / "output" / "feature_return_analysis.csv",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
