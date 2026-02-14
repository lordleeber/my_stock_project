import datetime
import os
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _build_url(start_date: str, end_date: str) -> str:
    return (
        "https://www.twse.com.tw/rwd/zh/change/TWTB8U"
        f"?startDate={start_date}&endDate={end_date}&response=csv"
    )


def fetch_year_to_date(end_date: str, output_dir: str) -> None:
    end_dt = datetime.datetime.strptime(end_date, "%Y%m%d")
    start_date = f"{end_dt.year}0101"

    dst_dir = Path(output_dir) / "raw" / "par_value_change" / f"{end_dt.year}"
    dst_dir.mkdir(parents=True, exist_ok=True)

    cp950_path = dst_dir / "cp950.csv"
    utf8_path = dst_dir / "all.csv"
    force_reprocess = os.getenv("FORCE_REPROCESS", "0") == "1"

    if utf8_path.exists() and not force_reprocess:
        print(f"[PAR_VALUE_CHANGE] {utf8_path} exists, skip.")
        return

    url = _build_url(start_date, end_date)
    try:
        print(f"Fetching PAR_VALUE_CHANGE {start_date}~{end_date}...")
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"[PAR_VALUE_CHANGE] Failed. Status code: {resp.status_code}")
            return

        if not resp.content:
            print("[PAR_VALUE_CHANGE] Empty response.")
            return

        cp950_path.write_bytes(resp.content)
        text = resp.content.decode("cp950", errors="ignore")
        utf8_path.write_text(text, encoding="utf-8")
        print(f"[PAR_VALUE_CHANGE] Saved: {utf8_path}")
    except Exception as exc:
        print(f"[PAR_VALUE_CHANGE] Error: {exc}")


def run_scraper(end_date: str, output_dir: str) -> None:
    fetch_year_to_date(end_date, output_dir)


if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "data")
    end_date_env = os.getenv("END_DATE") or datetime.datetime.today().strftime("%Y%m%d")
    run_scraper(end_date_env, output_dir)
