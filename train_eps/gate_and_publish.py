import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

MODELS_ROOT = Path("models_eps")
METRIC = "mae"
PRIMARY_MODEL = "lgb_delta"
BASELINE_MODEL = "baseline_anchor_eps"
MAX_RATIO = 0.99  # Gate passes only if primary_metric <= baseline_metric * MAX_RATIO.
MIN_FOLDS = 1  # Require at least this many distinct evaluation folds before gating/publishing.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate and publish monthly EPS model")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    month_name = str(args.month).zfill(2)
    if month_name < "01" or month_name > "12":
        raise ValueError("--month 必須是 01~12")
    month_dir = (Path.cwd() / "train_eps" / "output" / str(args.year) / month_name).resolve()
    eval_file = month_dir / "results_eval" / "evaluate_by_fold.json"
    model_file = month_dir / "results_train" / "model.pkl"
    models_root = (Path.cwd() / MODELS_ROOT).resolve()
    return month_dir, eval_file, model_file, models_root


def main() -> None:
    args = parse_args()
    month_dir, eval_file, model_file, models_root = resolve_paths(args)
    year = str(args.year)
    month_name = str(args.month).zfill(2)

    if not eval_file.exists():
        raise FileNotFoundError(f"evaluate file not found: {eval_file}")
    if not model_file.exists():
        raise FileNotFoundError(f"model file not found: {model_file}")

    with eval_file.open("r", encoding="utf-8") as f:
        df = pd.DataFrame(json.load(f))
    if METRIC not in df.columns:
        raise ValueError(f"metric '{METRIC}' not found in {eval_file}")

    # 只比較主要模型與 baseline
    use = df[df["model"].isin([PRIMARY_MODEL, BASELINE_MODEL])].copy()
    if use.empty:
        raise RuntimeError("no rows for primary/baseline models in evaluate file")

    folds = int(use["fold"].nunique())
    if folds < MIN_FOLDS:
        raise RuntimeError(f"insufficient folds: {folds} < {MIN_FOLDS}")

    metric_mean = use.groupby("model", as_index=False)[METRIC].mean()
    metric_map = {r["model"]: float(r[METRIC]) for _, r in metric_mean.iterrows()}

    if PRIMARY_MODEL not in metric_map or BASELINE_MODEL not in metric_map:
        raise RuntimeError("primary/baseline metric missing after aggregation")

    primary_val = metric_map[PRIMARY_MODEL]
    baseline_val = metric_map[BASELINE_MODEL]
    threshold = baseline_val * float(MAX_RATIO)
    passed = primary_val <= threshold

    result = {
        "month_dir": str(month_dir),
        "evaluate_file": str(eval_file),
        "model_file": str(model_file),
        "metric": METRIC,
        "primary_model": PRIMARY_MODEL,
        "baseline_model": BASELINE_MODEL,
        "primary_metric": primary_val,
        "baseline_metric": baseline_val,
        "max_ratio": float(MAX_RATIO),
        "threshold": threshold,
        "folds": folds,
        "passed": bool(passed),
        "dry_run": False,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 先寫一份 gate 結果在月份資料夾，方便追蹤
    gate_out = month_dir / "results_gate" / "gate_result.json"
    gate_out.parent.mkdir(parents=True, exist_ok=True)
    gate_out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if not passed:
        print("gate failed")
        print(json.dumps(result, indent=2))
        return

    target_dir = models_root / year / month_name
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    primary_metric_text = f"{primary_val:.6f}".rstrip("0").rstrip(".")
    filename_stem = f"{ts}_{primary_metric_text}"
    published_model = target_dir / f"{filename_stem}.pkl"
    published_meta = target_dir / f"{filename_stem}.json"

    shutil.copy2(model_file, published_model)

    # 同步保存發布時的評估摘要
    meta_payload = dict(result)
    meta_payload.update(
        {
            "published_model": str(published_model),
            "source_train_metrics": str(month_dir / "results_train" / "train_metrics.json"),
            "source_evaluate_by_fold": str(eval_file),
        }
    )
    published_meta.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    # 寫 latest 方便服務端直接讀最新模型
    latest_meta = target_dir / "latest.json"
    latest_meta.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    print("gate passed and published")
    print(json.dumps(meta_payload, indent=2))


if __name__ == "__main__":
    main()
