import numpy as np
import pandas as pd


def _pick_first_existing(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def get_prev_quarter(q_str):
    year = int(q_str[:4])
    quarter = int(q_str[-1])
    if quarter == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{quarter - 1}"


def get_trailing_quarters(q_str, n=4):
    quarters = [q_str]
    while len(quarters) < n:
        quarters.append(get_prev_quarter(quarters[-1]))
    return quarters


def calculate_ttm_eps(df_income_all):
    """
    Calculate TTM EPS from a quarterly EPS dataframe.

    Required columns:
    - symbol
    - eps_q
    Optional:
    - quarter/date (enables eps_growth calculation)
    """
    if df_income_all.empty:
        return pd.DataFrame(columns=["symbol", "eps_ttm", "eps_growth"])

    df = df_income_all.copy()
    eps_col = _pick_first_existing(df.columns, ["eps_q"])
    quarter_col = _pick_first_existing(df.columns, ["quarter", "date"])
    if "symbol" not in df.columns or eps_col is None:
        return pd.DataFrame(columns=["symbol", "eps_ttm", "eps_growth"])

    df["symbol"] = df["symbol"].astype(str)
    df["eps"] = pd.to_numeric(df[eps_col], errors="coerce")
    if quarter_col is not None and "quarter" not in df.columns:
        df["quarter"] = df[quarter_col].astype(str)

    # Keep only symbols with at least 4 valid EPS rows
    valid = df[df["eps"].notna()].copy()
    counts = valid.groupby("symbol")["eps"].count()
    valid_symbols = counts[counts >= 4].index

    ttm = (
        valid[valid["symbol"].isin(valid_symbols)]
        .groupby("symbol")["eps"]
        .sum()
        .reset_index()
        .rename(columns={"eps": "eps_ttm"})
    )

    ttm["eps_growth"] = np.nan
    if "quarter" in df.columns and not df["quarter"].isna().all():
        dfq = valid[valid["symbol"].isin(valid_symbols)].copy()
        dfq = dfq.sort_values(["symbol", "quarter"], ascending=[True, False])

        latest = dfq.drop_duplicates("symbol")[["symbol", "eps"]].rename(columns={"eps": "eps_latest"})
        yoy_base = dfq.groupby("symbol").nth(3).reset_index()[["symbol", "eps"]].copy()
        yoy_base = yoy_base.rename(columns={"eps": "eps_yoy_base"})

        growth = pd.merge(latest, yoy_base, on="symbol", how="left")
        growth["eps_growth"] = np.where(
            growth["eps_yoy_base"] > 0,
            (growth["eps_latest"] - growth["eps_yoy_base"]) / growth["eps_yoy_base"] * 100,
            np.nan,
        )
        ttm = pd.merge(ttm, growth[["symbol", "eps_growth"]], on="symbol", how="left", suffixes=("", "_new"))
        if "eps_growth_new" in ttm.columns:
            ttm["eps_growth"] = ttm["eps_growth_new"]
            ttm = ttm.drop(columns=["eps_growth_new"])

    return ttm[["symbol", "eps_ttm", "eps_growth"]]


def build_ttm_eps_for_quarter(
    q_str,
    fetch_dataframe_func,
    endpoint="/raw/quarterly-reports",
    limit=3000,
):
    """
    Fetch trailing 4 quarters then calculate TTM EPS.
    """
    trailing_quarters = get_trailing_quarters(q_str, n=4)
    frames = []
    for quarter in trailing_quarters:
        df_tmp = fetch_dataframe_func(
            endpoint,
            {"start_date": quarter, "end_date": quarter, "limit": limit},
        )
        eps_col = _pick_first_existing(df_tmp.columns, ["eps_q"])
        if df_tmp.empty or "symbol" not in df_tmp.columns or eps_col is None:
            continue
        frames.append(df_tmp[["symbol", eps_col]].assign(quarter=quarter))

    if not frames:
        return pd.DataFrame(columns=["symbol", "eps_ttm", "eps_growth"])

    df_eps = pd.concat(frames, ignore_index=True)
    return calculate_ttm_eps(df_eps)


def fetch_pe_ratio_for_date(fetch_dataframe_func, target_date, limit=5000):
    try:
        df = fetch_dataframe_func(
            "/raw/pe-ratio",
            {"start_date": target_date, "end_date": target_date, "limit": limit},
        )
        if df.empty or "symbol" not in df.columns or "pe_ratio" not in df.columns:
            return pd.DataFrame(columns=["symbol", "pe_ratio"])
        df = df[["symbol", "pe_ratio"]].copy()
        df["symbol"] = df["symbol"].astype(str)
        df["pe_ratio"] = pd.to_numeric(df["pe_ratio"], errors="coerce")
        return df.drop_duplicates("symbol")
    except Exception:
        return pd.DataFrame(columns=["symbol", "pe_ratio"])
