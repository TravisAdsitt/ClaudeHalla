"""Shared aiosqlite connection and transaction helper."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from claude_halla.db.migrations import run_migrations


_db: aiosqlite.Connection | None = None


async def open_db(path: str) -> aiosqlite.Connection:
    """Open the shared database connection and run migrations."""
    global _db
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await run_migrations(_db)
    return _db


async def close_db() -> None:
    """Close the shared database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    """Return the active database connection. Raises if not yet opened."""
    if _db is None:
        raise RuntimeError("Database connection has not been opened.")
    return _db


@asynccontextmanager
async def transaction(db: aiosqlite.Connection) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that wraps operations in a BEGIN/COMMIT transaction.
    Rolls back on exception.
    """
    await db.execute("BEGIN;")
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
