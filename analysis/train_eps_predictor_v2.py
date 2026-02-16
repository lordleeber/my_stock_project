import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import os

def run_v2_staged_experiment():
    print("Loading enhanced seasonal-monthly dataset...")
    df = pd.read_csv("analysis/eps_seasonal_monthly_dataset.csv")
    
    # 清理資料
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"Train: {len(train_df)} | Test: {len(test_df)}\n")

    # 基礎特徵 (不變)
    base_features = ['q2_eps', 'q2_margin', 'ly_q3_eps']
    
    results = {}

    # --- 階段 T1 (8月)：已知 7月 YoY ---
    features_t1 = base_features + ['rev_yoy_m7']
    model_t1 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t1.fit(train_df[features_t1], train_df['target_eps'])
    pred_t1 = model_t1.predict(test_df[features_t1])
    results['T1 (Aug) - with 7M YoY'] = mean_absolute_error(test_df['target_eps'], pred_t1)

    # --- 階段 T2 (9月)：已知 7, 8月 YoY ---
    features_t2 = base_features + ['rev_yoy_m7', 'rev_yoy_m8', 'rel_momentum_m8']
    model_t2 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t2.fit(train_df[features_t2], train_df['target_eps'])
    pred_t2 = model_t2.predict(test_df[features_t2])
    results['T2 (Sep) - with 8M YoY'] = mean_absolute_error(test_df['target_eps'], pred_t2)

    # --- 階段 T3 (10月)：已知 7, 8, 9月 YoY ---
    # 這裡可以算出 Q3 總營收的實質 YoY
    train_df.loc[:, 'q3_rev_yoy'] = ((train_df['rev_m7']+train_df['rev_m8']+train_df['rev_m9']) / 
                                     (train_df['ly_rev_m7']+train_df['ly_rev_m8']+train_df['ly_rev_m9'])) - 1
    test_df.loc[:, 'q3_rev_yoy'] = ((test_df['rev_m7']+test_df['rev_m8']+test_df['rev_m9']) / 
                                    (test_df['ly_rev_m7']+test_df['ly_rev_m8']+test_df['ly_rev_m9'])) - 1
    
    features_t3 = base_features + ['rev_yoy_m7', 'rev_yoy_m8', 'rev_yoy_m9', 'q3_rev_yoy']
    model_t3 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t3.fit(train_df[features_t3], train_df['target_eps'])
    pred_t3 = model_t3.predict(test_df[features_t3])
    results['T3 (Oct) - with Full Q3 YoY'] = mean_absolute_error(test_df['target_eps'], pred_t3)

    print("--- MAE Performance (2024Q3) ---")
    for stage, mae in results.items():
        print(f"{stage}: {mae:.4f}")

    print("\nCase Study: TSMC (2330)")
    tsmc = test_df[test_df['symbol'] == 2330]
    if not tsmc.empty:
        pos = test_df.index.get_loc(tsmc.index[0])
        print(f"  Real Q3 EPS: {tsmc.iloc[0]['target_eps']}")
        print(f"  T1 Pred: {pred_t1[pos]:.2f}")
        print(f"  T2 Pred: {pred_t2[pos]:.2f}")
        print(f"  T3 Pred: {pred_t3[pos]:.2f}")

    # 特徵重要性 (T3)
    print("\nT3 Feature Importances:")
    importances = pd.Series(model_t3.feature_importances_, index=features_t3).sort_values(ascending=False)
    print(importances)

if __name__ == "__main__":
    run_v2_staged_experiment()
