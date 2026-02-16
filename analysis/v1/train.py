import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

def train_v1():
    """
    執行 V1 模型的訓練與評估
    使用隨機森林 (Random Forest) 演算法來學習財報與營收之間的非線性關係
    """
    # 讀取資料並移除空值 (避免模型訓練失敗)
    df = pd.read_csv("analysis/v1/dataset.csv").dropna()
    
    # 定義輸入特徵：營收、淨利率、前一季 EPS、Q3 實質總營收
    features = ['q2_rev', 'q2_margin', 'q2_eps', 'q3_rev_total']
    
    X = df[features]
    y = df['target_eps']
    
    # 初始化並訓練隨機森林模型
    # n_estimators=100 代表使用 100 顆決策樹進行投票
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # 進行預測並計算平均絕對誤差 (MAE)
    preds = model.predict(X)
    mae = mean_absolute_error(y, preds)
    
    # 建立基準線 (Baseline)：直接假設 Q3 獲利會等於 Q2 (這是最簡單的預測)
    # 我們機器學習的 MAE 必須低於這個數值才有存在價值
    mae_baseline = mean_absolute_error(y, df['q2_eps'])
    
    print("--- V1 模型評估結果 ---")
    print(f"隨機森林預測 MAE (越小越好): {mae:.4f}")
    print(f"簡單基準 (假設 Q3=Q2) MAE:   {mae_baseline:.4f}")
    print("\n[註解] V1 在單一季度上表現優異，但缺乏跨年度季節性的感知。")

if __name__ == "__main__":
    train_v1()
