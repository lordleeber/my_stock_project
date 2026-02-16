import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import os

def train_enhanced_model():
    print("Loading enhanced dataset...")
    df = pd.read_csv("analysis/eps_enhanced_dataset.csv")
    
    # 清理
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['target_eps', 'q2_margin'])
    
    # 分割
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"Train: {len(train_df)} | Test: {len(test_df)}")

    # 定義特徵：加入季節性與月趨勢
    features = [
        'q2_eps', 'q2_margin', 
        'rev_trend_m8_m7', 'rev_trend_m9_m8', # 今年 Q3 動能
        'margin_seasonality_ratio', 'eps_seasonality_ratio', # 去年季節性
        'ly_q3_eps' # 去年同期絕對值
    ]

    X_train = train_df[features].fillna(0)
    y_train = train_df['target_eps']
    X_test = test_df[features].fillna(0)
    y_test = test_df['target_eps']

    # 1. 訓練模型
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X_train, y_train)
    
    # 2. 預測
    test_df['ml_pred'] = model.predict(X_test)
    
    # 3. 評估
    print("\n--- Comparative Evaluation (2024Q3) ---")
    
    # 直接用去年 Q3 預測今年 Q3
    mae_ly = mean_absolute_error(y_test, test_df['ly_q3_eps'].fillna(0))
    # 原始公式 (忽略季節性)
    naive_formula_eps = (test_df['q3_rev_total'] * test_df['q2_margin']) / (test_df['capital'] / 10)
    mae_naive = mean_absolute_error(y_test, naive_formula_eps.fillna(0))
    # 季節性公式 (考慮去年變動)
    mae_seasonal_formula = mean_absolute_error(y_test, test_df['pred_eps_seasonal'].fillna(0))
    # ML 模型
    mae_ml = mean_absolute_error(y_test, test_df['ml_pred'])

    print(f"1. Last Year Q3 Baseline MAE: {mae_ly:.4f}")
    print(f"2. Naive Formula (Q2 Margin) MAE: {mae_naive:.4f}")
    print(f"3. Seasonal Formula (LY Ratio) MAE: {mae_seasonal_formula:.4f}")
    print(f"4. Enhanced RandomForest MAE:   {mae_ml:.4f}")
    print(f"RandomForest R2 Score: {r2_score(y_test, test_df['ml_pred']):.4f}")

    # 4. 特徵重要性
    print("\nFeature Importances:")
    importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print(importances)

    # 5. 隨機抽樣對比 (台積電 2330 通常在樣本中)
    print("\nSample Comparisons (2024Q3):")
    cols = ['symbol', 'name', 'target_eps', 'pred_eps_seasonal', 'ml_pred']
    print(test_df[test_df['symbol'].isin([2330, 2317, 2454, 3701, 3704])][cols])

if __name__ == "__main__":
    train_enhanced_model()
