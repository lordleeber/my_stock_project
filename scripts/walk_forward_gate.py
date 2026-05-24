"""Walk-forward gate experiment using score_p90 as the regime signal.

Post-processes the existing top_n=10 rolling_trades.csv — no backtester re-run.
For each cohort, computes the walk-forward percentile rank of its score_p90
against ALL prior cohorts. If rank < threshold P, the gate fails:
  - skip variant   : that cohort contributes 0% return (sits in cash)
  - reduce variant : that cohort is filtered to ml_rank <= 5 (deploys top-5 only)

Baseline is the existing top_n=10 run (no gating). Sanity check: applying
"reduce to top-5" to ALL cohorts should reproduce the top_n=5 run.

Reports Sharpe / total PnL / monthly stability over the 46-cohort series and
writes scripts/output/walk_forward_gate.csv.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "models_selection"
SWEEP_ROOT = ROOT / "backtester" / "output" / "sweep_top_n"
SCORE_DIST_CSV = ROOT / "scripts" / "output" / "ml_score_distribution.csv"
OUT_DIR = ROOT / "scripts" / "output"
OUT_CSV = OUT_DIR / "walk_forward_gate.csv"

POSITION_AMOUNT = 100_000.0


def load_ranks() -> pd.DataFrame:
    frames = []
    for d in sorted(MODELS_ROOT.iterdir()):
        if not d.is_dir() or d.name == "latest":
            continue
        cs = d / "candidates_scored.csv"
        if not cs.exists():
            continue
        df = pd.read_csv(cs, usecols=["symbol", "ml_rank", "ml_score"])
        df["symbol"] = df["symbol"].astype(str).str.zfill(4)
        df["playbook_date"] = d.name
        df["ym"] = d.name[:7]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def annotate_trades(trades_csv: Path, ranks: pd.DataFrame) -> pd.DataFrame:
    trades = pd.read_csv(trades_csv)
    # only include closed trades (need net_pnl for return calc)
    trades = trades.dropna(subset=["exit_date", "net_pnl"]).copy()
    trades["symbol"] = trades["symbol"].astype(str).str.zfill(4)
    trades["ym"] = trades["entry_date"].astype(str).str[:7]
    rank_lookup = ranks[["ym", "symbol", "ml_rank", "ml_score", "playbook_date"]]
    trades = trades.merge(rank_lookup, on=["ym", "symbol"], how="left")
    miss = trades["ml_rank"].isna().sum()
    if miss > 0:
        print(f"[warn] {miss} trades have no ml_rank match (will be dropped)")
        trades = trades.dropna(subset=["ml_rank"])
    trades["ml_rank"] = trades["ml_rank"].astype(int)
    return trades


def walk_forward_percentile_rank(series: pd.Series) -> pd.Series:
    """For each index i, fraction of values at indices 0..i-1 that are <= series[i]."""
    out = []
    arr = series.to_numpy()
    for i in range(len(arr)):
        if i == 0:
            out.append(np.nan)
        else:
            prior = arr[:i]
            out.append(float(np.mean(prior <= arr[i])))
    return pd.Series(out, index=series.index)


def cohort_returns(
    trades: pd.DataFrame,
    cohort_order: list[str],
    gate_fail: dict[str, str],  # ym -> "skip" | "reduce" | "pass"
    position_amount: float,
) -> pd.DataFrame:
    rows = []
    for ym in cohort_order:
        action = gate_fail.get(ym, "pass")
        sub = trades[trades["ym"] == ym]
        if action == "skip":
            rows.append({
                "ym": ym, "action": "skip",
                "n_positions": 0,
                "capital": 0.0,
                "net_pnl": 0.0,
                "return_pct": 0.0,
            })
            continue
        if action == "reduce":
            sub = sub[sub["ml_rank"] <= 5]
        n = len(sub)
        capital = n * position_amount
        net = float(sub["net_pnl"].sum()) if n > 0 else 0.0
        ret = (net / capital * 100) if capital > 0 else 0.0
        rows.append({
            "ym": ym, "action": action,
            "n_positions": n,
            "capital": capital,
            "net_pnl": net,
            "return_pct": ret,
        })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, label: str) -> dict:
    rets = df["return_pct"].astype(float)
    mean = rets.mean()
    std = rets.std(ddof=1)
    sharpe = (mean / std) * math.sqrt(12) if std and std > 0 else float("nan")
    cum = df["net_pnl"].cumsum()
    peak = cum.cummax()
    max_dd = float((cum - peak).min())
    skipped = (df["action"] == "skip").sum()
    reduced = (df["action"] == "reduce").sum()
    return {
        "scenario": label,
        "n_cohorts": int(len(df)),
        "skipped": int(skipped),
        "reduced": int(reduced),
        "total_pnl": float(df["net_pnl"].sum()),
        "mean_monthly_ret_pct": float(mean),
        "std_monthly_ret_pct": float(std),
        "sharpe_annual": float(sharpe),
        "positive_months_pct": float((rets > 0).mean()),
        "worst_month_ret_pct": float(rets.min()),
        "max_dd_pnl": max_dd,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--trades-csv",
        default=str(SWEEP_ROOT / "top_10" / "rolling_trades.csv"),
    )
    p.add_argument(
        "--score-dist-csv",
        default=str(SCORE_DIST_CSV),
    )
    p.add_argument(
        "--percentile-thresholds",
        type=float, nargs="+", default=[0.10, 0.20, 0.30],
        help="Gate fails when wf percentile rank of score_p90 < threshold",
    )
    p.add_argument(
        "--warmup-cohorts", type=int, default=6,
        help="No gating applied until at least this many prior cohorts exist",
    )
    args = p.parse_args()

    ranks = load_ranks()
    trades = annotate_trades(Path(args.trades_csv), ranks)

    score_dist = pd.read_csv(args.score_dist_csv).sort_values("playbook_date").reset_index(drop=True)
    score_dist["ym"] = score_dist["playbook_date"].str[:7]
    score_dist["p90_wf_pct"] = walk_forward_percentile_rank(score_dist["p90"])

    # restrict to cohorts that actually have closed trades
    traded_yms = sorted(trades["ym"].unique())
    score_dist = score_dist[score_dist["ym"].isin(traded_yms)].reset_index(drop=True)
    cohort_order = score_dist["ym"].tolist()

    print(f"=== walk-forward gate (n={len(cohort_order)} cohorts) ===")
    print(f"score_p90 range: {score_dist['p90'].min():.3f} → {score_dist['p90'].max():.3f}")

    scenarios = []

    # Baseline: no gate, top_10
    baseline = cohort_returns(trades, cohort_order, gate_fail={}, position_amount=POSITION_AMOUNT)
    scenarios.append(summarize(baseline, "baseline_top10"))

    # Sanity: reduce ALL cohorts to top 5 (should match top_n=5 run)
    all_reduce = cohort_returns(
        trades, cohort_order,
        gate_fail={ym: "reduce" for ym in cohort_order},
        position_amount=POSITION_AMOUNT,
    )
    scenarios.append(summarize(all_reduce, "sanity_all_reduce_to_top5"))

    # Gated variants
    for thr in args.percentile_thresholds:
        for action in ("skip", "reduce"):
            gate = {}
            for _, r in score_dist.iterrows():
                ym = r["ym"]
                wf = r["p90_wf_pct"]
                idx = cohort_order.index(ym)
                if idx < args.warmup_cohorts:
                    continue
                if pd.notna(wf) and wf < thr:
                    gate[ym] = action
            df = cohort_returns(trades, cohort_order, gate_fail=gate, position_amount=POSITION_AMOUNT)
            scenarios.append(summarize(df, f"{action}_p90<{int(thr*100)}p"))

    out = pd.DataFrame(scenarios)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    fmt = out.copy()
    for c in ["mean_monthly_ret_pct", "std_monthly_ret_pct", "worst_month_ret_pct"]:
        fmt[c] = fmt[c].map(lambda x: f"{x:+.3f}%")
    fmt["positive_months_pct"] = fmt["positive_months_pct"].map(lambda x: f"{x:.2%}")
    fmt["sharpe_annual"] = fmt["sharpe_annual"].map(lambda x: f"{x:.3f}")
    for c in ["total_pnl", "max_dd_pnl"]:
        fmt[c] = fmt[c].map(lambda x: f"{x:,.0f}")
    print()
    print(fmt.to_string(index=False))

    # Also dump per-cohort decisions for one chosen variant for inspection
    print(f"\nwrote {OUT_CSV}")

    # Show gate triggers for the 20p threshold
    print("\n=== gate triggers at 20p threshold ===")
    trig = score_dist[score_dist["p90_wf_pct"] < 0.20].copy()
    trig = trig[trig.index >= args.warmup_cohorts]
    if len(trig):
        # join with baseline cohort returns to show what was avoided
        base_lookup = baseline.set_index("ym")["return_pct"].to_dict()
        trig["baseline_ret_pct"] = trig["ym"].map(base_lookup)
        print(trig[["playbook_date", "p90", "p90_wf_pct", "baseline_ret_pct"]].to_string(index=False))
    else:
        print("(none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
