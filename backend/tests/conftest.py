import os
import pytest
from sqlalchemy import create_engine


def _ensure_db_env():
    # Defaults match docker-compose.yml
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_USER", "user")
    os.environ.setdefault("DB_PASSWORD", "password")
    os.environ.setdefault("DB_NAME", "stock_db")


def _db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


@pytest.fixture(scope="session")
def engine():
    _ensure_db_env()
    return create_engine(_db_url())
