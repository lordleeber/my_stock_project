"""Unit tests for strategies.step5_score_and_publish.ensemble_score.

ensemble_score 把 K 顆 selection model 的預測合成單一 ml_score（越大越好，給
run_rolling 降冪排序用）。這些測試鎖死它的合約，避免日後改 step5 不小心破壞：

  - 單顆 + agg='score' 必須位元等價於 model.predict（舊 payload 向後相容）
  - agg='score' 是各顆 raw predict 的平均
  - agg='rank'  是各顆 rank 平均後取負（-mean_rank，仍 monotone-increasing）
  - agg='rank'  對「某顆 score scale 爆大」較 robust（這是它存在的理由）
  - 回傳值依 X 的列順序對位（positional），與 index 值無關 —— step5 之後
    直接 `df["ml_score"] = ensemble_score(...)`，靠的就是這個對位保證
  - 未知 agg 必須 raise ValueError

執行（venv 未裝 pytest 也能跑）：
  venv/bin/python3 strategies/tests/test_ensemble_score.py     # 內建 runner
  venv/bin/python3 -m pytest strategies/tests/test_ensemble_score.py   # 若有 pytest
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 將專案根目錄加入路徑（與 processor/tests/test_quarterly_logic.py 同慣例）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from strategies.step5_score_and_publish import ensemble_score  # noqa: E402


class FakeModel:
    """最小 selection-model stub：predict 回傳預設分數，長度須對齊 X。

    ensemble_score 只用到 model.predict(X)，所以不需真的 LGBMRanker —— 也讓測試
    不依賴 lightgbm、毫秒級完成。
    """

    def __init__(self, preds):
        self._preds = np.asarray(preds, dtype=float)

    def predict(self, X):
        assert len(X) == len(self._preds), "stub preds 長度需與 X 列數一致"
        return self._preds.copy()


def _make_X(n, index=None):
    """造一個 n 列、欄位內容無關緊要的 feature frame（FakeModel 不看內容）。"""
    return pd.DataFrame({"f1": range(n), "f2": range(n)}, index=index)


def test_single_model_score_equals_predict():
    """單顆 + agg='score' = model.predict —— 舊單 seed payload 向後相容。"""
    preds = [0.5, -0.3, 2.1, 0.0]
    m = FakeModel(preds)
    X = _make_X(len(preds))
    out = ensemble_score([m], X, "score")
    assert np.array_equal(out, np.asarray(preds))


def test_score_is_mean_of_raw_predictions():
    """agg='score' = 各顆 raw predict 的逐列平均。"""
    a = FakeModel([1.0, 2.0, 3.0])
    b = FakeModel([3.0, 2.0, 1.0])
    X = _make_X(3)
    out = ensemble_score([a, b], X, "score")
    assert np.allclose(out, [2.0, 2.0, 2.0])


def test_rank_agg_is_negative_mean_rank():
    """agg='rank'：每顆 desc rank（1=最佳）平均後取負；monotone-increasing。"""
    # A: 30>20>10 → 列 rank [3,2,1]；B: 25>15>5 → [3,2,1]
    a = FakeModel([10.0, 20.0, 30.0])
    b = FakeModel([5.0, 15.0, 25.0])
    X = _make_X(3)
    out = ensemble_score([a, b], X, "rank")
    # mean_rank = [3,2,1] → -mean_rank
    assert np.allclose(out, [-3.0, -2.0, -1.0])
    # 越大越好：最後一列（兩顆都評最佳）分數最高
    assert int(np.argmax(out)) == 2


def test_rank_agg_handles_ties_via_average_method():
    """method='average'：兩顆給相反排序時，rank 平均後應該全部打平。"""
    a = FakeModel([1.0, 2.0, 3.0])  # 列 rank [3,2,1]
    b = FakeModel([3.0, 2.0, 1.0])  # 列 rank [1,2,3]
    X = _make_X(3)
    out = ensemble_score([a, b], X, "rank")
    # mean_rank = [2,2,2] → 全平手
    assert np.allclose(out, [-2.0, -2.0, -2.0])


def test_rank_agg_is_robust_to_score_scale():
    """rank agg 存在的理由：壓掉「某顆 score scale 爆大」的支配效果。

    A 在第 2 列丟一個 1000 的離群值。'score' 會被它拉著走（第 2 列獨大），
    'rank' 只看序位，兩顆相反排序時打平 —— 證明 rank 對 scale 較 robust。
    """
    a = FakeModel([1.0, 2.0, 1000.0])
    b = FakeModel([3.0, 2.0, 1.0])
    X = _make_X(3)

    score_out = ensemble_score([a, b], X, "score")
    rank_out = ensemble_score([a, b], X, "rank")

    # score：A 的離群值支配 → 第 2 列獨大
    assert int(np.argmax(score_out)) == 2
    assert score_out[2] > score_out[0] and score_out[2] > score_out[1]

    # rank：離群尺度被中和 → 三列打平（ptp==0），與 score 的結論明顯不同
    assert np.ptp(rank_out) == 0.0


def test_output_is_positional_to_X_not_index_label():
    """回傳依 X 列順序對位，與 index 值無關（step5 直接位置賦值給 df 靠這點）。"""
    preds = [100.0, 200.0, 300.0]
    m = FakeModel(preds)
    # 非預設、非排序的 index
    X = _make_X(3, index=[5, 2, 9])

    score_out = ensemble_score([m], X, "score")
    assert np.array_equal(score_out, np.asarray(preds))  # 仍照列順序

    rank_out = ensemble_score([m], X, "rank")
    # 300>200>100 → 列 rank [3,2,1] → -[3,2,1]
    assert np.allclose(rank_out, [-3.0, -2.0, -1.0])


def test_unknown_agg_raises_value_error():
    """未知 agg 必須 fail-fast，不可悄悄回 None / 亂猜。"""
    m = FakeModel([1.0, 2.0])
    X = _make_X(2)
    try:
        ensemble_score([m], X, "median")
    except ValueError as exc:
        assert "median" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown agg")


def test_return_type_is_ndarray_length_matches():
    """合約：回傳 np.ndarray，長度 == len(X)（step5 賦值給 df 的一整欄）。"""
    a = FakeModel([1.0, 2.0, 3.0, 4.0])
    b = FakeModel([4.0, 3.0, 2.0, 1.0])
    X = _make_X(4)
    for agg in ("score", "rank"):
        out = ensemble_score([a, b], X, agg)
        assert isinstance(out, np.ndarray)
        assert out.shape == (4,)


def _run_all():
    """venv 未裝 pytest 時的內建 runner：跑完所有 test_* 並回報。"""
    tests = sorted(
        (name, fn)
        for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - test runner needs the catch-all
            failures.append((name, exc))
            print(f"FAIL  {name}: {exc!r}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
