"""
Kiểm tra DATABASE_URL (async SQLAlchemy + asyncpg).
Chạy từ thư mục gốc repo:
  pip install -r scripts/requirements-db-test.txt
  python scripts/test_db_connection.py
Ưu tiên đọc DATABASE_URL từ file .env ở thư mục gốc; không có thì dùng default bên dưới.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://moni:123456@localhost:5432/moni",
)


async def main() -> None:
    print("Using:", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)
    engine = create_async_engine(DATABASE_URL, echo=True)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("Connected OK:", result.scalar())
    except Exception as e:
        print("Connection failed:")
        print(e)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
