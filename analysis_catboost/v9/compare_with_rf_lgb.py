import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RF_BASE_DIR = Path(__file__).resolve().parents[2] / "analysis_randomForest" / "v9"
LGB_BASE_DIR = Path(__file__).resolve().parents[2] / "analysis_LightGBM" / "v9"


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    ae = np.abs(y_true - y_pred)
    return {
        "mae": float(np.mean(ae)),
        "p90_ae": float(np.quantile(ae, 0.9)),
        "n": int(len(ae)),
    }


def main() -> None:
    rows = []
    for slice_name in ["t1", "t2", "t3"]:
        rf_pred = pd.read_csv(RF_BASE_DIR / slice_name / "results" / "predictions.csv")
        lgb_pred = pd.read_csv(LGB_BASE_DIR / slice_name / "results" / "predictions.csv")
        cat_pred = pd.read_csv(BASE_DIR / slice_name / "results" / "predictions.csv")

        key_cols = ["fold", "symbol"]
        common = (
            rf_pred[key_cols]
            .drop_duplicates()
            .merge(lgb_pred[key_cols].drop_duplicates(), on=key_cols, how="inner")
            .merge(cat_pred[key_cols].drop_duplicates(), on=key_cols, how="inner")
        )

        rf_eval = rf_pred.merge(common, on=key_cols, how="inner")
        lgb_eval = lgb_pred.merge(common, on=key_cols, how="inner")
        cat_eval = cat_pred.merge(common, on=key_cols, how="inner")

        y_true = rf_eval["y_true"].to_numpy(float)
        rows.append({"slice": slice_name, "model": "rf_delta", **metrics(y_true, rf_eval["pred_rf_delta"].to_numpy(float))})
        rows.append({"slice": slice_name, "model": "lgb_delta", **metrics(y_true, lgb_eval["pred_lgb_delta"].to_numpy(float))})
        rows.append({"slice": slice_name, "model": "cat_delta", **metrics(y_true, cat_eval["pred_cat_delta"].to_numpy(float))})
        rows.append({"slice": slice_name, "model": "baseline_q2_eps", **metrics(y_true, rf_eval["pred_baseline_q2_eps"].to_numpy(float))})

    out_df = pd.DataFrame(rows).sort_values(["slice", "model"]).reset_index(drop=True)
    out_df[["mae", "p90_ae"]] = out_df[["mae", "p90_ae"]].round(4)

    out_path = BASE_DIR / "rf_lgb_cat_compare.csv"
    out_df.to_csv(out_path, index=False)

    print(
        json.dumps(
            {
                "output_csv": str(out_path),
                "slices": ["t1", "t2", "t3"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()

