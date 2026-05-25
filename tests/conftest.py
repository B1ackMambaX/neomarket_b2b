import os

# Must be set before any app module is imported so pydantic-settings picks them up.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
