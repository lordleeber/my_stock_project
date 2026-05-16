"""共用 DB 連線資訊。host 端 venv 跑的腳本（train_eps/strategies/backtester）走這支。

Docker container 內執行的服務（importer/calculator/backend）另有自己的 env-var
版本，預設指向 docker compose 內部 service network（host=db, port=5432）；兩派
defaults 不同，請勿合併。
"""


def get_db_url() -> str:
    return "postgresql://user:password@localhost:5419/stock_db"
