#!/usr/bin/env python3
"""Publish the monthly top-N stock picks to the My Stock Server API.

Reads ``models_selection/<DATE>/candidates_scored.csv`` (produced by
``strategies/step5_score_and_publish.py``), takes the top-N symbols by
``ml_rank``, and upserts them onto the server keyed by the picks' ``entry_date``
(the first trading day after cutoff — the day the list is actually traded).

Idempotent: GETs the target date first; POSTs (create) on 404, PUTs (update)
on 200. Re-running the same playbook overwrites cleanly instead of erroring.

Called as the last step of ``schedules/playbook_run.sh``. A non-zero exit there
propagates through ``set -e`` and trips ``OnFailure=stock-notify@`` (phone push).

Usage:
    venv/bin/python3 scripts/publish_stock_list.py --date 2026-06-11
    venv/bin/python3 scripts/publish_stock_list.py --date 2026-06-11 --dry-run
    STOCK_LIST_API_BASE=http://host:8053 venv/bin/python3 scripts/publish_stock_list.py --date ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

DEFAULT_API_BASE = "http://100.101.183.80:8053"
DEFAULT_TOP_N = 25
REPO_ROOT = Path(__file__).resolve().parent.parent


def _http(method: str, url: str, body: dict | None = None, timeout: int = 15):
    """Return (status_code, parsed_json_or_text). Does not raise on 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, _parse(raw)
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read().decode())


def _parse(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def load_picks(date: str, top_n: int) -> tuple[str, list[str]]:
    """Return (entry_date, [symbols]) for the top-N picks of a playbook date."""
    csv_path = REPO_ROOT / "models_selection" / date / "candidates_scored.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"candidates file not found: {csv_path}")

    # utf-8-sig strips the BOM so the first column is `symbol`, not `﻿symbol`.
    # dtype=str on symbol preserves any leading zeros (e.g. ETF-like 0050).
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"symbol": str})

    for col in ("symbol", "ml_rank", "entry_date"):
        if col not in df.columns:
            raise KeyError(f"{csv_path} missing required column {col!r}")

    df = df.sort_values("ml_rank").head(top_n)

    entry_dates = df["entry_date"].dropna().unique()
    if len(entry_dates) != 1:
        raise ValueError(
            f"expected a single entry_date in top-{top_n}, got {list(entry_dates)}"
        )
    entry_date = str(entry_dates[0])

    symbols = [s.strip() for s in df["symbol"].tolist()]
    if not symbols:
        raise ValueError(f"no symbols in top-{top_n} of {csv_path}")
    return entry_date, symbols


def publish(api_base: str, entry_date: str, symbols: list[str]) -> None:
    y, m, d = (int(x) for x in entry_date.split("-"))
    url = f"{api_base.rstrip('/')}/stock_list/{y}/{m}/{d}"
    body = {"stock_list": symbols}

    status, _ = _http("GET", url)
    if status == 200:
        method = "PUT"  # date already present → overwrite
    elif status == 404:
        method = "POST"  # new date → create
    else:
        raise RuntimeError(f"unexpected GET {url} -> {status}")

    wstatus, wbody = _http(method, url, body=body)
    if not (200 <= wstatus < 300):
        raise RuntimeError(f"{method} {url} -> {wstatus}: {wbody}")
    print(f"[publish] {method} {url} -> {wstatus} ({len(symbols)} symbols)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--date",
        required=True,
        help="playbook date YYYY-MM-DD (models_selection dir name)",
    )
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    ap.add_argument(
        "--api-base", default=os.environ.get("STOCK_LIST_API_BASE", DEFAULT_API_BASE)
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print payload + target URL, do not send"
    )
    args = ap.parse_args()

    entry_date, symbols = load_picks(args.date, args.top_n)
    y, m, d = (int(x) for x in entry_date.split("-"))
    url = f"{args.api_base.rstrip('/')}/stock_list/{y}/{m}/{d}"

    if args.dry_run:
        print(f"[dry-run] target : {url}")
        print(f"[dry-run] entry_date : {entry_date}  (from candidates_scored.csv)")
        print(
            f"[dry-run] payload : {json.dumps({'stock_list': symbols}, ensure_ascii=False)}"
        )
        return 0

    publish(args.api_base, entry_date, symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
