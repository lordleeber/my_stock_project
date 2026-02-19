import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="strategyF: relative-strength filtered strategy grid search")
    parser.add_argument("--candidates", type=Path, default=Path("analysis_randomForest/trading_filter/trade_candidates_2025_1013_1120.csv"))
    parser.add_argument("--quotes-cache", type=Path, default=Path("analysis_randomForest/trading_filter/daily_quotes_20251013_1120_sii.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("analysis_randomForest/trading_filter/strategyF"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("strategyF skeleton ready")
    print(f"- candidates: {args.candidates}")
    print(f"- quotes-cache: {args.quotes_cache}")
    print(f"- output-dir: {args.output_dir}")
    print("TODO: implement relative-strength filters and grid search")


if __name__ == "__main__":
    main()
