"""Validation harness for the multi-seed ensemble selection model.

Proves the ensemble removes single-seed variance by running 3 DISJOINT seed
groups per (K, agg) cell through the full walk-forward + backtest, then checking
their monthly-Sharpe spread collapses vs the single-seed sd (~0.049).

Matrix (full): K in {5,10} x agg in {score,rank} x 3 disjoint seed groups.

Efficiency: agg is a step5 (scoring) choice, NOT a training choice — the K models
are trained ONCE per (K, group) and reused across both aggs. So the run is:
  6 training sets  ->  12 score+backtest passes  (+1 single-seed control).

Seed groups (disjoint; K=5 nested in the K=10 pools so they're comparable):
  K=10:  g1 = seeds 1..10   g2 = 11..20   g3 = 21..30
  K=5 :  g1 = seeds 1..5    g2 = 11..15   g3 = 21..25
  control: single seed=42, n_seeds=1 (current production a-priori default)

Outputs:
  models_selection_val/<set>/              per-set ensemble models (walk-forward)
  backtester/output/val/<set>_<agg>/       per-cell rolling backtest
  backtester/output/val/SUMMARY.md         verdict table

Usage:
  venv/bin/python3 scripts/validate_ensemble.py                  # full matrix, sequential
  venv/bin/python3 scripts/validate_ensemble.py --dry-run        # print commands only
  venv/bin/python3 scripts/validate_ensemble.py --ks 5 --groups g1 --aggs score   # one cell
  venv/bin/python3 scripts/validate_ensemble.py --jobs 3         # train groups in parallel (OMP-limited)
  venv/bin/python3 scripts/validate_ensemble.py --skip-existing-train   # reuse trained models
  venv/bin/python3 scripts/validate_ensemble.py --report-only    # just (re)build SUMMARY.md

PASS criteria (per feedback_selection_model_prefer_stable — stability first):
  - 3-group monthly-Sharpe spread < 0.02  (vs single-seed sd ~0.049)
  - center ~0.707, NOT regressed (drop > 0.05 below baseline = fail)
  - PnL std ~ baseline (~9.8%)
Ensemble should be "center unchanged, variance smaller", never a regression.

!! STALE ABSOLUTE LEVELS (2026-08-18): the `center ~0.707` / `PnL std ~9.8%` numbers above
   were measured BEFORE the 2026-08-02 `entry_date` look-ahead fix (see strategies/CLAUDE.md
   § feature as-of guard). With the corrected as-of, the same old artifacts re-run at
   --end-date 2026-07-11 / top-25 / 40 cohorts give monthly Sharpe **0.5453**; after the
   2026-08-18 individual-report backfill, **0.5526**. Running this harness against the
   0.707 threshold will fail every cell for the wrong reason — re-baseline first.
   The *relative* criterion (3-group spread << single-seed sd) is unaffected.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable

MODELS_VAL_ROOT = ROOT_DIR / "models_selection_val"
BT_VAL_ROOT = ROOT_DIR / "backtester" / "output" / "val"

# --- 30-seed baseline distribution (see feedback_ml_experiment_rigor / CLAUDE.md) ---
BASELINE_CENTER = 0.707  # mean monthly Sharpe over 30 single seeds
SINGLE_SEED_SD = 0.049  # sd of that distribution — the "seed lottery" we want gone
FAIL_THRESHOLD = 0.05  # Sharpe regression > this = fail
SPREAD_TARGET = 0.02  # ideal 3-group spread once variance is averaged out

# base seed per (K, group); seeds = range(base, base+K)
SEED_GROUPS = {
    10: {"g1": 1, "g2": 11, "g3": 21},
    5: {"g1": 1, "g2": 11, "g3": 21},
}
CONTROL_SET = "single_s42"  # single seed=42, n_seeds=1


def seeds_for(k: int, base: int) -> list[int]:
    return list(range(base, base + k))


def run(cmd: list[str], *, env: dict | None = None, dry: bool, label: str) -> bool:
    """Run a subprocess from ROOT_DIR. Returns True on success (or dry-run)."""
    printable = " ".join(str(c) for c in cmd)
    if dry:
        print(f"[dry] {label}\n      {printable}")
        return True
    print(f"[run] {label}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env)
    ok = result.returncode == 0
    print(
        f"[{'ok' if ok else 'FAIL'}] {label}"
        + ("" if ok else f" (rc={result.returncode})")
    )
    return ok


# ---------------------------------------------------------------- training ---
def train_set(
    set_name: str,
    k: int,
    base_seed: int,
    *,
    skip_existing: bool,
    train_start: str | None,
    train_end: str | None,
    omp_threads: int | None,
    dry: bool,
) -> bool:
    """Train one (K, group) ensemble set into models_selection_val/<set>/."""
    cmd = [
        PY,
        "strategies/step4_batch_train_selection_model.py",
        "--seed",
        str(base_seed),
        "--n-seeds",
        str(k),
        "--models-root",
        str(MODELS_VAL_ROOT / set_name),
    ]
    if train_start:
        cmd += ["--start-date", train_start]
    if train_end:
        cmd += ["--end-date", train_end]
    if skip_existing:
        cmd += ["--skip-existing"]
    env = dict(os.environ)
    if omp_threads:
        env["OMP_NUM_THREADS"] = str(omp_threads)
    seeds = seeds_for(k, base_seed)
    return run(cmd, env=env, dry=dry, label=f"train {set_name} (K={k}, seeds={seeds})")


# ----------------------------------------------------- score + backtest ---
def score_and_backtest(
    set_name: str,
    agg: str,
    *,
    backtest_start: str,
    top_n: int,
    position_amount: float,
    dry: bool,
) -> bool:
    models_root = MODELS_VAL_ROOT / set_name
    bt_dir = BT_VAL_ROOT / f"{set_name}_{agg}"
    score_cmd = [
        PY,
        "strategies/step5_batch_score_and_publish.py",
        "--models-root",
        str(models_root),
        "--ensemble-agg",
        agg,
    ]
    bt_cmd = [
        PY,
        "backtester/run_rolling.py",
        "--start-date",
        backtest_start,
        "--top-n",
        str(top_n),
        "--position-amount",
        str(position_amount),
        "--models-root",
        str(models_root),
        "--out-dir",
        str(bt_dir),
    ]
    ok = run(score_cmd, dry=dry, label=f"score {set_name} agg={agg}")
    if not ok:
        return False
    return run(bt_cmd, dry=dry, label=f"backtest {set_name} agg={agg}")


# ------------------------------------------------------------- reporting ---
def read_metrics(set_name: str, agg: str) -> dict | None:
    summary = BT_VAL_ROOT / f"{set_name}_{agg}" / "rolling_summary.json"
    if not summary.exists():
        return None
    s = json.loads(summary.read_text(encoding="utf-8"))
    mo = s.get("monthly_stats_38_basis") or {}
    return {
        "sharpe": mo.get("monthly_sharpe"),
        "sharpe_ann": mo.get("monthly_sharpe_annualized"),
        "mean_pct": mo.get("mean_monthly_return_pct"),
        "std_pct": mo.get("std_monthly_return_pct"),
        "cohorts": mo.get("cohort_count"),
        "pnl": s.get("total_net_pnl"),
    }


def _fmt(v, spec=".3f"):
    return format(v, spec) if isinstance(v, (int, float)) else "  n/a"


def build_report(ks: list[int], groups: list[str], aggs: list[str], dry: bool) -> None:
    if dry:
        return
    lines: list[str] = []
    lines.append("# Multi-seed ensemble validation\n")
    lines.append(
        "Each (K, agg) cell ran 3 **disjoint** seed groups through the full "
        "walk-forward + backtest. If the ensemble kills the seed lottery, the "
        "3 groups' monthly Sharpe should cluster tightly (spread far below the "
        f"single-seed sd of {SINGLE_SEED_SD:.3f}, ideally < {SPREAD_TARGET:.2f}) "
        f"and stay centered near the 30-seed mean {BASELINE_CENTER:.3f}.\n"
    )
    lines.append(
        f"PASS = spread < {SPREAD_TARGET:.2f} AND center not regressed "
        f"(> {FAIL_THRESHOLD:.2f} below {BASELINE_CENTER:.3f} = fail).\n"
    )

    # control
    ctrl = read_metrics(CONTROL_SET, "score")
    lines.append("## Control — single seed=42\n")
    if ctrl:
        lines.append(
            f"- monthly Sharpe **{_fmt(ctrl['sharpe'])}** "
            f"(ann {_fmt(ctrl['sharpe_ann'])}), mean/std "
            f"{_fmt(ctrl['mean_pct'])}% / {_fmt(ctrl['std_pct'])}%, "
            f"PnL {_fmt(ctrl['pnl'], ',.0f')} ({ctrl['cohorts']} cohorts)\n"
        )
        lines.append(
            f"  > a single sample; the 30-seed distribution is mean "
            f"{BASELINE_CENTER:.3f} / sd {SINGLE_SEED_SD:.3f}, range ~0.64–0.83.\n"
        )
    else:
        lines.append("- (not run yet)\n")

    # matrix
    recommendations: list[
        tuple[float, float, int, str]
    ] = []  # (spread, -center, K, agg)
    lines.append("\n## Matrix — ensemble cells\n")
    group_cols = " | ".join(groups)
    group_sep = "|".join(["----"] * len(groups))
    lines.append(
        f"| K | agg | {group_cols} | center | spread | PnL (mean, M) | std% (mean) | verdict |"
    )
    lines.append(
        f"|---|-----|{group_sep}|--------|--------|---------------|-------------|---------|"
    )
    for k in ks:
        for agg in aggs:
            sharpes, pnls, stds = [], [], []
            cells = {}
            for g in groups:
                m = read_metrics(f"k{k}_{g}", agg)
                cells[g] = m
                if m and isinstance(m.get("sharpe"), (int, float)):
                    sharpes.append(m["sharpe"])
                    pnls.append(m["pnl"])
                    stds.append(m["std_pct"])
            cells_joined = " | ".join(
                _fmt(cells[g]["sharpe"]) if cells[g] else " n/a" for g in groups
            )
            if len(sharpes) == len(groups) and sharpes:
                center = sum(sharpes) / len(sharpes)
                spread = max(sharpes) - min(sharpes)
                mean_pnl = sum(pnls) / len(pnls) / 1e6
                mean_std = sum(stds) / len(stds)
                spread_ok = spread < SPREAD_TARGET
                center_ok = center >= BASELINE_CENTER - FAIL_THRESHOLD
                verdict = "✅ PASS" if (spread_ok and center_ok) else "❌ FAIL"
                if spread_ok and center_ok:
                    recommendations.append((spread, -center, k, agg))
                lines.append(
                    f"| {k} | {agg} | {cells_joined} | "
                    f"{center:.3f} | {spread:.3f} | {mean_pnl:+.2f} | {mean_std:.2f} | {verdict} |"
                )
            else:
                lines.append(
                    f"| {k} | {agg} | {cells_joined} | — | — | — | — | ⏳ incomplete |"
                )

    lines.append("\n## Recommendation\n")
    if recommendations:
        recommendations.sort()
        spread, neg_center, k, agg = recommendations[0]
        lines.append(
            f"**K={k}, agg={agg}** — tightest spread ({spread:.3f}) among passing "
            f"cells, center {-neg_center:.3f}. Use this for the production "
            f"follow-up (flip step4_batch default + retrain models_selection/).\n"
        )
    else:
        lines.append(
            "No cell passed yet (run incomplete, or spread/center criteria unmet). "
            "Inspect the table above.\n"
        )

    BT_VAL_ROOT.mkdir(parents=True, exist_ok=True)
    out = BT_VAL_ROOT / "SUMMARY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nReport written: {out}")


# ------------------------------------------------------------------ main ---
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-seed ensemble validation harness.")
    p.add_argument(
        "--ks", type=int, nargs="+", default=[10, 5], help="K values (default 10 5)"
    )
    p.add_argument(
        "--groups", nargs="+", default=["g1", "g2", "g3"], help="seed groups"
    )
    p.add_argument(
        "--aggs", nargs="+", default=["score", "rank"], choices=["score", "rank"]
    )
    p.add_argument(
        "--no-control", action="store_true", help="skip the single-seed=42 control"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print commands, do not execute"
    )
    p.add_argument(
        "--skip-existing-train",
        action="store_true",
        help="reuse already-trained models",
    )
    p.add_argument(
        "--report-only", action="store_true", help="only (re)build SUMMARY.md"
    )
    p.add_argument(
        "--jobs", type=int, default=1, help="parallel training jobs (OMP-limited)"
    )
    p.add_argument(
        "--omp-threads", type=int, default=None, help="OMP_NUM_THREADS per training job"
    )
    p.add_argument(
        "--train-start",
        type=str,
        default=None,
        help="override step4_batch --start-date",
    )
    p.add_argument(
        "--train-end", type=str, default=None, help="override step4_batch --end-date"
    )
    p.add_argument("--backtest-start", type=str, default="2022-07-11")
    p.add_argument("--top-n", type=int, default=15)
    p.add_argument("--position-amount", type=float, default=100_000.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.report_only:
        build_report(args.ks, args.groups, args.aggs, dry=False)
        return

    # default OMP threads when running parallel jobs (leave cores for others)
    omp = args.omp_threads
    if args.jobs > 1 and omp is None:
        omp = max(1, (os.cpu_count() or 4) // args.jobs)

    # 1) training: one set per (K, group), trained ONCE, reused across aggs.
    train_jobs: list[tuple[str, int, int]] = []  # (set_name, K, base_seed)
    for k in args.ks:
        for g in args.groups:
            base = SEED_GROUPS[k][g]
            train_jobs.append((f"k{k}_{g}", k, base))

    print(f"=== Training {len(train_jobs)} ensemble sets (jobs={args.jobs}) ===")
    train_results: dict[str, bool] = {}

    def _do_train(job):
        set_name, k, base = job
        return set_name, train_set(
            set_name,
            k,
            base,
            skip_existing=args.skip_existing_train,
            train_start=args.train_start,
            train_end=args.train_end,
            omp_threads=omp,
            dry=args.dry_run,
        )

    if args.jobs > 1 and not args.dry_run:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            for set_name, ok in ex.map(_do_train, train_jobs):
                train_results[set_name] = ok
    else:
        for job in train_jobs:
            set_name, ok = _do_train(job)
            train_results[set_name] = ok

    # control training
    if not args.no_control:
        print("=== Training control (single seed=42) ===")
        ok = train_set(
            CONTROL_SET,
            k=1,
            base_seed=42,
            skip_existing=args.skip_existing_train,
            train_start=args.train_start,
            train_end=args.train_end,
            omp_threads=omp,
            dry=args.dry_run,
        )
        train_results[CONTROL_SET] = ok

    # 2) score + backtest: each set x each agg (control: score only — agg is no-op).
    print(
        f"\n=== Score + backtest ({len(train_jobs)} sets x {len(args.aggs)} aggs) ==="
    )
    for set_name, k, base in train_jobs:
        if not train_results.get(set_name, True):
            print(f"[skip] {set_name}: training failed")
            continue
        for agg in args.aggs:
            score_and_backtest(
                set_name,
                agg,
                backtest_start=args.backtest_start,
                top_n=args.top_n,
                position_amount=args.position_amount,
                dry=args.dry_run,
            )
    if not args.no_control and train_results.get(CONTROL_SET, True):
        score_and_backtest(
            CONTROL_SET,
            "score",
            backtest_start=args.backtest_start,
            top_n=args.top_n,
            position_amount=args.position_amount,
            dry=args.dry_run,
        )

    # 3) report
    build_report(args.ks, args.groups, args.aggs, dry=args.dry_run)


if __name__ == "__main__":
    main()
