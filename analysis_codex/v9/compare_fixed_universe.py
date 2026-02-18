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
    t1 = pd.read_csv(BASE_DIR / "t1" / "results" / "predictions.csv")
    t2 = pd.read_csv(BASE_DIR / "t2" / "results" / "predictions.csv")
    t3 = pd.read_csv(BASE_DIR / "t3" / "results" / "predictions.csv")

    key_cols = ["fold", "symbol"]
    common = (
        t1[key_cols]
        .drop_duplicates()
        .merge(t2[key_cols].drop_duplicates(), on=key_cols, how="inner")
        .merge(t3[key_cols].drop_duplicates(), on=key_cols, how="inner")
    )

    rows = []
    for name, df in [("t1", t1), ("t2", t2), ("t3", t3)]:
        d = df.merge(common, on=key_cols, how="inner")
        m_rf = metrics(d["y_true"].to_numpy(float), d["pred_rf_delta"].to_numpy(float))
        m_bq = metrics(d["y_true"].to_numpy(float), d["pred_baseline_q2_eps"].to_numpy(float))
        rows.append({"slice": name, "model": "rf_delta", **m_rf})
        rows.append({"slice": name, "model": "baseline_q2_eps", **m_bq})

    out_df = pd.DataFrame(rows).sort_values(["model", "slice"]).reset_index(drop=True)
    out_df[["mae", "p90_ae"]] = out_df[["mae", "p90_ae"]].round(4)

    out_path = BASE_DIR / "fixed_universe_compare.csv"
    out_df.to_csv(out_path, index=False)

    print(
        json.dumps(
            {
                "common_rows": int(len(common)),
                "common_folds": sorted(common["fold"].astype(str).unique().tolist()),
                "output_csv": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()
