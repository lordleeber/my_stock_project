import pandas as pd
import numpy as np
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

def train_v4_model():
    """
    執行 V4 模型訓練與評估
    核心特色：使用大量財務比率 (ROE, 負債比, 流動比等) 進行全市場預測
    """
    print("正在讀取 V4 財務比率資料集...")
    df = pd.read_csv("analysis/v4/dataset.csv")
    # 清理無限大或空值，確保模型穩定
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # 訓練與測試分割 (2020-2023 訓練, 2024 測試)
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"訓練集樣本數: {len(train_df)} | 測試集樣本數: {len(test_df)}")

    # 定義 V4 特徵清單 (共 15 項)
    features = [
        'q2_eps',               # Q2 EPS 基準
        'ly_q3_eps',            # 去年同期季節性基準
        'q2_gross_margin',      # 毛利率 (競爭力)
        'q2_operating_margin',  # 營益率 (本業獲利力)
        'q2_net_margin',        # 淨利率 (最終獲利力)
        'margin_momentum',      # 淨利動能 (Q2 vs Q1)
        'q2_non_op_ratio',      # 業外佔比 (獲利純度)
        'q2_roe',               # 股東權益報酬率 (資產效率)
        'q2_roa',               # 總資產報酬率
        'q2_debt_ratio',        # 負債比 (財務槓桿)
        'q2_current_ratio',     # 流動比 (短期體質)
        'q2_ocf_ratio',         # 獲利含金量 (現金流)
        'q2_capex_intensity',   # 資本支出強度 (擴產動能)
        'rev_trend_m8_m7',      # 8月營收月增趨勢
        'rev_trend_m9_m8'       # 9月營收月增趨勢
    ]

    X_train = train_df[features]
    y_train = train_df['target_eps']
    X_test = test_df[features]
    y_test = test_df['target_eps']

    # 1. 訓練模型 (使用 500 顆樹並啟用全核心平行運算)
    model = RandomForestRegressor(n_estimators=500, max_depth=15, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    
    # 2. 進行 2024Q3 預測
    test_df.loc[:, 'v4_pred'] = model.predict(X_test)
    
    # 3. 評估指標
    print("\n--- Model V4 (Ratio-Based) 評估結果 (2024Q3) ---")
    mae = mean_absolute_error(y_test, test_df['v4_pred'])
    r2 = r2_score(y_test, test_df['v4_pred'])
    print(f"平均絕對誤差 (MAE): {mae:.4f}")
    print(f"決定係數 (R2 Score): {r2:.4f}")

    # 4. 特徵重要性分析
    print("\nV4 財務比率重要性排名 (Top 10):")
    importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print(importances.head(10))

    # 5. 指標個股追蹤
    print("\n[個股案例] 預測對比:")
    test_df['symbol'] = test_df['symbol'].astype(str)
    symbols = ['2330', '2317', '2454', '1795', '3704']
    case_results = test_df[test_df['symbol'].isin(symbols)][['symbol', 'name', 'target_eps', 'v4_pred']]
    print(case_results)

    # 6. 使用通用模組儲存預測結果
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from db_utils import save_eps_predictions
    
    # 準備儲存格式
    save_df = test_df[['symbol', 'v4_pred']].rename(columns={'v4_pred': 'predict_eps'})
    save_eps_predictions(save_df, target_quarter='2024Q3', model_version='v4')

if __name__ == "__main__":
    train_v4_model()
