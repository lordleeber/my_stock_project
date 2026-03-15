import requests
import pandas as pd
import os
import argparse
from datetime import datetime
from io import StringIO

FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"


def fetch_market_revenue(year_roc, month, market_type):
    """
    Fetch monthly revenue from MOPS static HTML files.
    market_type: 'sii' (上市) or 'otc' (上櫃)
    """
    # URL pattern: https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{year}_{month}_0.html
    # Note: month does not seem to have leading zeros based on observation (e.g., '3' not '03')
    url = f"https://mopsov.twse.com.tw/nas/t21/{market_type}/t21sc03_{year_roc}_{month}_0.html"

    print(f"Fetching {market_type.upper()} revenue for {year_roc}/{month} from: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # Verify URL existence first (handling redirects)
        res = requests.get(url, headers=headers, allow_redirects=True)
        res.raise_for_status()

        # MOPS usually uses Big5 encoding
        res.encoding = "big5"

        # Check if content looks valid (simple check)
        if "營業收入統計表" not in res.text:
            print(f"⚠️  Warning: Page content for {market_type} might be invalid.")
            return None

        # Pandas read_html is powerful for this
        # match='公司' ensures we only grab tables with company data
        # header=None to manually find the correct header row
        dfs = pd.read_html(StringIO(res.text), match="公司", header=None)

        all_data = []

        # The page contains multiple tables (one per industry). We need to concatenate them.
        for df in dfs:
            # Basic validation
            if df.empty or df.shape[1] < 5:
                continue

            # Find the header row
            header_row_idx = -1
            for i in range(min(5, len(df))):
                # Normalize values: remove newlines and spaces for matching
                row_values_raw = df.iloc[i].astype(str).tolist()
                row_values_norm = [
                    v.replace("\n", "").replace(" ", "") for v in row_values_raw
                ]

                # Check for key columns in this row
                if any("公司代號" in v for v in row_values_norm) and any(
                    "當月營收" in v for v in row_values_norm
                ):
                    header_row_idx = i
                    break

            clean_df = None

            if header_row_idx != -1:
                # Case 1: Header found
                # Set header
                df.columns = df.iloc[header_row_idx]
                df.columns.name = None

                # Slice data (skip header row)
                clean_df = df.iloc[header_row_idx + 1 :].copy()

                # Flatten columns: convert to string, strip whitespace/newlines
                clean_df.columns = [
                    str(c).replace("\n", "").replace(" ", "") for c in clean_df.columns
                ]

            else:
                # Case 2: Header not found, check if it looks like data
                sample_rows = min(5, len(df))
                valid_ids = 0
                for i in range(sample_rows):
                    val = str(df.iloc[i, 0]).strip()
                    # Check if it looks like a stock ID (4 digits)
                    import re

                    if re.match(r"^\d{4}", val):
                        valid_ids += 1

                if valid_ids > 0:
                    clean_df = df.copy()
                    # Assign standard columns if dimensions match
                    # Expected around 11 columns
                    if clean_df.shape[1] >= 10:
                        col_names = [
                            "公司代號",
                            "公司名稱",
                            "當月營收",
                            "上月營收",
                            "去年當月營收",
                            "上月比較增減(%)",
                            "去年同月增減(%)",
                            "當月累計營收",
                            "去年累計營收",
                            "前期比較增減(%)",
                            "備註",
                        ]

                        # Generate new columns list
                        new_cols = []
                        for idx in range(clean_df.shape[1]):
                            if idx < len(col_names):
                                new_cols.append(col_names[idx])
                            else:
                                new_cols.append(f"Unknown_{idx}")

                        clean_df.columns = new_cols
                    else:
                        continue

            if clean_df is None or clean_df.empty:
                continue

            # Additional clean: "公司代號" column should exist and be numeric
            if "公司代號" not in clean_df.columns:
                continue

            # Filter out non-data rows (like "合計")
            # We look for rows where '公司代號' is a number
            clean_df = clean_df[
                clean_df["公司代號"].astype(str).str.match(r"^\d{4}[A-Za-z0-9]*$")
            ]

            if not clean_df.empty:
                all_data.append(clean_df)

        if not all_data:
            print(f"❌ No valid data tables found for {market_type}.")
            return None

        final_df = pd.concat(all_data, ignore_index=True)
        print(f"✅ Parsed {len(final_df)} records for {market_type.upper()}.")
        return final_df

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(
                f"❌ Report not found (404). Data might not be available yet for {year_roc}/{month}."
            )
        else:
            print(f"❌ HTTP Error: {e}")
    except Exception as e:
        print(f"❌ Error fetching/parsing: {e}")

    return None


def process_and_save(year, month):
    year_roc = year - 1911

    df_sii = fetch_market_revenue(year_roc, month, "sii")
    df_otc = fetch_market_revenue(year_roc, month, "otc")

    if df_sii is None and df_otc is None:
        print("No data fetched. Exiting.")
        return

    # Combine
    dfs_to_concat = []
    if df_sii is not None:
        df_sii["market"] = "SII"
        dfs_to_concat.append(df_sii)
    if df_otc is not None:
        df_otc["market"] = "OTC"
        dfs_to_concat.append(df_otc)

    full_df = pd.concat(dfs_to_concat, ignore_index=True)

    # Rename columns to English for the system
    # Mapping based on typical table structure
    col_map = {
        "公司代號": "symbol",
        "公司名稱": "name",
        "當月營收": "revenue",
        "上月營收": "revenue_last_month",
        "去年當月營收": "revenue_last_year",
        "上月比較增減(%)": "mom_pct",
        "去年同月增減(%)": "yoy_pct",
        "當月累計營收": "revenue_acc",
        "去年累計營收": "revenue_acc_last_year",
        "前期比較增減(%)": "acc_yoy_pct",
        "備註": "comment",
    }

    # Flexible renaming (some columns might have slightly different names due to OCR/Parsing nuances if headers change)
    # But read_html usually preserves text well.
    # We strip whitespace from columns just in case
    full_df.columns = [c.strip().replace("\n", "") for c in full_df.columns]

    # Handle potentially slightly different column names (e.g. '上月比較\n增減(%)')
    # Let's do a fuzzy match or just trust the strip() above handles the newlines seen in the HTML raw output

    full_df.rename(columns=col_map, inplace=True)

    # Keep only mapped columns + market
    target_cols = list(col_map.values()) + ["market"]
    # Check intersection to allow for missing 'comment' etc
    available_cols = [c for c in target_cols if c in full_df.columns]
    full_df = full_df[available_cols]

    # Convert numeric columns
    numeric_cols = [
        "revenue",
        "revenue_last_month",
        "revenue_last_year",
        "mom_pct",
        "yoy_pct",
        "revenue_acc",
        "revenue_acc_last_year",
        "acc_yoy_pct",
    ]

    for col in numeric_cols:
        if col in full_df.columns:
            # Remove commas and convert to numeric, coercing errors to NaN
            full_df[col] = pd.to_numeric(
                full_df[col].astype(str).str.replace(",", ""), errors="coerce"
            )

    # Save
    # New raw path format: data/raw/monthly_revenue/YYYY/YYYYMXX/tmp.csv
    year_str = str(year)
    month_key = f"{year}M{month:02d}"
    output_dir = f"data/raw/monthly_revenue/{year_str}/{month_key}"
    os.makedirs(output_dir, exist_ok=True)

    tmp_path = os.path.join(output_dir, "tmp.csv")
    # Always overwrite tmp.csv; this is the latest daily snapshot.
    full_df.to_csv(tmp_path, index=False)
    print(f"\n✅ Saved {len(full_df)} records to: {tmp_path}")
    print(f"Sample:\n{full_df[['symbol', 'name', 'revenue', 'yoy_pct']].head()}")

    # Merge tmp snapshot into accumulated market.csv, preserving first publish_time.
    publish_time = os.getenv("PUBLISH_TIME", "").strip() or datetime.now().strftime(
        "%Y%m%d"
    )
    full_df["publish_time"] = publish_time

    market_path = os.path.join(output_dir, "market.csv")
    key_cols = ["market", "symbol"]
    if os.path.exists(market_path):
        market_df = pd.read_csv(market_path)
        if (
            "publish_date" in market_df.columns
            and "publish_time" not in market_df.columns
        ):
            market_df = market_df.rename(columns={"publish_date": "publish_time"})
        existing_keys = set(
            market_df[key_cols].astype(str).agg("||".join, axis=1).tolist()
        )
    else:
        market_df = pd.DataFrame(columns=list(full_df.columns))
        existing_keys = set()

    full_df["_key"] = full_df[key_cols].astype(str).agg("||".join, axis=1)
    new_rows = full_df[~full_df["_key"].isin(existing_keys)].drop(columns=["_key"])

    if len(new_rows) > 0:
        merged_df = pd.concat([market_df, new_rows], ignore_index=True)
        merged_df.to_csv(market_path, index=False)
        print(
            f"✅ Appended {len(new_rows)} new rows to: {market_path} (publish_time={publish_time})"
        )
    else:
        if not os.path.exists(market_path):
            full_df.drop(columns=["_key"]).to_csv(market_path, index=False)
        print(
            f"✅ No new rows to append. market.csv unchanged (publish_time={publish_time})"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch monthly revenue from MOPS (mopsov)."
    )
    parser.add_argument(
        "--year", type=int, help="Year (AD), e.g., 2023", required=False
    )
    parser.add_argument("--month", type=int, help="Month (1-12)", required=False)

    args = parser.parse_args()

    # Default to current month - 1 (last month's revenue) if not specified
    # Or asking user to be specific is safer.

    if args.year and args.month:
        process_and_save(args.year, args.month)
    else:
        # Default behavior: interactive or last month?
        # Let's prompt or default to previous month
        today = datetime.now()
        # If today is Jan 2026, we want Dec 2025.
        if today.month == 1:
            target_year = today.year - 1
            target_month = 12
        else:
            target_year = today.year
            target_month = today.month - 1

        print(
            f"No date specified. Defaulting to last month: {target_year}/{target_month}"
        )
        process_and_save(target_year, target_month)
