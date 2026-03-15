"""
共用 HTTP 客戶端，包含重試機制
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

from common.constants import API_BASE, HTTP_TIMEOUT, HTTP_RETRIES, HTTP_BACKOFF_FACTOR


def create_session() -> requests.Session:
    """建立帶有重試機制的 requests Session"""
    session = requests.Session()

    retry_strategy = Retry(
        total=HTTP_RETRIES,
        backoff_factor=HTTP_BACKOFF_FACTOR,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# 全域 session 實例
_session = None


def get_session() -> requests.Session:
    """取得全域 session (懶載入)"""
    global _session
    if _session is None:
        _session = create_session()
    return _session


def fetch_json(endpoint: str, params: dict = None, timeout: int = None) -> list | dict:
    """
    從 API 取得 JSON 資料

    Args:
        endpoint: API 端點路徑 (例如 "/raw/daily-quotes")
        params: 查詢參數
        timeout: 請求超時時間 (秒)

    Returns:
        JSON 資料 (list 或 dict)

    Raises:
        requests.RequestException: 請求失敗時
    """
    url = f"{API_BASE}{endpoint}"
    timeout = timeout or HTTP_TIMEOUT

    response = get_session().get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_dataframe(
    endpoint: str, params: dict = None, timeout: int = None
) -> pd.DataFrame:
    """
    從 API 取得資料並轉換為 DataFrame

    Args:
        endpoint: API 端點路徑
        params: 查詢參數
        timeout: 請求超時時間 (秒)

    Returns:
        pd.DataFrame，若無資料則回傳空 DataFrame
    """
    try:
        data = fetch_json(endpoint, params, timeout)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()
    except requests.RequestException as e:
        print(f"[HTTP Error] {endpoint}: {e}")
        return pd.DataFrame()
