import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In Cloud Run: GCS bucket mounted at /mnt/data via gcsfuse volume mount
# Locally: project root (two levels up from this file)
DATA_ROOT = Path(os.getenv("DATA_ROOT", "/mnt/data"))


class ScoredStock(BaseModel):
    ml_rank: int
    ml_score: float
    symbol: str
    name: Optional[str] = None
    pred_upside_pct: Optional[float] = None
    pe_current: Optional[float] = None
    close: Optional[float] = None
    entry_date: Optional[str] = None
    model_used: str


def _resolve_model_for_month(models_root: Path, year: int, month: int) -> Optional[Path]:
    """Return model dir with latest cutoff strictly before (year, month).
    Falls back to models_root/latest if no versioned model found."""
    ym = year * 100 + month
    best_ym: Optional[int] = None
    best_path: Optional[Path] = None

    for y_dir in sorted(models_root.iterdir()):
        if not y_dir.is_dir() or y_dir.name == "latest":
            continue
        try:
            y = int(y_dir.name)
        except ValueError:
            continue
        for m_dir in sorted(y_dir.iterdir()):
            if not m_dir.is_dir():
                continue
            try:
                m = int(m_dir.name)
            except ValueError:
                continue
            cutoff_ym = y * 100 + m
            if cutoff_ym < ym and (m_dir / "selection_model.pkl").exists():
                if best_ym is None or cutoff_ym > best_ym:
                    best_ym = cutoff_ym
                    best_path = m_dir

    if best_path:
        return best_path
    latest = models_root / "latest"
    return latest if (latest / "selection_model.pkl").exists() else None


@app.get("/selection/score", response_model=List[ScoredStock])
def get_selection_score(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
):
    try:
        month_str = f"{month:02d}"
        ds_path = DATA_ROOT / "strategies" / "output" / f"{year:04d}" / month_str / "dataset_strategy.csv"
        if not ds_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"dataset_strategy.csv not found for {year}/{month_str}",
            )

        models_root = DATA_ROOT / "models_selection"
        model_dir = _resolve_model_for_month(models_root, year, month)
        if model_dir is None:
            raise HTTPException(status_code=404, detail="No selection model found")

        model_used = "latest" if model_dir.name == "latest" else f"{model_dir.parent.name}/{model_dir.name}"

        with open(model_dir / "selection_model.pkl", "rb") as f:
            payload = pickle.load(f)
        model = payload["model"]
        feature_cols = payload["feature_cols"]

        ds = pd.read_csv(ds_path)
        for c in feature_cols:
            if c not in ds.columns:
                ds[c] = 0.0
        X = ds[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        ds = ds.copy()
        ds["ml_score"] = model.predict(X)
        ds = ds.sort_values("ml_score", ascending=False).reset_index(drop=True)
        ds["ml_rank"] = ds.index + 1

        def _opt_float(row, col):
            v = row.get(col)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return None
            try:
                return float(v)
            except Exception:
                return None

        results = []
        for _, row in ds.iterrows():
            results.append(ScoredStock(
                ml_rank=int(row["ml_rank"]),
                ml_score=float(row["ml_score"]),
                symbol=str(row["symbol"]),
                name=str(row["name"]) if pd.notna(row.get("name")) else None,
                pred_upside_pct=_opt_float(row, "pred_upside_pct"),
                pe_current=_opt_float(row, "pe_current"),
                close=_opt_float(row, "close"),
                entry_date=str(row["entry_date"]) if pd.notna(row.get("entry_date")) else None,
                model_used=model_used,
            ))
        return results

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
