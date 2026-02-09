import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# 加入專案根目錄到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.http_client import fetch_dataframe, fetch_json
from common.constants import API_BASE

# ---------------------------------------------------------
# 基本面旗艦級估值系統 3.0
# 改進：TTM EPS + PEG Ratio + 分產業估值 + 歷史區間
# ---------------------------------------------------------

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# =========================================================
# 產業估值策略配置
# =========================================================
INDUSTRY_VALUATION_CONFIG = {
    # 金融業：重視 PB 和殖利率
    '金融業': {'pe': 0.15, 'pb': 0.45, 'peg': 0.10, 'dividend': 0.30, 'max_pe': 15},
    '金融保險業': {'pe': 0.15, 'pb': 0.45, 'peg': 0.10, 'dividend': 0.30, 'max_pe': 15},
    '銀行業': {'pe': 0.15, 'pb': 0.50, 'peg': 0.05, 'dividend': 0.30, 'max_pe': 12},
    '保險業': {'pe': 0.20, 'pb': 0.40, 'peg': 0.10, 'dividend': 0.30, 'max_pe': 15},

    # 營建業：重視 PB (淨資產)，PE 不可靠
    '建材營造業': {'pe': 0.10, 'pb': 0.60, 'peg': 0.05, 'dividend': 0.25, 'max_pe': 10},
    '營建業': {'pe': 0.10, 'pb': 0.60, 'peg': 0.05, 'dividend': 0.25, 'max_pe': 10},

    # 高成長科技：重視 PEG
    '半導體業': {'pe': 0.25, 'pb': 0.15, 'peg': 0.45, 'dividend': 0.15, 'max_pe': 25},
    '電腦及週邊設備業': {'pe': 0.25, 'pb': 0.20, 'peg': 0.40, 'dividend': 0.15, 'max_pe': 20},
    '光電業': {'pe': 0.20, 'pb': 0.25, 'peg': 0.40, 'dividend': 0.15, 'max_pe': 20},
    '通信網路業': {'pe': 0.25, 'pb': 0.20, 'peg': 0.40, 'dividend': 0.15, 'max_pe': 20},
    '電子零組件業': {'pe': 0.25, 'pb': 0.20, 'peg': 0.40, 'dividend': 0.15, 'max_pe': 18},
    '電子通路業': {'pe': 0.30, 'pb': 0.25, 'peg': 0.30, 'dividend': 0.15, 'max_pe': 15},
    '資訊服務業': {'pe': 0.25, 'pb': 0.15, 'peg': 0.45, 'dividend': 0.15, 'max_pe': 25},
    '其他電子業': {'pe': 0.25, 'pb': 0.20, 'peg': 0.40, 'dividend': 0.15, 'max_pe': 18},

    # 傳產穩定：均衡 + 殖利率
    '食品工業': {'pe': 0.30, 'pb': 0.25, 'peg': 0.20, 'dividend': 0.25, 'max_pe': 20},
    '塑膠工業': {'pe': 0.30, 'pb': 0.30, 'peg': 0.15, 'dividend': 0.25, 'max_pe': 15},
    '紡織纖維': {'pe': 0.25, 'pb': 0.35, 'peg': 0.15, 'dividend': 0.25, 'max_pe': 15},
    '電機機械': {'pe': 0.30, 'pb': 0.25, 'peg': 0.25, 'dividend': 0.20, 'max_pe': 18},
    '電器電纜': {'pe': 0.30, 'pb': 0.30, 'peg': 0.15, 'dividend': 0.25, 'max_pe': 15},
    '生技醫療業': {'pe': 0.20, 'pb': 0.20, 'peg': 0.50, 'dividend': 0.10, 'max_pe': 30},

    # 景氣循環：重視 PB 和歷史區間
    '鋼鐵工業': {'pe': 0.20, 'pb': 0.45, 'peg': 0.10, 'dividend': 0.25, 'max_pe': 12},
    '航運業': {'pe': 0.15, 'pb': 0.50, 'peg': 0.10, 'dividend': 0.25, 'max_pe': 10},
    '汽車工業': {'pe': 0.25, 'pb': 0.35, 'peg': 0.20, 'dividend': 0.20, 'max_pe': 15},
    '橡膠工業': {'pe': 0.25, 'pb': 0.35, 'peg': 0.15, 'dividend': 0.25, 'max_pe': 15},
    '化學工業': {'pe': 0.25, 'pb': 0.35, 'peg': 0.15, 'dividend': 0.25, 'max_pe': 15},
    '玻璃陶瓷': {'pe': 0.25, 'pb': 0.40, 'peg': 0.10, 'dividend': 0.25, 'max_pe': 12},
    '造紙工業': {'pe': 0.25, 'pb': 0.40, 'peg': 0.10, 'dividend': 0.25, 'max_pe': 12},
    '水泥工業': {'pe': 0.25, 'pb': 0.40, 'peg': 0.10, 'dividend': 0.25, 'max_pe': 12},

    # 其他
    '觀光餐旅': {'pe': 0.30, 'pb': 0.30, 'peg': 0.20, 'dividend': 0.20, 'max_pe': 20},
    '貿易百貨業': {'pe': 0.30, 'pb': 0.25, 'peg': 0.25, 'dividend': 0.20, 'max_pe': 18},
    '油電燃氣業': {'pe': 0.25, 'pb': 0.30, 'peg': 0.15, 'dividend': 0.30, 'max_pe': 15},
}

# 預設配置 (未知產業)
DEFAULT_CONFIG = {'pe': 0.30, 'pb': 0.25, 'peg': 0.25, 'dividend': 0.20, 'max_pe': 18}


def get_latest_quarters(n=4):
    """取得最近 n 季的季度代碼"""
    today = datetime.now()
    year, month = today.year, today.month

    # 判斷當前最新可用季度
    if month >= 11:
        latest = (year, 3)
    elif month >= 8:
        latest = (year, 2)
    elif month >= 5:
        latest = (year, 1)
    elif month >= 4:
        latest = (year - 1, 4)
    else:
        latest = (year - 1, 3)

    quarters = []
    y, q = latest
    for _ in range(n):
        quarters.append(f"{y}Q{q}")
        q -= 1
        if q == 0:
            q = 4
            y -= 1

    return quarters


def fetch_all_data():
    """取得所有需要的資料，包含近四季財報"""
    try:
        quarters = get_latest_quarters(4)
        print(f"使用財報季度: {quarters[0]} (TTM: {quarters[-1]} ~ {quarters[0]})")

        # 取得最新交易日
        latest_data = fetch_json("/raw/daily-quotes", {"start_date": "2025-01-01", "end_date": "2026-12-31", "limit": 1})
        latest_date = latest_data[0]['date'] if latest_data else None

        # 取得近四季損益表 (計算 TTM EPS)
        all_income = []
        for q in quarters:
            df = fetch_dataframe("/raw/income-statements", {"start_date": q, "end_date": q, "limit": 3000})
            if not df.empty:
                df['quarter'] = q
                all_income.append(df)
        df_income_all = pd.concat(all_income, ignore_index=True) if all_income else pd.DataFrame()

        # 取得最新一季的資產負債表和現金流量表
        bs_stmt = fetch_dataframe("/raw/balance-sheets", {"start_date": quarters[0], "end_date": quarters[0], "limit": 3000})
        cf_stmt = fetch_dataframe("/raw/cash-flows", {"start_date": quarters[0], "end_date": quarters[0], "limit": 3000})

        # 取得當前價格
        p_data = fetch_dataframe("/raw/daily-quotes", {"start_date": latest_date, "end_date": latest_date, "limit": 5000})

        # 取得股票資訊 (產業別)
        info = fetch_dataframe("/raw/stock-info", {"limit": 5000})

        # 取得歷史 PE 資料 (近 3 年)
        hist_pe = fetch_historical_pe()

        # 取得股利資料
        dividends = fetch_dividends()

        return df_income_all, bs_stmt, cf_stmt, p_data, info, hist_pe, dividends, latest_date, quarters[0]

    except Exception as e:
        print(f"資料獲取失敗: {e}")
        return [pd.DataFrame()] * 7 + [None, None]


def fetch_historical_pe():
    """取得歷史 PE 資料 (近 3 年每月一筆)"""
    try:
        # 取樣：每季取一個交易日的 PE
        sample_dates = []
        today = datetime.now()
        for i in range(12):  # 近 3 年，每季一筆
            y = today.year - (i // 4)
            m = [3, 6, 9, 12][3 - (i % 4)]
            sample_dates.append(f"{y}-{m:02d}-15")

        all_pe = []
        for d in sample_dates[:6]:  # 只取近 6 筆減少 API 呼叫
            df = fetch_dataframe("/raw/daily-quotes", {"start_date": d, "end_date": d, "limit": 5000})
            if not df.empty and 'pe_ratio' in df.columns:
                df = df[['symbol', 'pe_ratio']].copy()
                df['pe_ratio'] = pd.to_numeric(df['pe_ratio'], errors='coerce')
                all_pe.append(df)

        if all_pe:
            df_all = pd.concat(all_pe, ignore_index=True)
            # 計算每檔股票的 PE 區間
            pe_stats = df_all[df_all['pe_ratio'] > 0].groupby('symbol')['pe_ratio'].agg(['min', 'max', 'median']).reset_index()
            pe_stats.columns = ['symbol', 'pe_min', 'pe_max', 'pe_median']
            return pe_stats

        return pd.DataFrame()
    except Exception as e:
        print(f"歷史 PE 取得失敗: {e}")
        return pd.DataFrame()


def fetch_dividends():
    """取得最近一年股利資料"""
    try:
        # 嘗試從 API 取得股利資料
        df = fetch_dataframe("/raw/dividends", {"limit": 5000})
        if not df.empty and 'cash_dividend' in df.columns:
            df['symbol'] = df['symbol'].astype(str)
            df['cash_dividend'] = pd.to_numeric(df['cash_dividend'], errors='coerce').fillna(0)
            # 取最新一筆
            return df.sort_values('year', ascending=False).drop_duplicates('symbol')[['symbol', 'cash_dividend']]
        return pd.DataFrame()
    except:
        return pd.DataFrame()


def calculate_ttm_eps(df_income_all):
    """計算 TTM EPS (近四季 EPS 加總)"""
    if df_income_all.empty:
        return pd.DataFrame()

    df = df_income_all.copy()
    df['symbol'] = df['symbol'].astype(str)
    df['eps'] = pd.to_numeric(df['eps'], errors='coerce').fillna(0)

    # 確保有四季資料的股票
    eps_count = df.groupby('symbol').size()
    valid_symbols = eps_count[eps_count >= 4].index

    # 計算 TTM EPS
    ttm = df[df['symbol'].isin(valid_symbols)].groupby('symbol')['eps'].sum().reset_index()
    ttm.columns = ['symbol', 'eps_ttm']

    # 計算 EPS YoY 成長率 (需要去年同期資料)
    # 簡化：用最新季 vs 去年同季
    df_sorted = df.sort_values(['symbol', 'quarter'], ascending=[True, False])
    latest = df_sorted.drop_duplicates('symbol')[['symbol', 'eps']].rename(columns={'eps': 'eps_latest'})

    # 取得去年同期 (第5季前的資料)
    quarters = df['quarter'].unique()
    if len(quarters) >= 4:
        df_yoy = df_sorted.groupby('symbol').nth(3)[['eps']].reset_index().rename(columns={'eps': 'eps_yoy_base'})
        latest = pd.merge(latest, df_yoy, on='symbol', how='left')
        latest['eps_growth'] = np.where(
            latest['eps_yoy_base'] > 0,
            (latest['eps_latest'] - latest['eps_yoy_base']) / latest['eps_yoy_base'] * 100,
            np.nan
        )
    else:
        latest['eps_growth'] = np.nan

    ttm = pd.merge(ttm, latest[['symbol', 'eps_growth']], on='symbol', how='left')
    return ttm


def get_industry_config(industry):
    """取得產業估值配置"""
    if pd.isna(industry):
        return DEFAULT_CONFIG
    for key, config in INDUSTRY_VALUATION_CONFIG.items():
        if key in str(industry):
            return config
    return DEFAULT_CONFIG


def calculate_fair_prices(df, industry_pe, industry_pb):
    """計算各種估值法的合理價"""
    results = []

    for _, row in df.iterrows():
        symbol = row['symbol']
        industry = row.get('industry', '')
        config = get_industry_config(industry)

        eps_ttm = row.get('eps_ttm', 0)
        nav = row.get('nav_per_share', 0)
        eps_growth = row.get('eps_growth', 0)
        dividend = row.get('cash_dividend', 0)
        close = row.get('close', 0)

        # 產業基準
        base_pe = industry_pe.get(industry, 15)
        base_pb = industry_pb.get(industry, 1.5)
        max_pe = config['max_pe']

        # 限制 PE 上限
        base_pe = min(base_pe, max_pe)

        # 1. PE 估值
        fair_pe = eps_ttm * base_pe if eps_ttm > 0 else 0

        # 2. PB 估值
        fair_pb = nav * base_pb if nav > 0 else 0

        # 3. PEG 估值 (成長股適用)
        if eps_growth and eps_growth > 5 and eps_ttm > 0:
            # PEG = 1 為合理，給予成長率等同的 PE
            growth_adjusted_pe = min(eps_growth, 30)  # 成長率上限 30%
            fair_peg = eps_ttm * growth_adjusted_pe
        else:
            fair_peg = fair_pe  # 無成長資料時用 PE 估值

        # 4. 殖利率估值 (DDM 簡化版)
        required_yield = 0.05  # 要求 5% 殖利率
        fair_dividend = dividend / required_yield if dividend > 0 else 0

        # 加權計算合理價
        weights = config
        prices = {
            'pe': fair_pe,
            'pb': fair_pb,
            'peg': fair_peg,
            'dividend': fair_dividend
        }

        # 過濾掉 0 的估值，重新分配權重
        valid_prices = {k: v for k, v in prices.items() if v > 0}
        if valid_prices:
            total_weight = sum(weights[k] for k in valid_prices.keys())
            weighted_price = sum(prices[k] * weights[k] for k in valid_prices.keys()) / total_weight
        else:
            weighted_price = 0

        results.append({
            'symbol': symbol,
            'fair_pe': round(fair_pe, 2),
            'fair_pb': round(fair_pb, 2),
            'fair_peg': round(fair_peg, 2),
            'fair_dividend': round(fair_dividend, 2),
            'predict_price': round(weighted_price, 2),
            'valuation_method': f"PE:{weights['pe']:.0%}/PB:{weights['pb']:.0%}/PEG:{weights['peg']:.0%}/DIV:{weights['dividend']:.0%}"
        })

    return pd.DataFrame(results)


def calculate_pe_percentile(df, hist_pe):
    """計算當前 PE 在歷史區間的位置"""
    if hist_pe.empty:
        df['pe_percentile'] = np.nan
        df['pe_zone'] = '無資料'
        return df

    df = pd.merge(df, hist_pe, on='symbol', how='left')

    # 計算百分位
    df['pe_percentile'] = np.where(
        (df['pe_max'] > df['pe_min']) & (df['pe_ratio'] > 0),
        (df['pe_ratio'] - df['pe_min']) / (df['pe_max'] - df['pe_min']) * 100,
        np.nan
    )

    # 分類
    def get_zone(pct):
        if pd.isna(pct):
            return '無資料'
        elif pct <= 20:
            return '極度低估'
        elif pct <= 40:
            return '相對低估'
        elif pct <= 60:
            return '合理區間'
        elif pct <= 80:
            return '相對高估'
        else:
            return '極度高估'

    df['pe_zone'] = df['pe_percentile'].apply(get_zone)
    return df


def run_valuation():
    print("=" * 60)
    print("基本面專家：旗艦級智能估值系統 3.0")
    print("改進：TTM EPS + PEG Ratio + 分產業估值 + 歷史區間")
    print("=" * 60)

    df_income_all, df_bs, df_cf, df_p, df_info, hist_pe, dividends, l_date, quarter = fetch_all_data()

    if df_p.empty:
        print("無法取得價格資料")
        return

    # 轉換 symbol 為字串
    for d in [df_income_all, df_bs, df_cf, df_p, df_info]:
        if not d.empty and 'symbol' in d.columns:
            d['symbol'] = d['symbol'].astype(str)

    # 計算 TTM EPS
    print("計算 TTM EPS...")
    ttm_eps = calculate_ttm_eps(df_income_all)
    if ttm_eps.empty:
        print("無法計算 TTM EPS，改用單季年化")
        # Fallback: 使用最新季 * 4
        if not df_income_all.empty:
            latest = df_income_all.sort_values('quarter', ascending=False).drop_duplicates('symbol')
            ttm_eps = latest[['symbol', 'eps']].copy()
            ttm_eps['eps'] = pd.to_numeric(ttm_eps['eps'], errors='coerce').fillna(0)
            ttm_eps['eps_ttm'] = ttm_eps['eps'] * 4
            ttm_eps['eps_growth'] = np.nan
            ttm_eps = ttm_eps[['symbol', 'eps_ttm', 'eps_growth']]

    print(f"TTM EPS 計算完成: {len(ttm_eps)} 檔")

    # 合併資料
    df = pd.merge(df_p[['symbol', 'name', 'close', 'pe_ratio']], ttm_eps, on='symbol', how='inner')
    df = pd.merge(df, df_bs[['symbol', 'nav_per_share']], on='symbol', how='left')
    df = pd.merge(df, df_info[['symbol', 'industry']], on='symbol', how='left')

    if not dividends.empty:
        df = pd.merge(df, dividends, on='symbol', how='left')
    else:
        df['cash_dividend'] = 0

    # 數值轉換
    num_cols = ['close', 'pe_ratio', 'eps_ttm', 'nav_per_share', 'cash_dividend', 'eps_growth']
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    # 過濾無效資料
    df = df[(df['nav_per_share'] > 0) & (df['close'] > 0)].copy()
    print(f"有效股票數: {len(df)}")

    # 計算產業基準
    industry_pe = df[df['pe_ratio'] > 0].groupby('industry')['pe_ratio'].median().to_dict()
    df['pb_ratio'] = df['close'] / df['nav_per_share']
    industry_pb = df[(df['pb_ratio'] > 0) & np.isfinite(df['pb_ratio'])].groupby('industry')['pb_ratio'].median().to_dict()

    # 計算各種合理價
    print("計算分產業估值...")
    fair_prices = calculate_fair_prices(df, industry_pe, industry_pb)
    df = pd.merge(df, fair_prices, on='symbol', how='left')

    # 計算 PE 歷史區間位置
    print("計算歷史 PE 區間...")
    df = calculate_pe_percentile(df, hist_pe)

    # 計算報酬潛力
    df['upside'] = np.where(
        df['close'] > 0,
        (df['predict_price'] - df['close']) / df['close'] * 100,
        np.nan
    )

    # 計算 ROE
    df['roe_annual'] = np.where(
        df['nav_per_share'] > 0,
        (df['eps_ttm'] / df['nav_per_share']) * 100,
        0
    )

    # 計算 PEG
    df['peg_ratio'] = np.where(
        (df['eps_growth'] > 0) & (df['pe_ratio'] > 0),
        df['pe_ratio'] / df['eps_growth'],
        np.nan
    )

    # 篩選條件 (放寬以展示更多結果)
    print("篩選低估股票...")
    undervalued = df[
        (df['upside'] > 20) &  # 潛在報酬 > 20%
        (df['eps_ttm'] > 0) &  # 獲利為正
        (df['roe_annual'] > 8)  # ROE > 8%
    ].copy()

    # 額外標記優質股
    undervalued['quality_flag'] = ''
    undervalued.loc[undervalued['peg_ratio'] < 1, 'quality_flag'] += 'PEG<1 '
    undervalued.loc[undervalued['pe_zone'] == '極度低估', 'quality_flag'] += '歷史低點 '
    undervalued.loc[undervalued['roe_annual'] > 15, 'quality_flag'] += '高ROE '

    undervalued = undervalued.sort_values('upside', ascending=False)
    undervalued['price_date'] = l_date
    undervalued['report_quarter'] = quarter
    undervalued = undervalued.rename(columns={'close': 'market_price'})

    # 格式化
    float_cols = ['market_price', 'predict_price', 'upside', 'eps_ttm', 'eps_growth',
                  'nav_per_share', 'roe_annual', 'pe_ratio', 'peg_ratio', 'pe_percentile',
                  'fair_pe', 'fair_pb', 'fair_peg', 'fair_dividend']
    for c in float_cols:
        if c in undervalued.columns:
            undervalued[c] = undervalued[c].round(2)

    # 輸出欄位
    final_cols = [
        'symbol', 'name', 'industry', 'price_date', 'market_price', 'predict_price', 'upside',
        'eps_ttm', 'eps_growth', 'pe_ratio', 'peg_ratio',
        'nav_per_share', 'roe_annual',
        'pe_zone', 'pe_percentile',
        'fair_pe', 'fair_pb', 'fair_peg', 'fair_dividend',
        'valuation_method', 'quality_flag', 'report_quarter'
    ]
    final_cols = [c for c in final_cols if c in undervalued.columns]

    output_path = os.path.join("strategy", "fundamental", "undervalued_picks.csv")
    undervalued[final_cols].to_csv(output_path, index=False, encoding='utf-8-sig')

    # 輸出統計
    print("=" * 60)
    print(f"篩選完成！共 {len(undervalued)} 檔低估股票")
    print(f"使用季度: {quarter} (TTM), 價格日期: {l_date}")
    print(f"結果見 {output_path}")
    print("=" * 60)

    # 顯示 Top 10
    if len(undervalued) > 0:
        print("\nTop 10 低估股票:")
        print("-" * 80)
        top10 = undervalued.head(10)[['symbol', 'name', 'industry', 'market_price', 'predict_price', 'upside', 'pe_zone', 'quality_flag']]
        print(top10.to_string(index=False))

    # 產業分布
    if len(undervalued) > 0:
        print("\n產業分布:")
        print(undervalued['industry'].value_counts().head(10).to_string())


if __name__ == "__main__":
    run_valuation()
