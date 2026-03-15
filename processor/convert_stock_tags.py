import os
import pandas as pd

RAW_DIR = "/app/data/raw/stock_tags"
INFO_PATH = "/app/data/processed/stock_info/all.csv"
PROCESSED_DIR = "/app/data/processed/stock_tags"


def process_stock_tags():
    all_tags = []

    # 1. 嘗試讀取 MoneyDJ 抓取的標籤 (如果有的話)
    raw_path = os.path.join(RAW_DIR, "all.csv")
    if os.path.exists(raw_path):
        print(f"Reading tags from {raw_path}")
        df_raw = pd.read_csv(raw_path)
        all_tags.append(df_raw[["symbol", "tag"]])

    # 2. 自動從 stock_info 的 industry 欄位生成初始標籤 (保底數據)
    if os.path.exists(INFO_PATH):
        print("Generating initial tags from industry info...")
        df_info = pd.read_csv(INFO_PATH)
        df_ind = df_info[["symbol", "industry"]].rename(columns={"industry": "tag"})
        all_tags.append(df_ind)

    if not all_tags:
        print("No tag data found to process.")
        return

    # 合併並去重
    final_df = pd.concat(all_tags, ignore_index=True)
    final_df["symbol"] = final_df["symbol"].astype(str).str.zfill(4)
    final_df = final_df.drop_duplicates()

    # 儲存
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    output_path = os.path.join(PROCESSED_DIR, "all.csv")
    final_df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"✅ Processed {len(final_df)} stock-tag mappings to {output_path}")


if __name__ == "__main__":
    process_stock_tags()
