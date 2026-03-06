from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize backtester monthly results for a year/month range.")
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True)
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True)
    parser.add_argument("--show-monthly", action="store_true", help="print monthly detail rows")
    return parser.parse_args()


def iter_months(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def main() -> None:
    args = parse_args()
    if (args.start_year, args.start_month) > (args.end_year, args.end_month):
        raise ValueError("start range must be <= end range")

    base = (Path.cwd() / "backtester" / "output").resolve()
    rows_main: list[dict] = []
    rows_baseline: list[dict] = []
    missing_main: list[str] = []
    missing_baseline: list[str] = []

    for y, m in iter_months(args.start_year, args.start_month, args.end_year, args.end_month):
        ym = f"{y:04d}-{m:02d}"
        p_main = base / f"{y:04d}" / f"{m:02d}" / "monthly_summary.csv"
        p_base = base / f"{y:04d}" / f"{m:02d}" / "monthly_summary_baseline.csv"

        if p_main.exists():
            df = pd.read_csv(p_main)
            if not df.empty:
                r = df.iloc[0].to_dict()
                r["year"] = y
                r["month"] = m
                r["year_month"] = ym
                rows_main.append(r)
            else:
                missing_main.append(ym)
        else:
            missing_main.append(ym)

        if p_base.exists():
            dfb = pd.read_csv(p_base)
            if not dfb.empty:
                rb = dfb.iloc[0].to_dict()
                rb["year"] = y
                rb["month"] = m
                rb["year_month"] = ym
                rows_baseline.append(rb)
            else:
                missing_baseline.append(ym)
        else:
            missing_baseline.append(ym)

    if not rows_main and not rows_baseline:
        print("No monthly_summary.csv or monthly_summary_baseline.csv found in the given range.")
        return

    print(f"Range: {args.start_year:04d}-{args.start_month:02d} ~ {args.end_year:04d}-{args.end_month:02d}")

    def _print_block(title: str, rows: list[dict], missing: list[str]) -> pd.DataFrame | None:
        print(f"\n[{title}]")
        if not rows:
            print("Months with data: 0")
            if missing:
                print(f"missing_months ({len(missing)}): {', '.join(missing)}")
            return None

        out = pd.DataFrame(rows).sort_values(["year", "month"]).reset_index(drop=True)
        total_capital = float(out["total_capital"].sum())
        gross_pnl = float(out["gross_pnl"].sum())
        total_cost = float(out["total_cost"].sum())
        net_pnl = float(out["net_pnl"].sum())
        return_pct = (net_pnl / total_capital * 100.0) if total_capital > 0 else 0.0
        sold_count = int(out["sold_count"].sum())
        sold_win_count = int(out["sold_win_count"].sum())
        sold_loss_count = int(out["sold_loss_count"].sum())

        print(f"Months with data: {len(out)}")
        print(f"total_capital: {total_capital:,.2f}")
        print(f"gross_pnl: {gross_pnl:,.2f}")
        print(f"total_cost: {total_cost:,.2f}")
        print(f"net_pnl: {net_pnl:,.2f}")
        print(f"return_pct: {return_pct:.4f}%")
        print(f"sold_count: {sold_count} (win={sold_win_count}, loss={sold_loss_count})")
        if missing:
            print(f"missing_months ({len(missing)}): {', '.join(missing)}")
        return out

    out_main = _print_block("Main Strategy", rows_main, missing_main)
    out_base = _print_block("Baseline", rows_baseline, missing_baseline)

    if args.show_monthly:
        print("\n[Monthly]")
        month_keys = sorted(set((r["year"], r["month"]) for r in (rows_main + rows_baseline)))
        main_map = {f"{int(r['year']):04d}-{int(r['month']):02d}": r for r in rows_main}
        base_map = {f"{int(r['year']):04d}-{int(r['month']):02d}": r for r in rows_baseline}
        for y, m in month_keys:
            ym = f"{y:04d}-{m:02d}"
            mrow = main_map.get(ym)
            brow = base_map.get(ym)
            m_text = (
                f"main return={float(mrow['return_pct']):.4f}% net={float(mrow['net_pnl']):,.2f}"
                if mrow is not None
                else "main N/A"
            )
            b_text = (
                f"baseline return={float(brow['return_pct']):.4f}% net={float(brow['net_pnl']):,.2f}"
                if brow is not None
                else "baseline N/A"
            )
            print(f"{ym} | {m_text} | {b_text}")


if __name__ == "__main__":
    main()
