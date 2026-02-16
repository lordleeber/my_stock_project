import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import os

def run_staged_experiment():
    print("Loading staged dataset...")
    df = pd.read_csv("analysis/eps_staged_dataset.csv")
    
    # 基礎特徵
    base_features = ['q2_eps', 'q2_margin', 'ly_q3_eps']
    
    # 衍生趨勢特徵
    df['mom_aug'] = (df['rev_m8'] / df['rev_m7']) - 1
    df['mom_sep'] = (df['rev_m9'] / df['rev_m8']) - 1
    
    # 清理 NaN
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    train_df = df[df['year'] < 2024].copy()
    test_df = df[df['year'] == 2024].copy()
    
    print(f"Train: {len(train_df)} | Test: {len(test_df)}\n")

    results = {}

    # --- 階段 1 (8月)：僅已知 7月營收 ---
    features_t1 = base_features + ['est_q3_rev_t1']
    model_t1 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t1.fit(train_df[features_t1], train_df['target_eps'])
    pred_t1 = model_t1.predict(test_df[features_t1])
    results['Stage T1 (Aug)'] = mean_absolute_error(test_df['target_eps'], pred_t1)

    # --- 階段 2 (9月)：已知 7, 8月營收 ---
    features_t2 = base_features + ['est_q3_rev_t2', 'mom_aug']
    model_t2 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t2.fit(train_df[features_t2], train_df['target_eps'])
    pred_t2 = model_t2.predict(test_df[features_t2])
    results['Stage T2 (Sep)'] = mean_absolute_error(test_df['target_eps'], pred_t2)

    # --- 階段 3 (10月)：已知 7, 8, 9月全營收 ---
    features_t3 = base_features + ['est_q3_rev_t3', 'mom_aug', 'mom_sep']
    model_t3 = RandomForestRegressor(n_estimators=100, random_state=42)
    model_t3.fit(train_df[features_t3], train_df['target_eps'])
    pred_t3 = model_t3.predict(test_df[features_t3])
    results['Stage T3 (Oct)'] = mean_absolute_error(test_df['target_eps'], pred_t3)

    print("--- MAE Improvement Over Time (2024Q3) ---")
    for stage, mae in results.items():
        print(f"{stage}: {mae:.4f}")

    print("\nSample Improvement Tracking (TSMC 2330):")
    tsmc = test_df[test_df['symbol'] == 2330]
    if not tsmc.empty:
        # Get the positional index in test_df
        pos = test_df.index.get_loc(tsmc.index[0])
        print(f"  Real Q3 EPS: {tsmc.iloc[0]['target_eps']}")
        print(f"  T1 Prediction (Aug): {pred_t1[pos]:.2f}")
        print(f"  T2 Prediction (Sep): {pred_t2[pos]:.2f}")
        print(f"  T3 Prediction (Oct): {pred_t3[pos]:.2f}")

if __name__ == "__main__":
    run_staged_experiment()
