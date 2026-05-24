"""Scan all candidates_scored.csv files and report per-cohort ml_score distribution.

Useful for deciding whether an absolute ml_score threshold is robust across
cohorts (LGBMRanker scores are not probability-calibrated, so a fixed
threshold only works if the score distribution is stable over time).

Outputs:
  - prints a table with one row per cohort (playbook_date)
  - writes scripts/output/ml_score_distribution.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "models_selection"
OUT_DIR = ROOT / "scripts" / "output"
OUT_CSV = OUT_DIR / "ml_score_distribution.csv"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top-n", type=int, default=10,
                   help="Also report mean ml_score of top-N picks per cohort")
    args = p.parse_args()

    rows = []
    for d in sorted(MODELS_ROOT.iterdir()):
        if not d.is_dir() or d.name == "latest":
            continue
        cs = d / "candidates_scored.csv"
        if not cs.exists():
            continue
        df = pd.read_csv(cs)
        if "ml_score" not in df.columns or len(df) == 0:
            continue
        s = df["ml_score"].astype(float)
        top_n_mean = float(
            df.sort_values("ml_score", ascending=False).head(args.top_n)["ml_score"].mean()
        )
        rows.append({
            "playbook_date": d.name,
            "n_candidates": int(len(s)),
            "min": float(s.min()),
            "p10": float(s.quantile(0.10)),
            "p25": float(s.quantile(0.25)),
            "median": float(s.median()),
            "p75": float(s.quantile(0.75)),
            "p90": float(s.quantile(0.90)),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "std": float(s.std(ddof=1)),
            f"top{args.top_n}_mean": top_n_mean,
        })

    df = pd.DataFrame(rows).sort_values("playbook_date").reset_index(drop=True)
    if df.empty:
        print("no candidates_scored.csv found under", MODELS_ROOT)
        return 1

    fmt = df.copy()
    for c in fmt.columns:
        if c in ("playbook_date", "n_candidates"):
            continue
        fmt[c] = fmt[c].map(lambda x: f"{x:.4f}")
    print("=== ml_score distribution per cohort ===")
    print(fmt.to_string(index=False))

    print("\n=== aggregate (across all cohorts) ===")
    agg_cols = [c for c in df.columns if c not in ("playbook_date", "n_candidates")]
    agg = df[agg_cols].agg(["mean", "std", "min", "max"]).T
    agg.columns = ["mean", "std", "min", "max"]
    print(agg.to_string(float_format=lambda x: f"{x:.4f}"))

    print("\n=== drift check (early vs recent thirds) ===")
    third = len(df) // 3
    if third >= 2:
        early = df.head(third)
        recent = df.tail(third)
        drift_rows = []
        for col in ["median", "p90", "max", f"top{args.top_n}_mean"]:
            drift_rows.append({
                "metric": col,
                "early_mean": f"{early[col].mean():.4f}",
                "recent_mean": f"{recent[col].mean():.4f}",
                "delta": f"{recent[col].mean() - early[col].mean():+.4f}",
                "delta_in_std": f"{(recent[col].mean() - early[col].mean()) / df[col].std(ddof=1):+.2f}σ",
            })
        print(pd.DataFrame(drift_rows).to_string(index=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
