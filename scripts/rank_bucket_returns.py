"""Rank-bucket forward returns: does the selection model's ml_rank predict returns?

For each cohort, join candidates_scored.csv (ml_rank, from the ensemble) with
feature_return_analysis.csv (fwd_return_pct, realized) on symbol, then bucket by
ml_rank three ways:
  - Fixed-count tiers : ranks 1-10, 11-20, 21-30 (= the actual trading tiers;
                        answers "are my top-10 picks better than the next 10?")
  - Quintiles Q1..Q5  : Q1 = best-ranked fifth of the universe (the old experiment)
  - Deciles   Q1..Q10 : model was trained with n_bins=10, so deciles are native

Reports, per scheme: per-bucket mean fwd_return (averaged equally across cohorts),
top-vs-bottom spread, monotonicity (Spearman of bucket index vs mean return), and
hit-rate (fraction of cohorts where the top bucket beat the bottom bucket — a
robustness check, not just one averaged number).

Feb/Mar cohorts are PIT-leaked (anchor = previous-year Q4 not yet published by the
02-10/03-10 cutoff, see backtester/CLAUDE.md), so their rank rests on future-peeking
features. Default EXCLUDES months 02/03; pass --include-feb-mar to see all cohorts.

Usage:
  venv/bin/python3 scripts/rank_bucket_returns.py
  venv/bin/python3 scripts/rank_bucket_returns.py --include-feb-mar
  venv/bin/python3 scripts/rank_bucket_returns.py --models-root models_selection_val/k10_g1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def load_cohorts(models_root: Path, fra_path: Path, include_feb_mar: bool):
    """Yield (cohort_date, merged_df[symbol, ml_rank, fwd_return_pct]) per cohort."""
    fra = pd.read_csv(fra_path)
    fra["playbook_date"] = fra["playbook_date"].astype(str)
    fra["symbol"] = fra["symbol"].astype(str).str.zfill(4)
    fra = fra[["playbook_date", "symbol", "fwd_return_pct"]]

    out = []
    for d in sorted(models_root.iterdir()):
        if not d.is_dir() or d.name == "latest":
            continue
        cs = d / "candidates_scored.csv"
        if not cs.exists():
            continue
        month = d.name[5:7]
        if not include_feb_mar and month in ("02", "03"):
            continue
        df = pd.read_csv(cs)
        if "ml_rank" not in df.columns:
            continue
        df["symbol"] = df["symbol"].astype(str).str.zfill(4)
        sub = fra[fra["playbook_date"] == d.name]
        m = df.merge(sub, on="symbol", how="inner")
        m = m.dropna(subset=["fwd_return_pct", "ml_rank"])
        if len(m) < 50:
            continue
        out.append((d.name, m.sort_values("ml_rank")))
    return out


def _spearman(xs, ys) -> float:
    return pd.Series(xs).corr(pd.Series(ys), method="spearman")


def fixed_tiers(cohorts, tiers=((1, 10), (11, 20), (21, 30))):
    """Mean fwd_return per fixed rank tier, averaged across cohorts + hit-rate."""
    per_cohort = {t: [] for t in tiers}
    top_beats_next = 0
    n = 0
    for _, m in cohorts:
        vals = {}
        for lo, hi in tiers:
            sel = m[(m["ml_rank"] >= lo) & (m["ml_rank"] <= hi)]["fwd_return_pct"]
            vals[(lo, hi)] = sel.mean() if len(sel) else float("nan")
            per_cohort[(lo, hi)].append(vals[(lo, hi)])
        # hit-rate: did 1-10 beat 11-20 this cohort?
        a, b = vals[tiers[0]], vals[tiers[1]]
        if pd.notna(a) and pd.notna(b):
            n += 1
            top_beats_next += int(a > b)
    means = {t: pd.Series(per_cohort[t]).mean() for t in tiers}
    return means, (top_beats_next, n)


def quantile_buckets(cohorts, q: int):
    """Mean fwd_return per quantile bucket (1=best) averaged across cohorts."""
    labels = list(range(1, q + 1))
    per_cohort = {b: [] for b in labels}
    top_beats_bot = 0
    n = 0
    for _, m in cohorts:
        try:
            buckets = pd.qcut(m["ml_rank"], q, labels=labels)
        except ValueError:
            continue
        g = m.assign(_b=buckets).groupby("_b", observed=True)["fwd_return_pct"].mean()
        for b in labels:
            per_cohort[b].append(g.get(b, float("nan")))
        if pd.notna(g.get(1)) and pd.notna(g.get(q)):
            n += 1
            top_beats_bot += int(g.get(1) > g.get(q))
    means = {b: pd.Series(per_cohort[b]).mean() for b in labels}
    return means, (top_beats_bot, n)


def report(label: str, models_root: Path, fra_path: Path, include_feb_mar: bool):
    cohorts = load_cohorts(models_root, fra_path, include_feb_mar)
    tag = "ALL cohorts" if include_feb_mar else "excl. Feb/Mar (tradeable)"
    print(f"\n{'=' * 64}\n{label}  [{tag}]  n_cohorts={len(cohorts)}\n{'=' * 64}")
    if not cohorts:
        print("  (no cohorts)")
        return

    # 1) fixed-count tiers
    tiers = ((1, 10), (11, 20), (21, 30))
    means, (hit, n) = fixed_tiers(cohorts, tiers)
    print("\n[Fixed tiers] mean fwd_return by rank tier:")
    for lo, hi in tiers:
        print(f"  rank {lo:>2}-{hi:<2}: {means[(lo, hi)]:+.3f}%")
    spread = means[(1, 10)] - means[(11, 20)]
    print(f"  -> top1-10 minus 11-20: {spread:+.3f}pp  "
          f"(top1-10 > 11-20 in {hit}/{n} cohorts = {hit / n * 100:.0f}%)")

    # 2) quintiles
    qm, (qhit, qn) = quantile_buckets(cohorts, 5)
    seq = [qm[b] for b in range(1, 6)]
    print("\n[Quintiles] Q1(best)..Q5(worst) mean fwd_return:")
    print("  " + "  ".join(f"Q{b}={qm[b]:+.2f}%" for b in range(1, 6)))
    print(f"  -> Q1-Q5 spread: {seq[0] - seq[-1]:+.3f}pp  "
          f"(Q1 > Q5 in {qhit}/{qn} = {qhit / qn * 100:.0f}%)  "
          f"monotonicity(Spearman bucket vs ret)={_spearman(range(1, 6), seq):+.2f}")

    # 3) deciles
    dm, (dhit, dn) = quantile_buckets(cohorts, 10)
    dseq = [dm[b] for b in range(1, 11)]
    print("\n[Deciles] Q1(best)..Q10(worst) mean fwd_return:")
    print("  " + "  ".join(f"Q{b}={dm[b]:+.2f}" for b in range(1, 11)))
    print(f"  -> Q1-Q10 spread: {dseq[0] - dseq[-1]:+.3f}pp  "
          f"(Q1 > Q10 in {dhit}/{dn} = {dhit / dn * 100:.0f}%)  "
          f"monotonicity(Spearman)={_spearman(range(1, 11), dseq):+.2f}")


def main() -> int:
    p = argparse.ArgumentParser(description="Rank-bucket forward returns by ml_rank.")
    p.add_argument("--models-root", type=Path, default=ROOT / "models_selection")
    p.add_argument("--include-feb-mar", action="store_true",
                   help="Include PIT-leaked Feb/Mar cohorts (default: excluded)")
    args = p.parse_args()
    fra = ROOT / "strategies" / "output" / "feature_return_analysis.csv"

    report("Production ensemble", args.models_root, fra, include_feb_mar=False)
    report("Production ensemble", args.models_root, fra, include_feb_mar=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
