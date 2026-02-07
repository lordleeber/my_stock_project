import os
import datetime
import numpy as np
import pandas as pd
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
    foreign_net: Optional[float] = None
    trust_net: Optional[float] = None
    dealer_net: Optional[float] = None
    foreign_held_shares: Optional[float] = None
    trust_held_shares: Optional[float] = None

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
    pe_ratio: Optional[float] = None

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
    date: str
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

class ShareholdingRaw(BaseModel):
    date: str
    symbol: str
    level: int
    level_name: Optional[str] = None
    holders: Optional[float]
    shares: Optional[float]
    percentage: Optional[float]

@app.get("/")
def read_root():
    return {"message": "Stock Analysis API is running"}

# --- Raw Data Endpoints ---

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
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df['date'] = df['date'].where(df['date'].notnull(), None)
        
        # 確保 symbol 是字串
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str)
                
        # 終極清理：將所有 dict 中的 NaN/Inf 轉為 None
        raw_list = df.to_dict(orient="records")
        clean_list = []
        for row in raw_list:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    clean_row[k] = None
                else:
                    clean_row[k] = v
            clean_list.append(clean_row)
            
        return clean_list

    except Exception as e:
        print(f"Raw Data Error ({table}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/raw/daily-quotes", response_model=List[DailyQuoteRaw])
def get_raw_quotes(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("daily_quotes", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/margin-trading", response_model=List[MarginTradingRaw])
def get_raw_margin_trading(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("margin_trading", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/margin-summary", response_model=List[MarginSummaryRaw])
def get_raw_margin_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("margin_summary", start_date, end_date, None, market, limit, offset)

@app.get("/raw/institutional-investors", response_model=List[InstitutionalInvestorsRaw])
def get_raw_institutional(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("institutional_investors", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/institutional-summary", response_model=List[InstitutionalSummaryRaw])
def get_raw_institutional_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("institutional_summary", start_date, end_date, None, market, limit, offset)

@app.get("/raw/foreign-holding", response_model=List[ForeignHoldingRaw])
def get_raw_foreign_holding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("foreign_holding", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/pe-ratio", response_model=List[PeRatioRaw])
def get_raw_pe_ratio(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("pe_ratio", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/market-indices", response_model=List[MarketIndexRaw])
def get_raw_market_indices(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("market_indices", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/monthly-revenue", response_model=List[MonthlyRevenueRaw])
def get_raw_monthly_revenue(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("monthly_revenue", start_date, end_date, symbol, market, limit, offset)

@app.get("/raw/shareholding", response_model=List[ShareholdingRaw])
def get_raw_shareholding(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    symbol: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
):
    return get_raw_data("shareholding_div", start_date, end_date, symbol, None, limit, offset)

import sys
# 確保能 import strategy
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy.core import run_backtest, StrategyConfig

@app.post("/backtest/run", response_model=BacktestResult)
def run_backtest_api(request: BacktestRequest):
    """
    執行回測策略 (使用共用 Strategy 模組)
    """
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        # 1. 抓取資料
        query_end_dt = datetime.datetime.strptime(request.end_date, "%Y-%m-%d") + datetime.timedelta(days=60)
        query_end = query_end_dt.strftime("%Y-%m-%d")

        print(f"Fetching backtest data: {request.start_date} ~ {query_end}...")
        
        query = text("""
            SELECT t.date, t.symbol, d.name, d.open, d.close, d.volume, t.vma10
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date >= :start AND t.date <= :end
            ORDER BY t.symbol, t.date
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"start": request.start_date, "end": query_end})
        
        if df.empty:
            return BacktestResult(
                summary=BacktestSummary(total_trades=0, total_profit=0, total_cost=0, roi=0, win_rate=0, avg_return=0),
                trades=[]
            )

        df['date'] = pd.to_datetime(df['date'])
        
        # 2. 設定策略參數
        config = StrategyConfig(
            strategy_mode=request.strategy_mode,
            capital=request.capital,
            hold_days=request.hold_days,
            allow_pyramiding=request.allow_pyramiding,
            only_red_candle=request.only_red_candle,
            take_profit_pct=request.take_profit_pct,
            stop_loss_pct=request.stop_loss_pct
        )
        
        # 3. 呼叫核心策略
        result = run_backtest(df, config)
        summary = result['summary']
        trades = result['trades']
        
        # 4. 轉換格式回傳
        return BacktestResult(
            summary=BacktestSummary(
                total_trades=summary.total_trades,
                total_profit=summary.total_profit,
                total_cost=summary.total_cost,
                roi=summary.roi,
                win_rate=summary.win_rate,
                avg_return=summary.avg_return
            ),
            trades=[t.__dict__ for t in trades]
        )

    except Exception as e:
        print(f"Backtest Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scanner/volume-spike", response_model=List[VolumeSpikeResult])
def get_volume_spike_scanner(
    date: str = Query(..., description="Scan date in YYYY-MM-DD format"),
    min_volume: int = Query(5000000, description="Minimum volume threshold"),
    volume_ratio: float = Query(4.0, description="Volume spike ratio vs average"),
    avg_days: int = Query(10, description="Days for average volume calculation"),
    filter_long_shadow: bool = Query(True, description="Filter long upper shadow candles")
):
    """
    Run volume spike scanner for a specific date
    Returns stocks with significant volume breakouts
    """
    try:
        from scanner.volume_spike_scanner import scan_volume_spike

        df = scan_volume_spike(
            scan_date=date,
            min_volume=min_volume,
            volume_ratio=volume_ratio,
            avg_days=avg_days,
            filter_long_shadow=filter_long_shadow
        )

        if df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            results.append(VolumeSpikeResult(
                symbol=row['symbol'],
                name=row['name'],
                date=row['date'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                volume_ratio=float(row['volume_ratio']),
                distance_from_high_pct=float(row['distance_from_high_pct']) if pd.notna(row['distance_from_high_pct']) else None,
                upper_shadow_ratio=float(row['upper_shadow_ratio']) if pd.notna(row['upper_shadow_ratio']) else None,
                ma5=float(row['ma5']) if pd.notna(row['ma5']) else None,
                ma10=float(row['ma10']) if pd.notna(row['ma10']) else None,
                ma20=float(row['ma20']) if pd.notna(row['ma20']) else None,
                ma60=float(row['ma60']) if pd.notna(row['ma60']) else None,
                k=float(row['k']) if pd.notna(row['k']) else None,
                d=float(row['d']) if pd.notna(row['d']) else None,
                rsi6=float(row['rsi6']) if pd.notna(row['rsi6']) else None,
                rsi12=float(row['rsi12']) if pd.notna(row['rsi12']) else None,
                macd_dif=float(row['macd_dif']) if pd.notna(row['macd_dif']) else None,
                macd_dea=float(row['macd_dea']) if pd.notna(row['macd_dea']) else None
            ))

        return results

    except Exception as e:
        print(f"Scanner Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
                                "ti.k", "ti.d", "ti.rsi6", "ti.rsi12", "ti.macd_dif", "ti.macd_dea"])
        if include_institutional:
            select_fields.extend(["ii.foreign_net", "ii.trust_net", "ii.dealer_net", "fh.foreign_held_shares",
                                "SUM(ii.trust_net) OVER (PARTITION BY dq.symbol ORDER BY dq.date) AS trust_held_shares"])

        joins = []
        if include_indicators:
            joins.append("LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date")
        if include_institutional:
            joins.append("LEFT JOIN institutional_investors ii ON dq.symbol = ii.symbol AND dq.date = ii.date")
            joins.append("LEFT JOIN foreign_holding fh ON dq.symbol = fh.symbol AND dq.date = fh.date")

        params = {"start_date": start_date, "end_date": end_date}
        where = ["dq.date >= :start_date", "dq.date <= :end_date"]
        if symbols:
            s_list = [s.strip() for s in symbols.split(",")]
            placeholders = ", ".join([f":s{i}" for i in range(len(s_list))])
            where.append(f"dq.symbol IN ({placeholders})")
            for i, s in enumerate(s_list): params[f"s{i}"] = s

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
            if include_institutional:
                record.update({k: float(getattr(row, k)) if getattr(row, k) is not None else None 
                             for k in ["foreign_net", "trust_net", "dealer_net", "foreign_held_shares", "trust_held_shares"]})
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