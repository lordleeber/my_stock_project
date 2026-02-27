import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate and publish monthly EPS model")
    parser.add_argument("--market", type=str, required=True, choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    parser.add_argument("--models-root", type=Path, default=Path("models_eps"))
    parser.add_argument("--eval-file", type=Path, default=None, help="預設 <month-dir>/results/evaluate_by_fold.csv")
    parser.add_argument("--model-file", type=Path, default=None, help="預設 <month-dir>/model.pkl")
    parser.add_argument("--metric", type=str, default="mae")
    parser.add_argument("--primary-model", type=str, default="lgb_delta")
    parser.add_argument("--baseline-model", type=str, default="baseline_anchor_eps")
    parser.add_argument("--max-ratio", type=float, default=0.975, help="primary <= baseline * max_ratio 才通過")
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    month_name = str(args.month).zfill(2)
    if month_name < "01" or month_name > "12":
        raise ValueError("--month 必須是 01~12")
    month_dir = (Path.cwd() / "train_eps" / args.market / str(args.year) / month_name).resolve()
    eval_file = args.eval_file if args.eval_file else month_dir / "results" / "evaluate_by_fold.csv"
    model_file = args.model_file if args.model_file else month_dir / "model.pkl"
    models_root = args.models_root if args.models_root.is_absolute() else (Path.cwd() / args.models_root).resolve()
    return month_dir, eval_file, model_file, models_root


def main() -> None:
    args = parse_args()
    month_dir, eval_file, model_file, models_root = resolve_paths(args)
    market = args.market
    year = str(args.year)
    month_name = str(args.month).zfill(2)

    if not eval_file.exists():
        raise FileNotFoundError(f"evaluate file not found: {eval_file}")
    if not model_file.exists():
        raise FileNotFoundError(f"model file not found: {model_file}")

    df = pd.read_csv(eval_file)
    if args.metric not in df.columns:
        raise ValueError(f"metric '{args.metric}' not found in {eval_file}")

    # 只比較主要模型與 baseline
    use = df[df["model"].isin([args.primary_model, args.baseline_model])].copy()
    if use.empty:
        raise RuntimeError("no rows for primary/baseline models in evaluate file")

    folds = int(use["fold"].nunique())
    if folds < args.min_folds:
        raise RuntimeError(f"insufficient folds: {folds} < {args.min_folds}")

    metric_mean = use.groupby("model", as_index=False)[args.metric].mean()
    metric_map = {r["model"]: float(r[args.metric]) for _, r in metric_mean.iterrows()}

    if args.primary_model not in metric_map or args.baseline_model not in metric_map:
        raise RuntimeError("primary/baseline metric missing after aggregation")

    primary_val = metric_map[args.primary_model]
    baseline_val = metric_map[args.baseline_model]
    threshold = baseline_val * float(args.max_ratio)
    passed = primary_val <= threshold

    result = {
        "month_dir": str(month_dir),
        "evaluate_file": str(eval_file),
        "model_file": str(model_file),
        "metric": args.metric,
        "primary_model": args.primary_model,
        "baseline_model": args.baseline_model,
        "primary_metric": primary_val,
        "baseline_metric": baseline_val,
        "max_ratio": float(args.max_ratio),
        "threshold": threshold,
        "folds": folds,
        "passed": bool(passed),
        "dry_run": bool(args.dry_run),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 先寫一份 gate 結果在月份資料夾，方便追蹤
    gate_out = month_dir / "gate_result.json"
    gate_out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if not passed:
        print("gate failed")
        print(json.dumps(result, indent=2))
        return

    if args.dry_run:
        print("gate passed (dry-run, not published)")
        print(json.dumps(result, indent=2))
        return

    target_dir = models_root / market / year / month_name
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    published_model = target_dir / f"{ts}.pkl"
    published_meta = target_dir / f"{ts}.json"

    shutil.copy2(model_file, published_model)

    # 同步保存發布時的評估摘要
    meta_payload = dict(result)
    meta_payload.update(
        {
            "published_model": str(published_model),
            "source_train_metrics": str(month_dir / "train_metrics.json"),
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

