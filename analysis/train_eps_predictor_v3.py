import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import os

def train_v3_model():
    print("Loading V3 dataset (Funda + Monthly + CashFlow)...")
    df = pd.read_csv("analysis/eps_v3_dataset.csv")
    
    # 清理資料
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"Train: {len(train_df)} | Test: {len(test_df)}")

    # V3 全特徵組合
    features = [
        'q2_eps', 'q2_margin', 'ly_q3_eps',
        'rev_trend_m8_m7', 'rev_trend_m9_m8',
        'q2_ocf_ratio', 'q2_re_ratio'
    ]

    X_train = train_df[features]
    y_train = train_df['target_eps']
    X_test = test_df[features]
    y_test = test_df['target_eps']

    # 1. 訓練
    model = RandomForestRegressor(n_estimators=300, random_state=42)
    model.fit(X_train, y_train)
    
    # 2. 預測
    test_df.loc[:, 'v3_pred'] = model.predict(X_test)
    
    # 3. 評估
    print("\n--- Model V3 Evaluation (2024Q3) ---")
    mae_v3 = mean_absolute_error(y_test, test_df['v3_pred'])
    r2_v3 = r2_score(y_test, test_df['v3_pred'])
    
    print(f"V3 RandomForest MAE: {mae_v3:.4f}")
    print(f"V3 RandomForest R2:  {r2_v3:.4f}")

    # 4. 特徵重要性
    print("\nV3 Feature Importances:")
    importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print(importances)

    # 5. 台積電 2330 追蹤
    print("\nTSMC (2330) V3 Prediction:")
    tsmc = test_df[test_df['symbol'] == 2330]
    if not tsmc.empty:
        print(f"  Real Q3 EPS: {tsmc.iloc[0]['target_eps']}")
        print(f"  V3 Prediction: {tsmc.iloc[0]['v3_pred']:.2f}")

if __name__ == "__main__":
    train_v3_model()
