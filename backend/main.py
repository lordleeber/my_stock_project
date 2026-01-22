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

# ... (get_db_url, read_root, health_check) ...

# ... (get_top_volume, get_ma_data, get_vma_data, get_volume_breakout) ...

@app.post("/backtest/run", response_model=BacktestResult)
def run_backtest_api(request: BacktestRequest):
    """
    執行回測策略: Volume > 5 * VMA10
    """
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        # 1. 抓取資料 (範圍稍微大一點以確保有足夠的出場日)
        # 這裡簡單抓取 end_date + 45 天
        query_end_dt = datetime.datetime.strptime(request.end_date, "%Y-%m-%d") + datetime.timedelta(days=45)
        query_end = query_end_dt.strftime("%Y-%m-%d")

        print(f"Fetching backtest data: {request.start_date} ~ {query_end}...")
        
        query = text("""
            SELECT t.date, t.symbol, d.name, d.open, d.close, d.volume, t.vma10
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date >= :start AND t.date <= :end
            ORDER BY t.symbol, t.date
        """)
        
        # 使用 pandas 讀取
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"start": request.start_date, "end": query_end})
        
        if df.empty:
            return BacktestResult(
                summary=BacktestSummary(total_trades=0, total_profit=0, total_cost=0, roi=0, win_rate=0, avg_return=0),
                trades=[]
            )

        df['date'] = pd.to_datetime(df['date'])
        
        # 2. 產生訊號
        df['vma10'] = df['vma10'].fillna(0)
        df['is_signal'] = df['volume'] > (df['vma10'] * 5)
        
        # 紅K濾網 (訊號日當天 Close > Open)
        if request.only_red_candle:
            df['is_signal'] = df['is_signal'] & (df['close'] > df['open'])

        # 篩選在使用者的查詢區間內的訊號
        start_ts = pd.Timestamp(request.start_date)
        end_ts = pd.Timestamp(request.end_date)
        mask_range = (df['date'] >= start_ts) & (df['date'] <= end_ts)
        
        # 這裡必須排序，確保我們是按照時間順序處理訊號，這樣 pyramiding 邏輯才正確
        # 雖然 SQL 已經 ORDER BY symbol, date，但我們 filter 後還是再 sort 一次保險，或者依賴原順序
        # 我們希望跨股票的時間順序其實沒差，因為鎖定是針對 symbol 的
        # 重點是同一個 symbol 的訊號必須按時間排
        signals = df[mask_range & df['is_signal']].copy()
        
        print(f"Found {len(signals)} signals.")
        
        trades = []
        locked_until = {} # key: symbol, value: sell_date (datetime.date)
        
        # 3. 執行策略模擬
        for idx, row in signals.iterrows():
            symbol = row['symbol']
            signal_date = row['date']
            
            # 檢查 Pyramiding 限制
            # 如果不允許加碼，且當前日期還在該股票的「持倉期」內，則跳過
            if not request.allow_pyramiding:
                if symbol in locked_until:
                    # 如果訊號日還沒超過上次的賣出日，表示還持有中
                    # (假設 T+1 買，T+1+Hold 賣，那必須等賣出後才能再看訊號)
                    # 嚴格來說，如果今天賣出，明天買進是可以的。
                    # 所以如果 signal_date < last_sell_date，表示還在持有期
                    # 因為買進是在 signal_date + 1，所以如果 signal_date 發生在賣出日當天或之前，
                    # 它的買進日會是賣出日+1 (或更晚)，這樣就不會重疊部位。
                    # 等等，如果我在 5/5 賣出，5/5 當天出現訊號，那會在 5/6 買進。這是合理的（接棒）。
                    # 但如果我在 5/4 出現訊號，5/5 買進，那就會重疊。
                    # 所以規則應該是：新的 buy_date 必須 > 舊的 sell_date 才能避免部位重疊。
                    # 但我們這裡只知道 signal_date。
                    # buy_date = signal_date + 1 (交易日)
                    # 簡單判斷：如果 signal_date < last_sell_date，那就跳過
                    if signal_date.date() < locked_until[symbol]:
                        continue

            # 取得該股票的局部資料
            stock_data = df[df['symbol'] == symbol].reset_index(drop=True)
            
            # 找到訊號日的 index
            sig_idx_list = stock_data.index[stock_data['date'] == signal_date].tolist()
            if not sig_idx_list: continue
            sig_idx = sig_idx_list[0]
            
            # T+1 買進
            buy_idx = sig_idx + 1
            # T+N 賣出
            sell_idx = sig_idx + 1 + request.hold_days
            
            if buy_idx >= len(stock_data) or sell_idx >= len(stock_data):
                continue
                
            buy_row = stock_data.iloc[buy_idx]
            sell_row = stock_data.iloc[sell_idx]
            
            buy_price = float(buy_row['open'])
            sell_price = float(sell_row['close'])
            
            # 檢查價格是否有效 (非 NaN 且大於 0)
            if pd.isna(buy_price) or pd.isna(sell_price) or buy_price <= 0:
                continue

            buy_date_dt = buy_row['date'].date()
            sell_date_dt = sell_row['date'].date()

            # 再一次檢查 Pyramiding (用準確的 buy_date)
            if not request.allow_pyramiding:
                if symbol in locked_until:
                    # 如果新的買入日期 <= 上次的賣出日期，表示資金還沒釋放
                    if buy_date_dt <= locked_until[symbol]:
                        continue

            # 決定股數
            shares = 0
            if request.strategy_mode == 'shares':
                shares = 1000 # 預設一張
            elif request.strategy_mode == 'amount':
                shares = int(request.capital // buy_price)
            
            if shares <= 0: continue

            cost = buy_price * shares
            revenue = sell_price * shares
            profit = revenue - cost
            ret = (sell_price - buy_price) / buy_price

            trades.append(TradeRecord(
                symbol=symbol,
                name=row['name'],
                buy_date=buy_date_dt,
                sell_date=sell_date_dt,
                buy_price=buy_price,
                sell_price=sell_price,
                shares=shares,
                profit=profit,
                return_rate=ret * 100
            ))
            
            # 更新鎖定日期
            locked_until[symbol] = sell_date_dt
            
        # 4. 統計結果
        if not trades:
            return BacktestResult(
                summary=BacktestSummary(total_trades=0, total_profit=0, total_cost=0, roi=0, win_rate=0, avg_return=0),
                trades=[]
            )
            
        df_trades = pd.DataFrame([t.dict() for t in trades])
        total_profit = df_trades['profit'].sum()
        # 這裡 total_cost 我們計算所有交易的買入成本總和
        trade_costs = df_trades['buy_price'] * df_trades['shares']
        total_cost = trade_costs.sum()
        
        avg_return = df_trades['return_rate'].mean()
        win_rate = (df_trades['profit'] > 0).mean() * 100
        roi = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        return BacktestResult(
            summary=BacktestSummary(
                total_trades=len(trades),
                total_profit=total_profit,
                total_cost=total_cost,
                roi=roi,
                win_rate=win_rate,
                avg_return=avg_return
            ),
            trades=trades
        )

    except Exception as e:
        print(f"Backtest Error: {e}")
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