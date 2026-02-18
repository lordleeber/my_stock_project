import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    ae = np.abs(y_true - y_pred)
    return {
        "mae": float(np.mean(ae)),
        "p90_ae": float(np.quantile(ae, 0.9)),
        "n": int(len(ae)),
    }


def main() -> None:
    t1_path = BASE_DIR / "t1" / "results" / "predictions.csv"
    t2_path = BASE_DIR / "t2" / "results" / "predictions.csv"
    t3_path = BASE_DIR / "t3" / "results" / "predictions.csv"

    t1 = pd.read_csv(t1_path)
    t2 = pd.read_csv(t2_path)
    t3 = pd.read_csv(t3_path)

    key_cols = ["fold", "symbol"]
    k1 = t1[key_cols].drop_duplicates()
    k2 = t2[key_cols].drop_duplicates()
    k3 = t3[key_cols].drop_duplicates()

    common_keys = k1.merge(k2, on=key_cols, how="inner").merge(k3, on=key_cols, how="inner")

    t1c = t1.merge(common_keys, on=key_cols, how="inner").copy()
    t2c = t2.merge(common_keys, on=key_cols, how="inner").copy()
    t3c = t3.merge(common_keys, on=key_cols, how="inner").copy()

    out_rows = []
    for name, df in [("t1", t1c), ("t2", t2c), ("t3", t3c)]:
        m_rf = metrics(df["y_true"].to_numpy(dtype=float), df["pred_rf_delta"].to_numpy(dtype=float))
        m_bq = metrics(df["y_true"].to_numpy(dtype=float), df["pred_baseline_q2_eps"].to_numpy(dtype=float))
        out_rows.append(
            {
                "slice": name,
                "model": "rf_delta",
                "mae": m_rf["mae"],
                "p90_ae": m_rf["p90_ae"],
                "n": m_rf["n"],
            }
        )
        out_rows.append(
            {
                "slice": name,
                "model": "baseline_q2_eps",
                "mae": m_bq["mae"],
                "p90_ae": m_bq["p90_ae"],
                "n": m_bq["n"],
            }
        )

    out_df = pd.DataFrame(out_rows).sort_values(["model", "slice"]).reset_index(drop=True)
    out_df[["mae", "p90_ae"]] = out_df[["mae", "p90_ae"]].round(4)

    out_path = BASE_DIR / "fixed_universe_compare.csv"
    out_df.to_csv(out_path, index=False)

    summary = {
        "common_rows": int(len(common_keys)),
        "common_folds": sorted(common_keys["fold"].astype(str).unique().tolist()),
        "output_csv": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()
