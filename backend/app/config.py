import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is Agent/ (three levels up from backend/app/config.py).
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    anthropic_api_key: str = os.environ["ANTHROPIC_API_KEY"]

    # Plain postgresql:// DSN — used as-is by the sync psycopg connection
    # the query_db tool opens, and adapted below for the async SQLModel engine.
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://expense_user:expense_pass@localhost:5432/expense_db",
    )

    docs_dir: Path = BASE_DIR / "docs"

    cors_origins: list[str] = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173"
    ).split(",")

    @property
    def database_url_async(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


settings = Settings()
