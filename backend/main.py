import os
import pickle
import datetime
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pydantic import BaseModel

app = FastAPI()

# 設定 CORS (允許前端存取)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生產環境建議設為具體的前端網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

# 定義回傳資料模型
class StockQuote(BaseModel):
    date: datetime.date
    market: str
    symbol: str
    name: str
    close: float
    volume: float
    change: Optional[float] = None

class MAQuote(BaseModel):
    date: datetime.date
    symbol: str
    name: str
    close: float
    volume: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma240: Optional[float] = None

class VMAQuote(BaseModel):
    date: datetime.date
    symbol: str
    name: str
    close: float
    volume: float
    vma5: Optional[float] = None
    vma10: Optional[float] = None
    vma20: Optional[float] = None
    vma60: Optional[float] = None
    vma120: Optional[float] = None
    vma240: Optional[float] = None

class VolumeBreakoutQuote(BaseModel):
    date: datetime.date
    symbol: str
    name: str
    close: float
    volume: float
    vma10: float
    ratio: float

# --- Backtest Models ---
class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    strategy_mode: str = "shares" # shares or amount
    capital: float = 100000
    hold_days: int = 3
    allow_pyramiding: bool = True
    only_red_candle: bool = False
    take_profit_pct: float = 0.0
    stop_loss_pct: float = 0.0

class TradeRecord(BaseModel):
    symbol: str
    name: str
    buy_date: datetime.date
    sell_date: datetime.date
    buy_price: float
    sell_price: float
    shares: int
    profit: float
    return_rate: float

class BacktestSummary(BaseModel):
    total_trades: int
    total_profit: float
    total_cost: float
    roi: float
    win_rate: float
    avg_return: float

class BacktestResult(BaseModel):
    summary: BacktestSummary
    trades: List[TradeRecord]

# --- Scanner Models ---

class VolumeSpikeResult(BaseModel):
    symbol: str
    name: str
    date: datetime.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_ratio: float
    distance_from_high_pct: Optional[float] = None
    upper_shadow_ratio: Optional[float] = None
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    k: Optional[float] = None
    d: Optional[float] = None
    rsi6: Optional[float] = None
    rsi12: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None

class CandlestickData(BaseModel):
    date: datetime.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None

class InstitutionalData(BaseModel):
    date: datetime.date
    foreign_net: float
    trust_net: float
    foreign_held_shares: Optional[float] = None
    trust_held_shares: Optional[float] = None

class MLTrainingData(BaseModel):
    date: datetime.date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma240: Optional[float] = None
    vma5: Optional[float] = None
    vma10: Optional[float] = None
    vma20: Optional[float] = None
    vma60: Optional[float] = None
    k: Optional[float] = None
    d: Optional[float] = None
    rsi6: Optional[float] = None
    rsi12: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    foreign_streak_days: Optional[int] = None
    trust_streak_days: Optional[int] = None
    dealer_streak_days: Optional[int] = None
    foreign_net: Optional[float] = None
    trust_net: Optional[float] = None
    dealer_net: Optional[float] = None
    foreign_held_shares: Optional[float] = None
    trust_held_shares: Optional[float] = None
    large_holder_ratio: Optional[float] = None
    small_holder_ratio: Optional[float] = None
    concentration_spread: Optional[float] = None
    large_holder_ratio_wow: Optional[float] = None
    small_holder_ratio_wow: Optional[float] = None
    concentration_spread_wow: Optional[float] = None

# --- Raw Data Models ---
class DailyQuoteRaw(BaseModel):
    date: str  # 改為字串以確保一致
    symbol: str
    name: str
    market: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    value: Optional[float] = None
    transactions: Optional[float] = None
    change: Optional[float] = None
    direction: Optional[str] = None
    bid: Optional[str] = None  # Stored as text in database
    ask: Optional[str] = None  # Stored as text in database

class MarginTradingRaw(BaseModel):
    date: str  # Stored as text in database
    symbol: str
    market: str
    name: Optional[str] = None
    margin_long_buy: Optional[float]
    margin_long_sell: Optional[float]
    margin_long_cash_repay: Optional[float]
    margin_long_prev_balance: Optional[float] = None
    margin_long_balance: Optional[float]
    margin_long_limit: Optional[float]
    margin_short_buy: Optional[float]
    margin_short_sell: Optional[float]
    margin_short_cash_repay: Optional[float]
    margin_short_prev_balance: Optional[float] = None
    margin_short_balance: Optional[float]
    margin_short_limit: Optional[float]
    offset_balance: Optional[float] = None

class MarginSummaryRaw(BaseModel):
    date: str  # Stored as text (consistent with all other tables)
    market: str
    item: str
    buy: Optional[float]
    sell: Optional[float]
    cash_repay: Optional[float]
    prev_balance: Optional[float]
    today_balance: Optional[float]

class InstitutionalInvestorsRaw(BaseModel):
    date: str
    symbol: str
    name: Optional[str] = None
    market: str
    foreign_buy: Optional[float] = None
    foreign_sell: Optional[float] = None
    foreign_net: Optional[float] = None
    trust_buy: Optional[float] = None
    trust_sell: Optional[float] = None
    trust_net: Optional[float] = None
    dealer_buy: Optional[float] = None
    dealer_sell: Optional[float] = None
    dealer_net: Optional[float] = None
    dealer_self_buy: Optional[float] = None
    dealer_self_sell: Optional[float] = None
    dealer_self_net: Optional[float] = None
    dealer_hedge_buy: Optional[float] = None
    dealer_hedge_sell: Optional[float] = None
    dealer_hedge_net: Optional[float] = None

class InstitutionalSummaryRaw(BaseModel):
    date: str
    market: str
    institution: str
    buy: Optional[float] = None
    sell: Optional[float] = None
    net: Optional[float] = None

class ForeignHoldingRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    issued_shares: Optional[float] = None
    foreign_investable_shares: Optional[float] = None
    foreign_held_shares: Optional[float] = None
    foreign_investable_ratio: Optional[float] = None
    foreign_held_ratio: Optional[float] = None
    foreign_legal_limit_ratio: Optional[float] = None

class TrustHoldingRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    issued_shares: Optional[float] = None
    trust_held_shares: Optional[float] = None
    trust_held_ratio: Optional[float] = None

class DealerHoldingRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    issued_shares: Optional[float] = None
    dealer_held_shares: Optional[float] = None
    dealer_held_ratio: Optional[float] = None

class PeRatioRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    dividend_year: Optional[int] = None
    pb_ratio: Optional[float] = None

class MarketIndexRaw(BaseModel):
    date: str
    symbol: str
    name: str
    market: str
    close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None

class MonthlyRevenueRaw(BaseModel):
    date: str  # Format: YYYYMXX (e.g. 2025M01)
    symbol: str
    market: str
    name: Optional[str] = None
    revenue_current: Optional[float]
    revenue_last_month: Optional[float]
    revenue_last_year: Optional[float]
    mom_pct: Optional[float]
    yoy_pct: Optional[float]
    revenue_cumulative: Optional[float] = None
    revenue_cumulative_last_year: Optional[float] = None
    cumulative_yoy_pct: Optional[float] = None
    publish_time: Optional[str] = None

class StockInfoRaw(BaseModel):
    symbol: str
    name: str
    industry: str
    market: str
    listing_date: Optional[str] = None
    tags: Optional[List[str]] = None

class StockTagRaw(BaseModel):
    symbol: str
    tag: str

class ShareholdingRaw(BaseModel):
    date: str
    symbol: str
    level: int
    level_name: Optional[str] = None
    holders: Optional[float]
    shares: Optional[float]
    percentage: Optional[float]

class ShareholdingConcentrationRaw(BaseModel):
    date: str
    symbol: str
    large_holder_ratio: Optional[float] = None
    small_holder_ratio: Optional[float] = None
    concentration_spread: Optional[float] = None
    large_holder_count: Optional[float] = None
    small_holder_count: Optional[float] = None
    large_holder_ratio_wow: Optional[float] = None
    small_holder_ratio_wow: Optional[float] = None
    concentration_spread_wow: Optional[float] = None

class ShortInterestAnalysisRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    sbl_balance: Optional[float] = None
    sbl_balance_wow: Optional[float] = None
    sbl_balance_wow_pct: Optional[float] = None
    sbl_sell: Optional[float] = None
    sbl_repay: Optional[float] = None
    sbl_sell_repay_ratio: Optional[float] = None
    margin_short_balance: Optional[float] = None
    margin_short_balance_wow: Optional[float] = None
    margin_short_balance_wow_pct: Optional[float] = None
    short_pressure_score: Optional[float] = None

class MarginPressureAnalysisRaw(BaseModel):
    date: str
    symbol: str
    market: str
    name: Optional[str] = None
    margin_long_balance: Optional[float] = None
    margin_long_limit: Optional[float] = None
    margin_usage_ratio: Optional[float] = None
    margin_long_balance_wow: Optional[float] = None
    margin_long_balance_wow_pct: Optional[float] = None
    margin_short_balance: Optional[float] = None
    margin_short_limit: Optional[float] = None
    short_usage_ratio: Optional[float] = None
    margin_short_balance_wow: Optional[float] = None
    margin_short_balance_wow_pct: Optional[float] = None
    short_cover_pressure: Optional[float] = None
    margin_pressure_score: Optional[float] = None

class QuarterlyReportRaw(BaseModel):
    date: str  # Format: YYYYQX (e.g. 2025Q1)
    symbol: str
    market: str
    name: Optional[str] = None
    # Profitability (Quarterly / Accumulated)
    revenue_q: Optional[float] = None
    revenue_acc: Optional[float] = None
    revenue_acc_ly: Optional[float] = None
    revenue_acc_yoy: Optional[float] = None
    op_income_q: Optional[float] = None
    op_income_acc: Optional[float] = None
    op_income_acc_ly: Optional[float] = None
    op_income_acc_yoy: Optional[float] = None
    non_op_income_q: Optional[float] = None
    non_op_income_acc: Optional[float] = None
    non_op_income_acc_ly: Optional[float] = None
    non_op_income_acc_yoy: Optional[float] = None
    pretax_income_q: Optional[float] = None
    pretax_income_acc: Optional[float] = None
    pretax_income_acc_ly: Optional[float] = None
    pretax_income_acc_yoy: Optional[float] = None
    net_income_q: Optional[float] = None
    net_income_acc: Optional[float] = None
    net_income_acc_ly: Optional[float] = None
    net_income_acc_yoy: Optional[float] = None
    eps_q: Optional[float] = None
    eps_acc: Optional[float] = None
    eps_acc_ly: Optional[float] = None
    eps_acc_yoy: Optional[float] = None
    # Financial Condition
    capital: Optional[float] = None
    nav_per_share: Optional[float] = None
    equity_to_assets_ratio: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None

class IncomeStatementRaw(BaseModel):
    date: str
    market: str
    symbol: str
    name: Optional[str] = None
    statement_type: Optional[str] = None
    revenue_q: Optional[float] = None
    revenue_acc: Optional[float] = None
    cost_of_revenue_q: Optional[float] = None
    cost_of_revenue_acc: Optional[float] = None
    gross_profit_q: Optional[float] = None
    gross_profit_acc: Optional[float] = None
    operating_expense_q: Optional[float] = None
    operating_expense_acc: Optional[float] = None
    operating_income_q: Optional[float] = None
    operating_income_acc: Optional[float] = None
    non_operating_income_q: Optional[float] = None
    non_operating_income_acc: Optional[float] = None
    pretax_income_q: Optional[float] = None
    pretax_income_acc: Optional[float] = None
    tax_expense_q: Optional[float] = None
    tax_expense_acc: Optional[float] = None
    net_income_q: Optional[float] = None
    net_income_acc: Optional[float] = None
    other_comprehensive_income_q: Optional[float] = None
    other_comprehensive_income_acc: Optional[float] = None
    comprehensive_income_q: Optional[float] = None
    comprehensive_income_acc: Optional[float] = None
    eps_q: Optional[float] = None
    eps_acc: Optional[float] = None
    net_interest_income_q: Optional[float] = None
    net_interest_income_acc: Optional[float] = None
    non_interest_income_q: Optional[float] = None
    non_interest_income_acc: Optional[float] = None
    net_revenue_q: Optional[float] = None
    net_revenue_acc: Optional[float] = None
    other_income_net_q: Optional[float] = None
    other_income_net_acc: Optional[float] = None

class BalanceSheetRaw(BaseModel):
    date: str
    market: str
    symbol: str
    name: Optional[str] = None
    statement_type: Optional[str] = None
    current_assets: Optional[float] = None
    noncurrent_assets: Optional[float] = None
    total_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    noncurrent_liabilities: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    equity_parent: Optional[float] = None
    share_capital: Optional[float] = None
    capital_surplus: Optional[float] = None
    retained_earnings: Optional[float] = None
    other_equity: Optional[float] = None
    treasury_shares: Optional[float] = None
    nav_per_share: Optional[float] = None

class CashFlowRaw(BaseModel):
    date: str
    market: str
    symbol: str
    name: Optional[str] = None
    statement_type: Optional[str] = None
    cash_flow_operating_q: Optional[float] = None
    cash_flow_operating_acc: Optional[float] = None
    cash_flow_investing_q: Optional[float] = None
    cash_flow_investing_acc: Optional[float] = None
    cash_flow_financing_q: Optional[float] = None
    cash_flow_financing_acc: Optional[float] = None
    fx_effect_q: Optional[float] = None
    fx_effect_acc: Optional[float] = None
    net_cash_change_q: Optional[float] = None
    net_cash_change_acc: Optional[float] = None
    cash_begin: Optional[float] = None
    cash_end: Optional[float] = None

class XbrlStatementRaw(BaseModel):
    date: str
    symbol: str
    publish_time: Optional[str] = None
    period: Optional[str] = None
    period_type: Optional[str] = None
    account_code: Optional[str] = None
    account_name_cht: Optional[str] = None
    account_name_eng: Optional[str] = None
    value_text: Optional[str] = None

class DividendRaw(BaseModel):
    date: str
    symbol: str
    name: str
    close_before: Optional[float] = None
    ref_price: Optional[float] = None
    rights_dividend_value: Optional[float] = None
    type: Optional[str] = None

class ValuationAnalysisRaw(BaseModel):
    date: str
    symbol: str
    close: Optional[float] = None
    ttm_eps: Optional[float] = None
    pe_ratio_calculated: Optional[float] = None
    pe_ratio_from_pe_table: Optional[float] = None
    pe_percentile: Optional[float] = None

@app.get("/")
def read_root():
    return {"message": "Stock Analysis API is running"}

# --- Raw Data Endpoints ---

@app.get("/raw/dividend", response_model=List[DividendRaw])
def get_raw_dividend(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    """取得除權除息資料"""
    return get_raw_data("dividend", start_date, end_date, symbol, None, limit, offset)

def get_raw_data(
    table: str,
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    """通用原始資料查詢邏輯"""
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        params = {"start": start_date, "end": end_date, "limit": limit, "offset": offset}
        where_clauses = ["date >= :start", "date <= :end"]
        
        if symbol:
            params["symbol"] = symbol
            where_clauses.append("symbol = :symbol")
        if market:
            params["market"] = market
            where_clauses.append("market = :market")
            
        with engine.connect() as conn:
            # 先獲取表格的所有欄位名稱
            column_query = text(f"SELECT * FROM {table} LIMIT 0")
            table_columns = conn.execute(column_query).keys()
            
            # 動態建立 ORDER BY
            order_by = "date DESC"
            if "symbol" in table_columns:
                order_by += ", symbol ASC"
                
            sql = text(f"""
                SELECT * FROM {table}
                WHERE {" AND ".join(where_clauses)}
                ORDER BY {order_by}
                LIMIT :limit OFFSET :offset
            """)
            
            df = pd.read_sql(sql, conn, params=params)
        
        if df.empty:
            return []
        
        # 統一日期格式為 YYYY-MM-DD 字串，處理 NaT
        # 註：季報、財報與月營收使用 YYYYQX/YYYYMXX 格式，應跳過轉換
        periodic_tables = [
            "quarterly_reports",
            "income_statement",
            "balance_sheet",
            "cash_flow",
            "income_statement_xbrl",
            "balance_sheet_xbrl",
            "cash_flow_xbrl",
            "monthly_revenue",
        ]
        if 'date' in df.columns and table not in periodic_tables:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df['date'] = df['date'].where(df['date'].notnull(), None)
        
        # 確保 symbol 是字串
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str)
        return _to_clean_records(df)

    except Exception as e:
        print(f"Raw Data Error ({table}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _to_clean_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """將 DataFrame 轉為 JSON 友善 dict list。"""
    raw_list = df.to_dict(orient="records")
    clean_list = []
    for row in raw_list:
        clean_row = {}
        for k, v in row.items():
            # 使用 np.isfinite 處理所有 numpy/python 數值型態，並排除 NaN/Inf
            if isinstance(v, (float, np.floating)) and not np.isfinite(v):
                clean_row[k] = None
            elif pd.isna(v):  # 處理 pandas.NA 或其他缺失值
                clean_row[k] = None
            else:
                clean_row[k] = v
        clean_list.append(clean_row)
    return clean_list


XBRL_TABLE_TO_STATEMENT_TYPE = {
    "income_statement_xbrl": "income_statement",
    "balance_sheet_xbrl": "balance_sheet",
    "cash_flow_xbrl": "cash_flow",
}


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        ).scalar()
    )


def _get_table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalars().all()
    return set(rows)


def get_raw_xbrl_data(
    table: str,
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
):
    """XBRL 專用查詢：補 account_name_cht/account_name_eng，並僅回傳 value_text。"""
    try:
        statement_type = XBRL_TABLE_TO_STATEMENT_TYPE.get(table)
        if not statement_type:
            raise ValueError(f"Unsupported xbrl table: {table}")

        db_url = get_db_url()
        engine = create_engine(db_url)

        params = {"start": start_date, "end": end_date, "limit": limit, "offset": offset}
        where_clauses = ["x.date >= :start", "x.date <= :end"]
        if symbol:
            params["symbol"] = symbol
            where_clauses.append("x.symbol = :symbol")

        with engine.connect() as conn:
            if _table_exists(conn, "xbrl_codebook"):
                codebook_columns = _get_table_columns(conn, "xbrl_codebook")
                cht_expr = "cb.account_name_cht" if "account_name_cht" in codebook_columns else (
                    "cb.account_name_zh" if "account_name_zh" in codebook_columns else "NULL"
                )
                eng_expr = "cb.account_name_eng" if "account_name_eng" in codebook_columns else (
                    "cb.account_name_en" if "account_name_en" in codebook_columns else "NULL"
                )
                join_conditions = ["cb.account_code = x.account_code"]
                if "statement_type" in codebook_columns:
                    join_conditions.append("cb.statement_type = :statement_type")
                    params["statement_type"] = statement_type

                sql = text(
                    f"""
                    SELECT
                        x.date,
                        x.symbol,
                        x.publish_time,
                        x.period,
                        x.period_type,
                        x.account_code,
                        {cht_expr} AS account_name_cht,
                        {eng_expr} AS account_name_eng,
                        x.value_text
                    FROM {table} x
                    LEFT JOIN xbrl_codebook cb
                        ON {' AND '.join(join_conditions)}
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY x.date DESC, x.symbol ASC, x.account_code ASC
                    LIMIT :limit OFFSET :offset
                    """
                )
            else:
                sql = text(
                    f"""
                    SELECT
                        x.date,
                        x.symbol,
                        x.publish_time,
                        x.period,
                        x.period_type,
                        x.account_code,
                        NULL AS account_name_cht,
                        NULL AS account_name_eng,
                        x.value_text
                    FROM {table} x
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY x.date DESC, x.symbol ASC, x.account_code ASC
                    LIMIT :limit OFFSET :offset
                    """
                )

            df = pd.read_sql(sql, conn, params=params)

        if df.empty:
            return []

        output_cols = [
            "date",
            "symbol",
            "publish_time",
            "period",
            "period_type",
            "account_code",
            "account_name_cht",
            "account_name_eng",
            "value_text",
        ]
        for col in output_cols:
            if col not in df.columns:
                df[col] = None
        df = df[output_cols]

        for col in output_cols:
            if col in df.columns:
                df[col] = df[col].where(df[col].notna(), None)
        if "symbol" in df.columns:
            df["symbol"] = df["symbol"].astype(str)

        return _to_clean_records(df)

    except Exception as e:
        print(f"Raw Data Error ({table}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/raw/stock-info", response_model=List[StockInfoRaw])
def get_raw_stock_info(
    symbol: Optional[str] = None,
    industry: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    """取得股票基本資料與產業分類"""
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        params = {"limit": limit, "offset": offset}
        where_clauses = []
        
        if symbol:
            params["symbol"] = symbol
            where_clauses.append("s.symbol = :symbol")
        if industry:
            params["industry"] = industry
            where_clauses.append("s.industry = :industry")
        if market:
            params["market"] = market.lower()
            where_clauses.append("s.market = :market")
            
        # 使用 LEFT JOIN 並透過 array_agg 合併標籤
        sql_text = """
            SELECT 
                s.symbol, s.name, s.industry, s.market, s.listing_date,
                array_agg(t.tag) FILTER (WHERE t.tag IS NOT NULL) as tags
            FROM stock_info s
            LEFT JOIN stock_tags t ON s.symbol = t.symbol
        """
        
        if where_clauses:
            sql_text += " WHERE " + " AND ".join(where_clauses)
            
        sql_text += " GROUP BY s.symbol, s.name, s.industry, s.market, s.listing_date"
        sql_text += " ORDER BY s.symbol ASC LIMIT :limit OFFSET :offset"
        
        with engine.connect() as conn:
            df = pd.read_sql(text(sql_text), conn, params=params)
        
        # 處理 DataFrame 中的 tags (SQL 回傳的是 list)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/raw/stock-tags", response_model=List[StockTagRaw])
def get_raw_stock_tags(
    symbol: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    """取得股票標籤對照 (symbol, tag)"""
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)

        params = {"limit": limit, "offset": offset}
        where_clauses = []
        if symbol:
            params["symbol"] = symbol
            where_clauses.append("symbol = :symbol")
        if tag:
            params["tag"] = tag
            where_clauses.append("tag = :tag")

        sql_text = "SELECT symbol, tag FROM stock_tags"
        if where_clauses:
            sql_text += " WHERE " + " AND ".join(where_clauses)
        sql_text += " ORDER BY symbol ASC, tag ASC LIMIT :limit OFFSET :offset"

        with engine.connect() as conn:
            df = pd.read_sql(text(sql_text), conn, params=params)

        if df.empty:
            return []
        df["symbol"] = df["symbol"].astype(str)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/raw/daily-quotes", response_model=List[DailyQuoteRaw])
def get_raw_quotes(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("daily_quotes", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/margin-trading", response_model=List[MarginTradingRaw])
def get_raw_margin_trading(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("margin_trading", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/margin-summary", response_model=List[MarginSummaryRaw])
def get_raw_margin_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("margin_summary", start_date, end_date, None, market, limit, offset)

@app.get("/raw/institutional-investors", response_model=List[InstitutionalInvestorsRaw])
def get_raw_institutional(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("institutional_investors", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/institutional-summary", response_model=List[InstitutionalSummaryRaw])
def get_raw_institutional_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("institutional_summary", start_date, end_date, None, market, limit, offset)

@app.get("/raw/foreign-holding", response_model=List[ForeignHoldingRaw])
def get_raw_foreign_holding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("foreign_holding", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/trust-holding", response_model=List[TrustHoldingRaw])
def get_raw_trust_holding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("trust_holding", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/dealer-holding", response_model=List[DealerHoldingRaw])
def get_raw_dealer_holding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("dealer_holding", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/pe-ratio", response_model=List[PeRatioRaw])
def get_raw_pe_ratio(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("pe_ratio", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/valuation-analysis", response_model=List[ValuationAnalysisRaw])
def get_raw_valuation_analysis(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("valuation_analysis", start_date, end_date, symbol, None, limit, offset)

@app.get("/raw/market-indices", response_model=List[MarketIndexRaw])
def get_raw_market_indices(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("market_indices", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/monthly-revenue", response_model=List[MonthlyRevenueRaw])
def get_raw_monthly_revenue(
    start_date: str = Query(..., description="Format: YYYYMXX (e.g. 2025M01) or YYYY-MM-DD"),
    end_date: str = Query(..., description="Format: YYYYMXX"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    # 如果是 YYYYMXX 格式則直接傳入，否則保持原樣
    return get_raw_data("monthly_revenue", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/shareholding", response_model=List[ShareholdingRaw])
def get_raw_shareholding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("shareholding", start_date, end_date, symbol, None, limit, offset)

@app.get("/raw/shareholding-concentration", response_model=List[ShareholdingConcentrationRaw])
def get_raw_shareholding_concentration(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("shareholding_concentration", start_date, end_date, symbol, None, limit, offset)

@app.get("/raw/short-interest-analysis", response_model=List[ShortInterestAnalysisRaw])
def get_raw_short_interest_analysis(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("short_interest_analysis", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/margin-pressure-analysis", response_model=List[MarginPressureAnalysisRaw])
def get_raw_margin_pressure_analysis(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    return get_raw_data("margin_pressure_analysis", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/quarterly-reports", response_model=List[QuarterlyReportRaw])
def get_raw_quarterly_reports(
    start_date: str = Query(..., description="Format: YYYYQX (e.g. 2020Q1)"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    """
    Fetch quarterly financial reports.
    Note: Date filtering for this endpoint uses 'YYYYQX' string format (e.g. '2020Q1'), not YYYY-MM-DD.
    """
    import re
    q_pattern = re.compile(r"^\d{4}Q[1-4]$")
    if not q_pattern.match(start_date) or not q_pattern.match(end_date):
        raise HTTPException(
            status_code=400, 
            detail="Invalid date format. Quarterly reports require 'YYYYQX' format (e.g., 2025Q1)."
        )
    return get_raw_data("quarterly_reports", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/income-statements", response_model=List[IncomeStatementRaw])
def get_raw_income_statements(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_data("income_statement", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/balance-sheets", response_model=List[BalanceSheetRaw])
def get_raw_balance_sheets(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_data("balance_sheet", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/cash-flows", response_model=List[CashFlowRaw])
def get_raw_cash_flows(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_data("cash_flow", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/income-statements-xbrl", response_model=List[XbrlStatementRaw])
def get_raw_income_statements_xbrl(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_xbrl_data("income_statement_xbrl", start_date, end_date, symbol, limit, offset)

@app.get("/raw/balance-sheets-xbrl", response_model=List[XbrlStatementRaw])
def get_raw_balance_sheets_xbrl(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_xbrl_data("balance_sheet_xbrl", start_date, end_date, symbol, limit, offset)

@app.get("/raw/cash-flows-xbrl", response_model=List[XbrlStatementRaw])
def get_raw_cash_flows_xbrl(
    start_date: str = Query(..., description="Format: YYYYQX"),
    end_date: str = Query(..., description="Format: YYYYQX"),
    symbol: Optional[str] = None,
    limit: int = Query(1000, gt=0, le=5000),
    offset: int = Query(0, ge=0)
):
    import re
    if not re.match(r"^\d{4}Q[1-4]$", start_date) or not re.match(r"^\d{4}Q[1-4]$", end_date):
        raise HTTPException(status_code=400, detail="Dates must be in format YYYYQX")
    return get_raw_xbrl_data("cash_flow_xbrl", start_date, end_date, symbol, limit, offset)

# @app.get("/scanner/volume-spike", response_model=List[VolumeSpikeResult])
# def get_volume_spike_scanner(
#     date: str = Query(..., description="Scan date in YYYY-MM-DD format"),
#     min_volume: int = Query(5000000, description="Minimum volume threshold"),
#     volume_ratio: float = Query(4.0, description="Volume spike ratio vs average"),
#     avg_days: int = Query(10, description="Days for average volume calculation"),
#     filter_long_shadow: bool = Query(True, description="Filter long upper shadow candles")
# ):
#     """
#     Run volume spike scanner for a specific date
#     Returns stocks with significant volume breakouts
#     """
#     try:
#         from scanner.volume_spike_scanner import scan_volume_spike

#         df = scan_volume_spike(
#             scan_date=date,
#             min_volume=min_volume,
#             volume_ratio=volume_ratio,
#             avg_days=avg_days,
#             filter_long_shadow=filter_long_shadow
#         )

#         if df.empty:
#             return []

#         results = []
#         for _, row in df.iterrows():
#             results.append(VolumeSpikeResult(
#                 symbol=row['symbol'],
#                 name=row['name'],
#                 date=row['date'],
#                 open=float(row['open']),
#                 high=float(row['high']),
#                 low=float(row['low']),
#                 close=float(row['close']),
#                 volume=float(row['volume']),
#                 volume_ratio=float(row['volume_ratio']),
#                 distance_from_high_pct=float(row['distance_from_high_pct']) if pd.notna(row['distance_from_high_pct']) else None,
#                 upper_shadow_ratio=float(row['upper_shadow_ratio']) if pd.notna(row['upper_shadow_ratio']) else None,
#                 ma5=float(row['ma5']) if pd.notna(row['ma5']) else None,
#                 ma10=float(row['ma10']) if pd.notna(row['ma10']) else None,
#                 ma20=float(row['ma20']) if pd.notna(row['ma20']) else None,
#                 ma60=float(row['ma60']) if pd.notna(row['ma60']) else None,
#                 k=float(row['k']) if pd.notna(row['k']) else None,
#                 d=float(row['d']) if pd.notna(row['d']) else None,
#                 rsi6=float(row['rsi6']) if pd.notna(row['rsi6']) else None,
#                 rsi12=float(row['rsi12']) if pd.notna(row['rsi12']) else None,
#                 macd_dif=float(row['macd_dif']) if pd.notna(row['macd_dif']) else None,
#                 macd_dea=float(row['macd_dea']) if pd.notna(row['macd_dea']) else None
#             ))

#         return results

#     except Exception as e:
#         print(f"Scanner Error: {e}")
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=str(e))

@app.get("/scanner/candlestick/{symbol}", response_model=List[CandlestickData])
def get_candlestick_data(
    symbol: str,
    date: str = Query(..., description="Center date in YYYY-MM-DD format"),
    days_before: int = Query(30, description="Days before center date"),
    days_after: int = Query(10, description="Days after center date")
):
    """
    Get candlestick chart data for a specific stock around a date
    """
    try:
        from datetime import timedelta

        center_date = datetime.datetime.strptime(date, '%Y-%m-%d')
        start_date = (center_date - timedelta(days=days_before)).strftime('%Y-%m-%d')
        end_date = (center_date + timedelta(days=days_after)).strftime('%Y-%m-%d')

        db_url = get_db_url()
        engine = create_engine(db_url)

        sql = text("""
            SELECT dq.date, dq.open, dq.high, dq.low, dq.close, dq.volume,
                   ti.ma5, ti.ma10, ti.ma20, ti.ma60
            FROM daily_quotes dq
            LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date
            WHERE dq.symbol = :symbol
              AND dq.date >= :start_date
              AND dq.date <= :end_date
            ORDER BY dq.date
        """)

        with engine.connect() as conn:
            result = conn.execute(sql, {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        if not result:
            return []

        candlestick_data = []
        for row in result:
            if row.open is None or row.high is None or row.low is None or row.close is None or row.volume is None:
                continue
            candlestick_data.append(CandlestickData(
                date=row.date,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                ma5=float(row.ma5) if row.ma5 is not None else None,
                ma10=float(row.ma10) if row.ma10 is not None else None,
                ma20=float(row.ma20) if row.ma20 is not None else None,
                ma60=float(row.ma60) if row.ma60 is not None else None
            ))

        return candlestick_data

    except Exception as e:
        print(f"Candlestick Data Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scanner/institutional/{symbol}", response_model=List[InstitutionalData])
def get_institutional_data(
    symbol: str,
    date: str = Query(..., description="Center date in YYYY-MM-DD format"),
    days_before: int = Query(90, description="Days before center date"),
    days_after: int = Query(90, description="Days after center date")
):
    """Get institutional investor net buy/sell data for a specific stock around a date"""
    try:
        from datetime import timedelta

        center_date = datetime.datetime.strptime(date, '%Y-%m-%d')
        start_date = (center_date - timedelta(days=days_before)).strftime('%Y-%m-%d')
        end_date = (center_date + timedelta(days=days_after)).strftime('%Y-%m-%d')

        db_url = get_db_url()
        engine = create_engine(db_url)

        sql = text("""
            WITH cumulative AS (
                SELECT ii.date, ii.foreign_net, ii.trust_net, fh.foreign_held_shares,
                       SUM(ii.trust_net) OVER (ORDER BY ii.date) AS trust_held_shares
                FROM institutional_investors ii
                LEFT JOIN foreign_holding fh ON ii.symbol = fh.symbol AND ii.date = fh.date
                WHERE ii.symbol = :symbol
            )
            SELECT * FROM cumulative
            WHERE date >= :start_date AND date <= :end_date
            ORDER BY date
        """)

        with engine.connect() as conn:
            result = conn.execute(sql, {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        if not result:
            return []

        data = []
        for row in result:
            if row.foreign_net is None and row.trust_net is None:
                continue
            data.append(InstitutionalData(
                date=row.date,
                foreign_net=float(row.foreign_net) if row.foreign_net is not None else 0,
                trust_net=float(row.trust_net) if row.trust_net is not None else 0,
                foreign_held_shares=float(row.foreign_held_shares) if row.foreign_held_shares is not None else None,
                trust_held_shares=float(row.trust_held_shares) if row.trust_held_shares is not None else None
            ))

        return data

    except Exception as e:
        print(f"Institutional Data Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health_check():
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        return {"status": "ok", "db_connection": "success", "result": result}
    except Exception as e:
        return {"status": "error", "db_connection": "failed", "detail": str(e)}

@app.get("/quotes/top-volume", response_model=List[StockQuote])
def get_top_volume(
    date: str = Query(..., description="Date in YYYY-MM-DD or YYYYMMDD format"), 
    limit: int = 10,
    sort: str = Query("desc", description="Sort order: asc or desc")
):
    if len(date) == 8 and date.isdigit():
        date_str = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    else:
        date_str = date

    sort_order = "ASC" if sort.lower() == "asc" else "DESC"

    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        sql = text(f"""
            SELECT date, market, symbol, name, close, volume, change
            FROM daily_quotes
            WHERE date = :date 
            ORDER BY volume {sort_order}
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date_str, "limit": limit}).fetchall()
            
        if not result:
            return []
            
        quotes = []
        for row in result:
            quotes.append(StockQuote(
                date=row.date,
                market=row.market,
                symbol=row.symbol,
                name=row.name,
                close=float(row.close) if row.close is not None else 0.0,
                volume=float(row.volume) if row.volume is not None else 0.0,
                change=float(row.change) if row.change is not None else None
            ))
            
        return quotes

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analysis/ma", response_model=List[MAQuote])
def get_ma_data(
    date: str = Query(..., description="Date in YYYY-MM-DD"), 
    limit: int = 10,
    sort: str = Query("desc", description="Sort by volume: asc or desc")
):
    if len(date) == 8 and date.isdigit():
        date_str = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    else:
        date_str = date

    sort_order = "ASC" if sort.lower() == "asc" else "DESC"

    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        sql = text(f"""
            SELECT t.date, t.symbol, d.name, d.close, d.volume, 
                   t.ma5, t.ma10, t.ma20, t.ma60, t.ma120, t.ma240
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date = :date AND d.volume > 0
            ORDER BY d.volume {sort_order}
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date_str, "limit": limit}).fetchall()
            
        return [
            MAQuote(
                date=row.date,
                symbol=row.symbol,
                name=row.name,
                close=float(row.close),
                volume=float(row.volume),
                ma5=float(row.ma5) if row.ma5 is not None else None,
                ma10=float(row.ma10) if row.ma10 is not None else None,
                ma20=float(row.ma20) if row.ma20 is not None else None,
                ma60=float(row.ma60) if row.ma60 is not None else None,
                ma120=float(row.ma120) if row.ma120 is not None else None,
                ma240=float(row.ma240) if row.ma240 is not None else None
            ) for row in result
        ]

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analysis/vma", response_model=List[VMAQuote])
def get_vma_data(
    date: str = Query(..., description="Date in YYYY-MM-DD"), 
    limit: int = 10,
    sort: str = Query("desc", description="Sort by volume: asc or desc")
):
    if len(date) == 8 and date.isdigit():
        date_str = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    else:
        date_str = date

    sort_order = "ASC" if sort.lower() == "asc" else "DESC"

    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        sql = text(f"""
            SELECT t.date, t.symbol, d.name, d.close, d.volume, 
                   t.vma5, t.vma10, t.vma20, t.vma60, t.vma120, t.vma240
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date = :date AND d.volume > 0
            ORDER BY d.volume {sort_order}
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date_str, "limit": limit}).fetchall()
            
        return [
            VMAQuote(
                date=row.date,
                symbol=row.symbol,
                name=row.name,
                close=float(row.close),
                volume=float(row.volume),
                vma5=float(row.vma5) if row.vma5 is not None else None,
                vma10=float(row.vma10) if row.vma10 is not None else None,
                vma20=float(row.vma20) if row.vma20 is not None else None,
                vma60=float(row.vma60) if row.vma60 is not None else None,
                vma120=float(row.vma120) if row.vma120 is not None else None,
                vma240=float(row.vma240) if row.vma240 is not None else None
            ) for row in result
        ]

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ml/training-data", response_model=List[MLTrainingData])
def get_ml_training_data(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD"),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
    include_indicators: bool = Query(True, description="Include indicators"),
    include_institutional: bool = Query(True, description="Include institutional")
):
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)

        select_fields = ["dq.date", "dq.symbol", "dq.open", "dq.high", "dq.low", "dq.close", "dq.volume"]
        if include_indicators:
            select_fields.extend(["ti.ma5", "ti.ma10", "ti.ma20", "ti.ma60", "ti.ma120", "ti.ma240",
                                "ti.vma5", "ti.vma10", "ti.vma20", "ti.vma60",
                                "ti.k", "ti.d", "ti.rsi6", "ti.rsi12", "ti.macd_dif", "ti.macd_dea",
                                "ti.foreign_streak_days", "ti.trust_streak_days", "ti.dealer_streak_days"])
        if include_institutional:
            select_fields.extend(["ii.foreign_net", "ii.trust_net", "ii.dealer_net", "fh.foreign_held_shares",
                                "SUM(ii.trust_net) OVER (PARTITION BY dq.symbol ORDER BY dq.date) AS trust_held_shares",
                                "shc.large_holder_ratio", "shc.small_holder_ratio", "shc.concentration_spread",
                                "shc.large_holder_ratio_wow", "shc.small_holder_ratio_wow", "shc.concentration_spread_wow"])

        joins = []
        if include_indicators:
            joins.append("LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date")
        if include_institutional:
            joins.append("LEFT JOIN institutional_investors ii ON dq.symbol = ii.symbol AND dq.date = ii.date")
            joins.append("LEFT JOIN foreign_holding fh ON dq.symbol = fh.symbol AND dq.date = fh.date")
            joins.append(
                "LEFT JOIN LATERAL ("
                "  SELECT sc.large_holder_ratio, sc.small_holder_ratio, sc.concentration_spread, "
                "         sc.large_holder_ratio_wow, sc.small_holder_ratio_wow, sc.concentration_spread_wow "
                "  FROM shareholding_concentration sc "
                "  WHERE sc.symbol = dq.symbol AND sc.date <= dq.date "
                "  ORDER BY sc.date DESC "
                "  LIMIT 1"
                ") shc ON TRUE"
            )

        params = {"start_date": start_date, "end_date": end_date}
        where = ["dq.date >= :start_date", "dq.date <= :end_date"]
        if symbols:
            s_list = [s.strip() for s in symbols.split(",")]
            placeholders = ", ".join([f":s{i}" for i in range(len(s_list))])
            where.append(f"dq.symbol IN ({placeholders})")
            for i, s in enumerate(s_list):
                params[f"s{i}"] = s

        query = text(f"SELECT {', '.join(select_fields)} FROM daily_quotes dq {' '.join(joins)} WHERE {' AND '.join(where)} ORDER BY dq.date, dq.symbol")

        with engine.connect() as conn:
            result = conn.execute(query, params).fetchall()

        data = []
        for row in result:
            record = {"date": row.date, "symbol": row.symbol, "open": float(row.open), "high": float(row.high),
                      "low": float(row.low), "close": float(row.close), "volume": float(row.volume)}
            if include_indicators:
                record.update({k: float(getattr(row, k)) if getattr(row, k) is not None else None 
                             for k in ["ma5", "ma10", "ma20", "ma60", "ma120", "ma240", "vma5", "vma10", "vma20", "vma60",
                                       "k", "d", "rsi6", "rsi12", "macd_dif", "macd_dea"]})
                record.update({k: int(getattr(row, k)) if getattr(row, k) is not None else None
                             for k in ["foreign_streak_days", "trust_streak_days", "dealer_streak_days"]})
            if include_institutional:
                record.update({k: float(getattr(row, k)) if getattr(row, k) is not None else None 
                             for k in ["foreign_net", "trust_net", "dealer_net", "foreign_held_shares", "trust_held_shares",
                                       "large_holder_ratio", "small_holder_ratio", "concentration_spread",
                                       "large_holder_ratio_wow", "small_holder_ratio_wow", "concentration_spread_wow"]})
            data.append(MLTrainingData(**record))
        return data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quotes/volume-breakout", response_model=List[VolumeBreakoutQuote])
def get_volume_breakout(
    date: str = Query(..., description="Date in YYYY-MM-DD"),
    min_volume: int = 1000000,
    ratio: float = 3.0,
    limit: int = 20
):
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        sql = text("""
            SELECT t.date, t.symbol, d.name, d.close, d.volume, t.vma10,
                   (d.volume / NULLIF(t.vma10, 0)) as ratio
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date = :date AND d.volume >= :min_volume AND (d.volume / NULLIF(t.vma10, 0)) >= :ratio
            ORDER BY ratio DESC LIMIT :limit
        """)
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date, "min_volume": min_volume, "ratio": ratio, "limit": limit}).fetchall()
        return [VolumeBreakoutQuote(date=row.date, symbol=row.symbol, name=row.name, close=float(row.close),
                                   volume=float(row.volume), vma10=float(row.vma10), ratio=float(row.ratio)) for row in result]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# ML Selection Scoring
# ---------------------------------------------------------------------------

class ScoredStock(BaseModel):
    ml_rank: int
    ml_score: float
    symbol: str
    name: Optional[str] = None
    pred_upside_pct: Optional[float] = None
    pe_current: Optional[float] = None
    ttm_eps: Optional[float] = None
    volume_lots: Optional[float] = None
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    net_pnl: Optional[float] = None
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
    """Return pre-scored stocks from candidates_scored.csv (pre-computed by ML pipeline)."""
    try:
        app_dir = Path(__file__).resolve().parent  # /app in Docker, backend/ locally
        # In Docker: models_selection mounted at /app/models_selection
        # Locally: models_selection is at project root (parent of backend/)
        models_selection_dir = app_dir / "models_selection"
        if not models_selection_dir.exists():
            models_selection_dir = app_dir.parent / "models_selection"

        month_str = f"{month:02d}"
        scored_path = models_selection_dir / f"{year:04d}" / month_str / "candidates_scored.csv"
        if not scored_path.exists():
            raise HTTPException(status_code=404, detail=f"candidates_scored.csv not found for {year}/{month_str}")

        ds = pd.read_csv(scored_path)
        ds["symbol"] = ds["symbol"].astype(str)
        ds = ds.sort_values("ml_rank").reset_index(drop=True)
        model_used = f"pre-computed {year}/{month_str}"

        # Join with rolling_trades for entry/exit price and net_pnl
        trades_path = app_dir / "backtester" / "output" / "rolling" / "rolling_trades.csv"
        if not trades_path.exists():
            trades_path = app_dir.parent / "backtester" / "output" / "rolling" / "rolling_trades.csv"
        trades_lookup: dict = {}
        if trades_path.exists():
            trades = pd.read_csv(trades_path)
            trades["symbol"] = trades["symbol"].astype(str)
            for _, t in trades.iterrows():
                trades_lookup[(t["symbol"], t["entry_date"])] = t

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
            sym = str(row["symbol"])
            entry_date = str(row["entry_date"]) if pd.notna(row.get("entry_date")) else None
            trade = trades_lookup.get((sym, entry_date), {})
            results.append(ScoredStock(
                ml_rank=int(row["ml_rank"]),
                ml_score=float(row["ml_score"]),
                symbol=sym,
                name=str(row["name"]) if pd.notna(row.get("name")) else None,
                pred_upside_pct=_opt_float(row, "pred_upside_pct"),
                pe_current=_opt_float(row, "pe_current"),
                ttm_eps=_opt_float(row, "ttm_eps"),
                volume_lots=_opt_float(row, "volume_lots"),
                entry_date=entry_date,
                entry_price=_opt_float(trade, "entry_price"),
                exit_date=str(trade["exit_date"]) if trade.get("exit_date") and pd.notna(trade.get("exit_date")) else None,
                exit_price=_opt_float(trade, "exit_price"),
                net_pnl=_opt_float(trade, "net_pnl"),
                model_used=model_used,
            ))
        return results

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
