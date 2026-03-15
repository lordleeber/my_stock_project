import os
import pandas as pd

RAW_PATH = "/app/data/raw/stock_info/all.csv"
PROCESSED_DIR = "/app/data/processed/stock_info"


def process_stock_info():
    if not os.path.exists(RAW_PATH):
        print(f"Raw stock info not found: {RAW_PATH}")
        return

    print("Processing stock info...")

    # 讀取 Raw CSV (包含 industry, market, name, symbol)
    df = pd.read_csv(RAW_PATH)

    # 確保 symbol 是字串並補零 (雖然台股通常是 4 位，但保持好習慣)
    df["symbol"] = df["symbol"].astype(str).str.zfill(4)

    # 儲存
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    output_path = os.path.join(PROCESSED_DIR, "all.csv")
    df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"✅ Processed {len(df)} stocks to {output_path}")


if __name__ == "__main__":
    process_stock_info()
