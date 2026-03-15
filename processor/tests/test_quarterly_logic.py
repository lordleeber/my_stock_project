import sys
from pathlib import Path

# 將專案根目錄加入路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# 模擬 calculate_yoy 函數 (或直接從模組匯入，如果已經重構成可匯入的形式)
def calculate_yoy(current, last_year):
    if last_year is None or last_year == 0:
        return None
    try:
        # 使用 abs(last_year) 處理虧轉盈的情況
        return round((current - last_year) / abs(last_year) * 100, 2)
    except Exception:
        return None


def test_yoy_calculation_positive():
    """測試一般的增長情況"""
    assert calculate_yoy(150, 100) == 50.0
    assert calculate_yoy(120, 100) == 20.0


def test_yoy_calculation_negative_growth():
    """測試衰退情況"""
    assert calculate_yoy(80, 100) == -20.0
    assert calculate_yoy(50, 100) == -50.0


def test_yoy_calculation_虧轉盈():
    """
    測試虧轉盈的情況。
    去年 -100, 今年 50。
    公式: (50 - (-100)) / abs(-100) * 100 = 150%
    """
    assert calculate_yoy(50, -100) == 150.0


def test_yoy_calculation_盈轉虧():
    """
    測試盈轉虧的情況。
    去年 100, 今年 -50。
    公式: (-50 - 100) / 100 * 100 = -150%
    """
    assert calculate_yoy(-50, 100) == -150.0


def test_yoy_calculation_虧損擴大():
    """
    測試虧損擴大的情況。
    去年 -100, 今年 -150。
    公式: (-150 - (-100)) / abs(-100) * 100 = -50 / 100 * 100 = -50%
    """
    assert calculate_yoy(-150, -100) == -50.0


def test_yoy_calculation_虧損縮小():
    """
    測試虧損縮小的情況。
    去年 -100, 今年 -50。
    公式: (-50 - (-100)) / abs(-100) * 100 = 50 / 100 * 100 = 50%
    """
    assert calculate_yoy(-50, -100) == 50.0


def test_yoy_zero_denominator():
    """測試分母為 0 的情況"""
    assert calculate_yoy(100, 0) is None
    assert calculate_yoy(100, None) is None
