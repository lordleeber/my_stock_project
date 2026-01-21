import os
import datetime
from typing import List, Optional
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

@app.get("/")
def read_root():
    return {"Hello": "Stock Analysis API"}

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

class KDQuote(BaseModel):
    date: datetime.date
    symbol: str
    name: str
    close: float
    volume: float
    k: float
    d: float

class RSIQuote(BaseModel):
    date: datetime.date
    symbol: str
    name: str
    close: float
    volume: float
    rsi: float

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
        
        # 使用 f-string 插入 sort_order (因為 SQLAlchemy bind params 不支援關鍵字)
        # sort_order 已經過驗證，安全
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

@app.get("/analysis/kd-rank", response_model=List[KDQuote])
def get_kd_rank(
    date: str = Query(..., description="Date in YYYY-MM-DD"), 
    limit: int = 10,
    sort: str = Query("asc", description="Sort order: asc or desc")
):
    """
    取得指定日期 KD 指標排行 (預設 K 值遞增)
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
            SELECT t.date, t.symbol, d.name, d.close, d.volume, t.k, t.d
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date = :date 
              AND t.k IS NOT NULL
              AND d.volume > 0
            ORDER BY t.k {sort_order}
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date_str, "limit": limit}).fetchall()
            
        return [
            KDQuote(
                date=row.date,
                symbol=row.symbol,
                name=row.name,
                close=float(row.close),
                volume=float(row.volume),
                k=float(row.k),
                d=float(row.d)
            ) for row in result
        ]

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analysis/rsi-rank", response_model=List[RSIQuote])
def get_rsi_rank(
    date: str = Query(..., description="Date in YYYY-MM-DD"), 
    limit: int = 10,
    sort: str = Query("asc", description="Sort order: asc or desc")
):
    """
    取得指定日期 RSI 指標排行 (預設遞增)
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
            SELECT t.date, t.symbol, d.name, d.close, d.volume, t.rsi
            FROM technical_indicators t
            JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
            WHERE t.date = :date 
              AND t.rsi IS NOT NULL
              AND d.volume > 0
            ORDER BY t.rsi {sort_order}
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {"date": date_str, "limit": limit}).fetchall()
            
        return [
            RSIQuote(
                date=row.date,
                symbol=row.symbol,
                name=row.name,
                close=float(row.close),
                volume=float(row.volume),
                rsi=float(row.rsi)
            ) for row in result
        ]

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
