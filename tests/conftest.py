import os
from pathlib import Path

from dotenv import load_dotenv

_ = load_dotenv(Path(__file__).resolve().parents[1] / ".env")

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/neomarket_test",
)
_ = os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
