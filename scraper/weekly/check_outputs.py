import datetime
import os
import re
from pathlib import Path


def _append_missing(title, context, missing):
    if not missing:
        return
    error_md = Path("/app/error_scraper.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_md, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {title}\n")
        for line in context:
            f.write(f"{line}\n")
        f.write("Missing files:\n")
        for path in missing:
            f.write(f"- {path}\n")
    print(f"\n[WARN] Missing outputs detected. See: {error_md}")


def _is_file_valid(path: Path, min_bytes: int, min_lines: int) -> bool:
    if not path.exists():
        return False
    try:
        if path.stat().st_size < min_bytes:
            return False
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            line_count = 0
            for _ in f:
                line_count += 1
                if line_count >= min_lines:
                    return True
        return False
    except OSError:
        return False


def _find_latest_tdcc_file(base_dir: Path):
    candidates = list(base_dir.glob("*/TDCC_OD_1-5_*.csv"))
    if not candidates:
        return None

    def _extract_date(path: Path):
        m = re.search(r"TDCC_OD_1-5_(\d{8})\.csv$", path.name)
        return m.group(1) if m else ""

    candidates.sort(key=lambda p: _extract_date(p))
    return candidates[-1]


def check_weekly_outputs(output_dir, tdcc_date=""):
    base_dir = Path(output_dir).resolve() / "raw" / "shareholding"
    min_bytes = int(os.getenv("MIN_BYTES", "10"))
    min_lines = int(os.getenv("MIN_LINES", "2"))

    missing = []
    context = []

    if tdcc_date:
        year = tdcc_date[:4]
        target = base_dir / year / f"TDCC_OD_1-5_{tdcc_date}.csv"
        context.append(f"Date: {tdcc_date}")
        if not _is_file_valid(target, min_bytes, min_lines):
            missing.append(str(target))
    else:
        latest = _find_latest_tdcc_file(base_dir)
        context.append("Date: auto-detect latest")
        if latest is None:
            missing.append(str(base_dir / "<year>/TDCC_OD_1-5_YYYYMMDD.csv"))
        elif not _is_file_valid(latest, min_bytes, min_lines):
            missing.append(str(latest))
        else:
            context.append(f"Latest file: {latest}")

    _append_missing(
        title="scraper-weekly missing outputs",
        context=context,
        missing=missing,
    )


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    tdcc_date = os.getenv("TDCC_DATE", "").strip()

    if tdcc_date and (len(tdcc_date) != 8 or not tdcc_date.isdigit()):
        print(f"[WARN] Invalid TDCC_DATE: {tdcc_date}. Fallback to latest file check.")
        tdcc_date = ""

    check_weekly_outputs(output_dir, tdcc_date)


if __name__ == "__main__":
    main()
