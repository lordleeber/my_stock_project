import os
import datetime
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

# ... (get_db_url, read_root, health_check) ...

# ... (get_top_volume, get_ma_data, get_vma_data, get_volume_breakout) ...

# ... (保留前面的 import)
import sys
# 確保能 import strategy
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy.core import run_backtest, StrategyConfig

# ... (保留前面定義的模型與函式，直到 run_backtest_api)

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
        # TradeRecord dataclass -> Pydantic model
        # 注意: dataclass 的屬性與 Pydantic 定義需一致
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
        # Import scanner function
        from scanner.volume_spike_scanner import scan_volume_spike

        # Run scanner
        df = scan_volume_spike(
            scan_date=date,
            min_volume=min_volume,
            volume_ratio=volume_ratio,
            avg_days=avg_days,
            filter_long_shadow=filter_long_shadow
        )

        if df.empty:
            return []

        # Convert DataFrame to Pydantic models
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
    Used to render charts in frontend
    """
    try:
        from datetime import timedelta

        # Calculate date range
        center_date = datetime.datetime.strptime(date, '%Y-%m-%d')
        start_date = (center_date - timedelta(days=days_before)).strftime('%Y-%m-%d')
        end_date = (center_date + timedelta(days=days_after)).strftime('%Y-%m-%d')

        # Query data
        db_url = get_db_url()
        engine = create_engine(db_url)

        sql = text("""
            SELECT
                dq.date,
                dq.open,
                dq.high,
                dq.low,
                dq.close,
                dq.volume,
                ti.ma5,
                ti.ma10,
                ti.ma20,
                ti.ma60
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

        # Convert to Pydantic models
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
            SELECT date, foreign_net, trust_net
            FROM institutional_investors
            WHERE symbol = :symbol
              AND date >= :start_date
              AND date <= :end_date
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
                trust_net=float(row.trust_net) if row.trust_net is not None else 0
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
    """
    取得指定日期成交量排行 (可選遞增或遞減)
    """
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
    """
    取得指定日期各均線數值 (以成交量排序)
    """
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
            WHERE t.date = :date 
              AND d.volume > 0
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
    """
    取得指定日期各成交量均線數值 (以成交量排序)
    """
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
            WHERE t.date = :date 
              AND d.volume > 0
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