#!/usr/bin/env python3
"""Publish the active-stocks universe to the My Stock Server API.

Reads ``active_stocks.txt`` (repo root, one symbol per line) and PUTs it to the
server's single global ``/active_stocks`` resource::

    {"symbols": ["1101", "1102", ...]}

``active_stocks.txt`` is regenerated monthly on the 15th by
``scraper/monthly/generate_active_stocks.py``; this pushes the current file.
Called as the last step of ``schedules/monthly_update.sh`` on day 15 — after the
revenue importer, so a push failure never blocks the revenue import. A non-zero
exit propagates through ``set -e`` and trips ``OnFailure=stock-notify@``.

PUT is an idempotent full-replace (set semantics), so re-running is safe.

Usage:
    venv/bin/python3 scripts/publish_active_stocks.py
    venv/bin/python3 scripts/publish_active_stocks.py --dry-run
    STOCK_LIST_API_BASE=http://host:8053 venv/bin/python3 scripts/publish_active_stocks.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_BASE = "http://100.101.183.80:8053"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "active_stocks.txt"


def _http(method: str, url: str, body: dict | None = None, timeout: int = 15):
    """Return (status_code, parsed_json_or_text). Does not raise on 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _parse(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read().decode())


def _parse(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def load_symbols(path: Path) -> list[str]:
    """Return the non-blank, stripped symbol lines from active_stocks.txt."""
    if not path.exists():
        raise FileNotFoundError(f"active stocks file not found: {path}")
    symbols = [s.strip() for s in path.read_text(encoding="utf-8").splitlines()]
    symbols = [s for s in symbols if s]
    if not symbols:
        raise ValueError(f"no symbols in {path}")
    return symbols


def publish(api_base: str, symbols: list[str]) -> None:
    url = f"{api_base.rstrip('/')}/active_stocks"
    status, body = _http("PUT", url, body={"symbols": symbols})
    if not (200 <= status < 300):
        raise RuntimeError(f"PUT {url} -> {status}: {body}")
    print(f"[publish] PUT {url} -> {status} ({len(symbols)} symbols)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--file", type=Path, default=DEFAULT_FILE, help="active_stocks.txt path"
    )
    ap.add_argument(
        "--api-base", default=os.environ.get("STOCK_LIST_API_BASE", DEFAULT_API_BASE)
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print target + count, do not send"
    )
    args = ap.parse_args()

    symbols = load_symbols(args.file)
    url = f"{args.api_base.rstrip('/')}/active_stocks"

    if args.dry_run:
        print(f"[dry-run] target : {url}")
        print(f"[dry-run] source : {args.file}")
        print(
            f"[dry-run] count  : {len(symbols)}  (first={symbols[0]}, last={symbols[-1]})"
        )
        return 0

    publish(args.api_base, symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
