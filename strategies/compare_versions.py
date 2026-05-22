"""
比對重構前後 strategies pipeline 的輸出差異。

用法:
  # 全量比對
  venv/bin/python3 strategies/compare_versions.py --out strategies/compare_report.csv

  # 限定 cohort (sample 驗證用)
  venv/bin/python3 strategies/compare_versions.py \
      --months 2022/01,2024/11,2026/02 \
      --out strategies/compare_sample.csv

預設路徑:
  --old-output-root  strategies/output_old           （舊 YYYY/MM 結構）
  --new-output-root  strategies/output               （新 YYYY-MM-DD 結構）
  --old-models-root  models_selection_old            （舊 YYYY/MM 結構）
  --new-models-root  models_selection                （新 YYYY-MM-DD 結構）

新版目錄是 playbook run date（cutoff +1：5/8/11 月 = 16 號，其餘月份 = 11 號）。
對 cohort 2022/01，舊 = `2022/01/`、新 = `2022-01-11/`；本 script 內部依公式換算。

比對對象:
  1. dataset_strategy.csv     — rows / cols added/removed / 共有 numeric 欄位的平均絕對差
  2. trade_candidates.csv     — 候選股集合 Jaccard、共有 symbol 的
                                base_eps_growth_pct / ml_eps_delta_pct Spearman
  3. selection_model latest.json (train_through) — train/eval IC、feature count
  4. candidates_scored.csv    — top-N overlap、ml_rank Spearman、scored_by_train_through 是否一致

舊版 schema (models_selection_old/) 的 latest.json key 是 `cutoff`、
candidates_scored.csv column 是 `scored_by_model_cutoff`；本 script 會 fallback 讀。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.shared_config import playbook_run_date  # noqa: E402

MONTH_DIR_RE = re.compile(r"^\d{2}$")
YEAR_DIR_RE = re.compile(r"^\d{4}$")
NEW_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--old-output-root", type=Path, default=ROOT_DIR / "strategies" / "output_old"
    )
    p.add_argument(
        "--new-output-root", type=Path, default=ROOT_DIR / "strategies" / "output"
    )
    p.add_argument(
        "--old-models-root", type=Path, default=ROOT_DIR / "models_selection_old"
    )
    p.add_argument(
        "--new-models-root", type=Path, default=ROOT_DIR / "models_selection"
    )
    p.add_argument(
        "--out", type=Path, default=ROOT_DIR / "strategies" / "compare_report.csv"
    )
    p.add_argument(
        "--months",
        type=str,
        default=None,
        help="逗號分隔的 YYYY/MM 清單,例如 2024/11,2026/02。預設全量。",
    )
    return p.parse_args()


def scan_months(*roots: Path) -> list[tuple[int, str]]:
    """掃所有 root,聯集出 (year, month_str) 月份清單。

    Old roots (`output_old/`, `models_selection_old/`) 結構是 `<YYYY>/<MM>/`；
    new roots (`output/`, `models_selection/`) 結構是 `<YYYY-MM-DD>/`。兩種都掃。
    """
    found: set[tuple[int, str]] = set()
    for root in roots:
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            # 新格式：YYYY-MM-DD
            if NEW_DIR_RE.fullmatch(name):
                y_str, m_str, _ = name.split("-")
                found.add((int(y_str), m_str))
                continue
            # 舊格式：YYYY/MM
            if YEAR_DIR_RE.fullmatch(name):
                for month_dir in entry.iterdir():
                    if month_dir.is_dir() and MONTH_DIR_RE.fullmatch(month_dir.name):
                        found.add((int(name), month_dir.name))
    return sorted(found)


def new_dir(root: Path, year: int, month: str) -> Path:
    """回傳該 cohort 在新格式 root 下的目錄（playbook_run_date 命名）。"""
    return root / playbook_run_date(year, month)


def old_dir(root: Path, year: int, month: str) -> Path:
    """回傳該 cohort 在舊格式 root 下的目錄。"""
    return root / str(year) / month


def parse_months_arg(s: str | None) -> list[tuple[int, str]] | None:
    if not s:
        return None
    out: list[tuple[int, str]] = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        y_str, m_str = tok.split("/")
        out.append((int(y_str), m_str.zfill(2)))
    return out


def read_csv_safe(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] read fail: {path}: {exc}")
        return None


def read_json_safe(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] read fail: {path}: {exc}")
        return None


def diff_set(old: set[str], new: set[str]) -> tuple[str, str]:
    added = sorted(new - old)
    removed = sorted(old - new)
    return (";".join(added), ";".join(removed))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return np.nan
    return len(a & b) / len(a | b)


def spearman_safe(s1: pd.Series, s2: pd.Series) -> float:
    s1 = pd.to_numeric(s1, errors="coerce")
    s2 = pd.to_numeric(s2, errors="coerce")
    mask = s1.notna() & s2.notna()
    if mask.sum() < 3:
        return np.nan
    if s1[mask].std() == 0 or s2[mask].std() == 0:
        return np.nan
    return float(s1[mask].corr(s2[mask], method="spearman"))


def compute_dataset_metrics(
    old_ds: pd.DataFrame | None, new_ds: pd.DataFrame | None
) -> dict:
    out: dict = {
        "ds_rows_old": np.nan,
        "ds_rows_new": np.nan,
        "ds_rows_diff_pct": np.nan,
        "ds_cols_added": "",
        "ds_cols_removed": "",
        "ds_shared_numeric_mean_abs_diff": np.nan,
    }
    if old_ds is None or new_ds is None:
        return out

    out["ds_rows_old"] = len(old_ds)
    out["ds_rows_new"] = len(new_ds)
    if len(old_ds) > 0:
        out["ds_rows_diff_pct"] = (len(new_ds) - len(old_ds)) / len(old_ds) * 100.0

    added, removed = diff_set(set(old_ds.columns), set(new_ds.columns))
    out["ds_cols_added"] = added
    out["ds_cols_removed"] = removed

    # 共有 numeric 欄位的 mean abs diff（依 symbol 對齊）
    if "symbol" in old_ds.columns and "symbol" in new_ds.columns:
        old_ds = old_ds.copy()
        new_ds = new_ds.copy()
        old_ds["symbol"] = old_ds["symbol"].astype(str).str.strip()
        new_ds["symbol"] = new_ds["symbol"].astype(str).str.strip()
        shared = sorted(
            set(old_ds.columns) & set(new_ds.columns) - {"symbol", "name", "industry"}
        )
        # 只保留兩邊都是 numeric 的欄位
        numeric_shared = [
            c
            for c in shared
            if pd.api.types.is_numeric_dtype(old_ds[c])
            and pd.api.types.is_numeric_dtype(new_ds[c])
        ]
        if numeric_shared:
            merged = old_ds[["symbol"] + numeric_shared].merge(
                new_ds[["symbol"] + numeric_shared],
                on="symbol",
                how="inner",
                suffixes=("_old", "_new"),
            )
            if not merged.empty:
                diffs = []
                for c in numeric_shared:
                    d = (merged[f"{c}_old"] - merged[f"{c}_new"]).abs().mean()
                    if pd.notna(d):
                        diffs.append(d)
                if diffs:
                    out["ds_shared_numeric_mean_abs_diff"] = float(np.mean(diffs))
    return out


def compute_trade_candidates_metrics(
    old_tc: pd.DataFrame | None, new_tc: pd.DataFrame | None
) -> dict:
    out = {
        "tc_n_old": np.nan,
        "tc_n_new": np.nan,
        "tc_symbol_jaccard": np.nan,
        "tc_upside_rank_corr": np.nan,
    }
    if old_tc is None or new_tc is None:
        return out

    out["tc_n_old"] = len(old_tc)
    out["tc_n_new"] = len(new_tc)

    if "symbol" not in old_tc.columns or "symbol" not in new_tc.columns:
        return out

    old_sym = set(old_tc["symbol"].astype(str).str.strip())
    new_sym = set(new_tc["symbol"].astype(str).str.strip())
    out["tc_symbol_jaccard"] = jaccard(old_sym, new_sym)

    for col, out_key in [
        ("base_eps_growth_pct", "tc_base_growth_rank_corr"),
        ("ml_eps_delta_pct", "tc_ml_delta_rank_corr"),
    ]:
        if col in old_tc.columns and col in new_tc.columns:
            old_x = old_tc[["symbol", col]].copy()
            new_x = new_tc[["symbol", col]].copy()
            old_x["symbol"] = old_x["symbol"].astype(str).str.strip()
            new_x["symbol"] = new_x["symbol"].astype(str).str.strip()
            merged = old_x.merge(
                new_x, on="symbol", how="inner", suffixes=("_old", "_new")
            )
            out[out_key] = spearman_safe(merged[f"{col}_old"], merged[f"{col}_new"])
    return out


def compute_selection_model_metrics(
    old_meta: dict | None, new_meta: dict | None
) -> dict:
    """新版 latest.json 用 `train_through` key；舊版用 `cutoff` — 兩者都不直接列出，但
    train/eval IC、feature count、train_rows 兩個 schema 共用。"""
    out = {
        "sm_train_ic_old": np.nan,
        "sm_train_ic_new": np.nan,
        "sm_eval_ic_old": np.nan,
        "sm_eval_ic_new": np.nan,
        "sm_n_features_old": np.nan,
        "sm_n_features_new": np.nan,
        "sm_train_rows_old": np.nan,
        "sm_train_rows_new": np.nan,
    }
    if isinstance(old_meta, dict):
        out["sm_train_ic_old"] = old_meta.get("train_spearman_ic", np.nan)
        out["sm_eval_ic_old"] = old_meta.get("eval_spearman_ic", np.nan)
        feats = old_meta.get("feature_cols")
        if isinstance(feats, list):
            out["sm_n_features_old"] = len(feats)
        out["sm_train_rows_old"] = old_meta.get("train_rows", np.nan)
    if isinstance(new_meta, dict):
        out["sm_train_ic_new"] = new_meta.get("train_spearman_ic", np.nan)
        out["sm_eval_ic_new"] = new_meta.get("eval_spearman_ic", np.nan)
        feats = new_meta.get("feature_cols")
        if isinstance(feats, list):
            out["sm_n_features_new"] = len(feats)
        out["sm_train_rows_new"] = new_meta.get("train_rows", np.nan)
    return out


def compute_candidates_scored_metrics(
    old_cs: pd.DataFrame | None, new_cs: pd.DataFrame | None
) -> tuple[dict, str]:
    out = {
        "cs_n_old": np.nan,
        "cs_n_new": np.nan,
        "cs_top10_overlap": np.nan,
        "cs_top20_overlap": np.nan,
        "cs_ml_rank_spearman": np.nan,
        "cs_train_through_match": "",
    }
    note = ""
    if old_cs is None or new_cs is None:
        return out, note

    out["cs_n_old"] = len(old_cs)
    out["cs_n_new"] = len(new_cs)

    needed = {"symbol", "ml_rank"}
    if not needed.issubset(old_cs.columns) or not needed.issubset(new_cs.columns):
        note = "missing symbol/ml_rank in candidates_scored"
        return out, note

    old = old_cs[["symbol", "ml_rank"]].copy()
    new = new_cs[["symbol", "ml_rank"]].copy()
    old["symbol"] = old["symbol"].astype(str).str.strip()
    new["symbol"] = new["symbol"].astype(str).str.strip()

    for n in (10, 20):
        old_top = set(old.nsmallest(n, "ml_rank")["symbol"])
        new_top = set(new.nsmallest(n, "ml_rank")["symbol"])
        if old_top and new_top:
            out[f"cs_top{n}_overlap"] = len(old_top & new_top) / n

    merged = old.merge(new, on="symbol", how="inner", suffixes=("_old", "_new"))
    if len(merged) >= 3:
        out["cs_ml_rank_spearman"] = spearman_safe(
            merged["ml_rank_old"], merged["ml_rank_new"]
        )

    # walk-forward 來源比對：新版 column 是 `scored_by_train_through`，
    # 舊版（models_selection_old/）是 `scored_by_model_cutoff`，fallback 讀。
    def _train_through(df: pd.DataFrame) -> str | None:
        for col in ("scored_by_train_through", "scored_by_model_cutoff"):
            if col in df.columns:
                vals = df[col].dropna().unique()
                if len(vals) >= 1:
                    return str(vals[0])
        return None

    c_old = _train_through(old_cs)
    c_new = _train_through(new_cs)
    if c_old is None and c_new is None:
        out["cs_train_through_match"] = "both_missing"
    elif c_old is None:
        out["cs_train_through_match"] = f"old_missing; new={c_new}"
    elif c_new is None:
        out["cs_train_through_match"] = f"new_missing; old={c_old}"
    elif c_old == c_new:
        out["cs_train_through_match"] = f"match:{c_old}"
    else:
        out["cs_train_through_match"] = f"diff: old={c_old} new={c_new}"
    return out, note


def compare_month(
    year: int,
    month: str,
    old_output_root: Path,
    new_output_root: Path,
    old_models_root: Path,
    new_models_root: Path,
) -> dict:
    old_od = old_dir(old_output_root, year, month)
    new_od = new_dir(new_output_root, year, month)
    old_md = old_dir(old_models_root, year, month)
    new_md = new_dir(new_models_root, year, month)

    row: dict = {"year": year, "month": month}

    old_ds = read_csv_safe(old_od / "dataset_strategy.csv")
    new_ds = read_csv_safe(new_od / "dataset_strategy.csv")
    row.update(compute_dataset_metrics(old_ds, new_ds))

    old_tc = read_csv_safe(old_od / "trade_candidates.csv")
    new_tc = read_csv_safe(new_od / "trade_candidates.csv")
    row.update(compute_trade_candidates_metrics(old_tc, new_tc))

    old_meta = read_json_safe(old_md / "latest.json")
    new_meta = read_json_safe(new_md / "latest.json")
    row.update(compute_selection_model_metrics(old_meta, new_meta))

    old_cs = read_csv_safe(old_md / "candidates_scored.csv")
    new_cs = read_csv_safe(new_md / "candidates_scored.csv")
    cs_metrics, cs_note = compute_candidates_scored_metrics(old_cs, new_cs)
    row.update(cs_metrics)

    notes: list[str] = []
    for label, path in [
        ("old_dataset_strategy", old_od / "dataset_strategy.csv"),
        ("new_dataset_strategy", new_od / "dataset_strategy.csv"),
        ("old_trade_candidates", old_od / "trade_candidates.csv"),
        ("new_trade_candidates", new_od / "trade_candidates.csv"),
        ("old_latest_json", old_md / "latest.json"),
        ("new_latest_json", new_md / "latest.json"),
        ("old_candidates_scored", old_md / "candidates_scored.csv"),
        ("new_candidates_scored", new_md / "candidates_scored.csv"),
    ]:
        if not path.exists():
            notes.append(f"missing:{label}")
    if cs_note:
        notes.append(cs_note)
    row["notes"] = "; ".join(notes)
    return row


def print_summary(df: pd.DataFrame) -> None:
    print()
    print("=" * 60)
    print(f"COMPARE SUMMARY ({len(df)} months)")
    print("=" * 60)

    both_sm = df[df["sm_train_ic_old"].notna() & df["sm_train_ic_new"].notna()]
    print(
        f"\n[Coverage] months with both old & new selection_model: {len(both_sm)}/{len(df)}"
    )

    if not both_sm.empty:
        for col, label in [
            ("sm_train_ic_old", "train_ic_old"),
            ("sm_train_ic_new", "train_ic_new"),
            ("sm_eval_ic_old", "eval_ic_old"),
            ("sm_eval_ic_new", "eval_ic_new"),
        ]:
            vals = both_sm[col].dropna()
            if not vals.empty:
                print(f"  [{label}] mean={vals.mean():.4f}  median={vals.median():.4f}")

    rank_corr = df["cs_ml_rank_spearman"].dropna()
    if not rank_corr.empty:
        print(
            f"\n[cs_ml_rank_spearman]  mean={rank_corr.mean():.3f}  "
            f"median={rank_corr.median():.3f}  "
            f"min={rank_corr.min():.3f}  max={rank_corr.max():.3f}"
        )
        worst = df.dropna(subset=["cs_ml_rank_spearman"]).nsmallest(
            5, "cs_ml_rank_spearman"
        )
        print("\n[5 worst cs_ml_rank_spearman months]")
        for _, r in worst.iterrows():
            print(
                f"  {int(r['year'])}/{r['month']}  spearman={r['cs_ml_rank_spearman']:.3f}  "
                f"top10_overlap={r['cs_top10_overlap']:.2f}  "
                f"top20_overlap={r['cs_top20_overlap']:.2f}  "
                f"n_old={int(r['cs_n_old']) if pd.notna(r['cs_n_old']) else 'NA'}  "
                f"n_new={int(r['cs_n_new']) if pd.notna(r['cs_n_new']) else 'NA'}"
            )

    top10 = df["cs_top10_overlap"].dropna()
    if not top10.empty:
        print(
            f"\n[cs_top10_overlap]    mean={top10.mean():.3f}  "
            f"median={top10.median():.3f}  min={top10.min():.3f}  max={top10.max():.3f}"
        )

    jacc = df["tc_symbol_jaccard"].dropna()
    if not jacc.empty:
        print(
            f"\n[tc_symbol_jaccard]   mean={jacc.mean():.3f}  "
            f"median={jacc.median():.3f}  min={jacc.min():.3f}  max={jacc.max():.3f}"
        )

    big_row_diff = df[df["ds_rows_diff_pct"].abs() > 20].sort_values(
        "ds_rows_diff_pct", key=lambda s: s.abs(), ascending=False
    )
    if not big_row_diff.empty:
        print(f"\n[Dataset row diff > 20%]  {len(big_row_diff)} months")
        for _, r in big_row_diff.head(10).iterrows():
            old_n = int(r["ds_rows_old"]) if pd.notna(r["ds_rows_old"]) else "NA"
            new_n = int(r["ds_rows_new"]) if pd.notna(r["ds_rows_new"]) else "NA"
            print(
                f"  {int(r['year'])}/{r['month']}  old={old_n:>5}  new={new_n:>5}  "
                f"diff_pct={r['ds_rows_diff_pct']:+.1f}%"
            )

    bad_months = df[df["notes"].astype(str).str.contains("missing:", na=False)]
    if not bad_months.empty:
        print(f"\n[Missing files]  {len(bad_months)} months have missing artifacts:")
        for _, r in bad_months.head(10).iterrows():
            print(f"  {int(r['year'])}/{r['month']}: {r['notes']}")

    tt_diff = df[df["cs_train_through_match"].astype(str).str.startswith("diff:")]
    if not tt_diff.empty:
        print(
            f"\n[scored_by_train_through differs]  {len(tt_diff)} months  "
            "(walk-forward picked a different model)"
        )
        for _, r in tt_diff.head(10).iterrows():
            print(f"  {int(r['year'])}/{r['month']}: {r['cs_train_through_match']}")


def main() -> None:
    args = parse_args()

    explicit = parse_months_arg(args.months)
    if explicit is not None:
        months = explicit
    else:
        months = scan_months(
            args.old_output_root,
            args.new_output_root,
            args.old_models_root,
            args.new_models_root,
        )

    print(f"Comparing {len(months)} months ...")
    rows = [
        compare_month(
            y,
            m,
            args.old_output_root,
            args.new_output_root,
            args.old_models_root,
            args.new_models_root,
        )
        for (y, m) in months
    ]

    df = pd.DataFrame(rows)
    column_order = [
        "year",
        "month",
        "ds_rows_old",
        "ds_rows_new",
        "ds_rows_diff_pct",
        "ds_cols_added",
        "ds_cols_removed",
        "ds_shared_numeric_mean_abs_diff",
        "tc_n_old",
        "tc_n_new",
        "tc_symbol_jaccard",
        "tc_upside_rank_corr",
        "sm_train_ic_old",
        "sm_train_ic_new",
        "sm_eval_ic_old",
        "sm_eval_ic_new",
        "sm_n_features_old",
        "sm_n_features_new",
        "sm_train_rows_old",
        "sm_train_rows_new",
        "cs_n_old",
        "cs_n_new",
        "cs_top10_overlap",
        "cs_top20_overlap",
        "cs_ml_rank_spearman",
        "cs_train_through_match",
        "notes",
    ]
    df = df.reindex(columns=column_order)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, float_format="%.6f")
    print(f"\nWrote: {args.out}")
    print_summary(df)


if __name__ == "__main__":
    main()
