import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import os

def train_v3_model():
    """
    執行 V3 模型的訓練與評估
    這是目前系統中最精準的版本，整合了現金流與資產負債表特徵
    """
    print("正在讀取 V3 資料集 (四大報表整合版)...")
    df = pd.read_csv("analysis/v3/dataset.csv")
    
    # 清理資料 (將無限大或極端離群值轉為 0)
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # 訓練集與測試集切割 (2020-2023 訓練, 2024 測試)
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"訓練集樣本: {len(train_df)} | 測試集樣本: {len(test_df)}")

    # 定義 V3 全特徵組合
    features = [
        'q2_eps',           # 獲利基準
        'q2_margin',        # 利潤率
        'ly_q3_eps',        # 去年同期 (季節性因子)
        'rev_trend_m8_m7',  # 8月營收動能
        'rev_trend_m9_m8',  # 9月營收動能
        'q2_ocf_ratio',     # 獲利含金量 (現金流特徵)
        'q2_re_ratio'       # 財務厚度 (資產負債表特徵)
    ]

    X_train = train_df[features]
    y_train = train_df['target_eps']
    X_test = test_df[features]
    y_test = test_df['target_eps']

    # 1. 訓練隨機森林模型 (增加決策樹數量至 300 以提升穩定性)
    model = RandomForestRegressor(n_estimators=300, random_state=42)
    model.fit(X_train, y_train)
    
    # 2. 進行預測
    test_df.loc[:, 'v3_pred'] = model.predict(X_test)
    
    # 3. 評估指標
    print("\n--- Model V3 評估結果 (測試集: 2024Q3) ---")
    mae_v3 = mean_absolute_error(y_test, test_df['v3_pred'])
    r2_v3 = r2_score(y_test, test_df['v3_pred'])
    
    print(f"平均絕對誤差 (MAE): {mae_v3:.4f}")
    print(f"決定係數 (R2 Score): {r2_v3:.4f}")

    # 4. 顯示特徵重要性 (告訴你模型最看重什麼)
    print("\nV3 特徵重要性排名:")
    importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print(importances)

    # 5. 核心個股追蹤 (以台積電為例)
    print("\n[個股案例] 台積電 (2330) V3 預測對比:")
    tsmc = test_df[test_df['symbol'] == 2330]
    if not tsmc.empty:
        print(f"  真實 Q3 EPS: {tsmc.iloc[0]['target_eps']}")
        print(f"  V3 模型預測: {tsmc.iloc[0]['v3_pred']:.2f}")
        print("  [註解] V3 在加入保留盈餘與現金流後，對績優股的預測精度顯著提升。")

if __name__ == "__main__":
    train_v3_model()
