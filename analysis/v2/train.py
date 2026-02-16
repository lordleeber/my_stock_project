import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

def train_v2():
    """
    執行 V2 模型的訓練與評估
    採用「時間切割」驗證：使用 2021-2023 年資料訓練，測試 2024 年
    這比 V1 的交叉驗證更能反映真實世界的預測能力
    """
    # 讀取資料集並補齊缺失值 (假設缺失營收成長為 0)
    df = pd.read_csv("analysis/v2/dataset.csv").fillna(0)
    
    # 定義特徵：加入「去年同期 EPS」與「7月營收年增率」
    features = ['q2_eps', 'q2_margin', 'ly_q3_eps', 'rev_yoy_m7']
    
    # 將資料切割為 訓練集 (過去) 與 測試集 (最新)
    train = df[df['year'] < 2024]
    test = df[df['year'] == 2024]
    
    print(f"訓練樣本數: {len(train)} | 測試樣本數: {len(test)}")
    
    # 訓練模型
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(train[features], train['target_eps'])
    
    # 在 2024Q3 (測試集) 上進行預測
    preds = model.predict(test[features])
    mae = mean_absolute_error(test['target_eps'], preds)
    
    print("\n--- V2 模型評估結果 (測試於 2024Q3) ---")
    print(f"MAE: {mae:.4f}")
    print("\n[註解] V2 透過加入去年同期的 'ly_q3_eps' 特徵，能捕捉產業季節性與 YoY 成長動能。")

if __name__ == "__main__":
    train_v2()
