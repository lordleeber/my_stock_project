import pandas as pd
import numpy as np
import os
import sys
import argparse
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# 引入共用資料庫工具
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from db_utils import save_eps_predictions

def run_training_and_eval(args):
    """
    執行 V4 模型訓練與多階段回測評估
    """
    print(f"正在讀取資料集: {args.dataset}")
    df = pd.read_csv(args.dataset)
    # 基本資料清理
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    df['year'] = df['year'].astype(int)
    
    # 定義特徵清單
    features = [
        'q2_eps', 'ly_q3_eps', 
        'q2_gross_margin', 'q2_operating_margin', 'q2_net_margin', 
        'margin_momentum', 'q2_non_op_ratio',
        'q2_roe', 'q2_roa', 'q2_debt_ratio', 'q2_current_ratio',
        'q2_ocf_ratio', 'q2_capex_intensity',
        'rev_trend_m8_m7', 'rev_trend_m9_m8'
    ]

    # --- 多階段時序回測 (Addressing Reviewer Issue #2) ---
    print("\n--- 執行時序擴張回測 (Expanding Window Backtest) ---")
    unique_years = sorted(df['year'].unique())
    # 至少要有兩年資料才能進行回測 (一年訓練，一年測試)
    if len(unique_years) < 2:
        print("❌ 樣本年份不足，無法執行時序回測")
        return

    test_years = unique_years[1:] # 從第二年開始當作測試集
    fold_results = []

    for test_year in test_years:
        train_data = df[df['year'] < test_year]
        test_data = df[df['year'] == test_year]
        
        model = RandomForestRegressor(n_estimators=300, max_depth=15, random_state=args.seed, n_jobs=-1)
        model.fit(train_data[features], train_data['target_eps'])
        
        preds = model.predict(test_data[features])
        mae = mean_absolute_error(test_data['target_eps'], preds)
        
        print(f"Fold Year {test_year}: 訓練筆數={len(train_data)}, 測試筆數={len(test_data)}, MAE={mae:.4f}")
        fold_results.append(mae)

    print(f"\n跨年平均 MAE: {np.mean(fold_results):.4f}")

    # --- 最終生產模型訓練 ---
    # 使用所有可用資料進行最終訓練
    print("\n--- 訓練最終生產模型 ---")
    final_model = RandomForestRegressor(n_estimators=500, max_depth=15, random_state=args.seed, n_jobs=-1)
    final_model.fit(df[features], df['target_eps'])
    
    # 顯示特徵重要性
    print("\n特徵重要性排名 (Top 10):")
    importances = pd.Series(final_model.feature_importances_, index=features).sort_values(ascending=False)
    print(importances.head(10))

    # --- 指標個股個案研究 (Addressing Reviewer Issue #5) ---
    if args.sample_symbols:
        print(f"\n[個股案例] 針對 {args.target_year}{args.target_quarter} 的預測對比:")
        # 僅在最後一年進行樣本展示
        last_year_df = df[df['year'] == unique_years[-1]].copy()
        last_year_df['symbol'] = last_year_df['symbol'].astype(str)
        
        # 進行預測
        last_year_df['v4_pred'] = final_model.predict(last_year_df[features])
        
        samples = args.sample_symbols.split(',')
        results = last_year_df[last_year_df['symbol'].isin(samples)][['symbol', 'name', 'target_eps', 'v4_pred']]
        if not results.empty:
            print(results)
        else:
            print("  (未在資料集中找到指定的樣本股票)")

    # --- 資料庫持久化 (Addressing Reviewer Issue #1 - Explicit Flag) ---
    if args.save_db:
        print(f"\n正在執行資料庫寫入... (Target: {args.target_year}{args.target_quarter})")
        # 預測當前最新的資料集
        df_to_save = df[df['year'] == unique_years[-1]].copy()
        df_to_save['predict_eps'] = final_model.predict(df_to_save[features])
        
        save_eps_predictions(
            df_to_save[['symbol', 'predict_eps']], 
            target_quarter=f"{args.target_year}{args.target_quarter}", 
            model_version='v4'
        )
    else:
        print("\n跳過資料庫寫入 (--save-db 未開啟)。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V4 模型訓練與生產評估腳本")
    parser.add_argument("--dataset", type=str, default="analysis/v4/dataset.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-year", type=int, default=2024, help="生產寫入的目標年份")
    parser.add_argument("--target-quarter", type=str, default="Q3", help="生產寫入的目標季度")
    parser.add_argument("--sample-symbols", type=str, default="2330,2317,2454,1795,3704", help="個案研究的股票代號(逗號分隔)")
    parser.add_argument("--save-db", action="store_true", help="顯式開關：是否將結果寫入資料庫")
    
    args = parser.parse_args()
    run_training_and_eval(args)
