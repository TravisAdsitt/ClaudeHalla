"""Registry entry CRUD queries."""

from __future__ import annotations

from typing import Any

import aiosqlite

from claude_halla.db.connection import transaction
from claude_halla.util.time import utcnow_iso


async def get_registry_entry_by_url(
    db: aiosqlite.Connection,
    repo_url: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM registry_entries WHERE repo_url = ?;",
        (repo_url,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_registry_entry_by_id(
    db: aiosqlite.Connection,
    entry_id: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM registry_entries WHERE id = ?;",
        (entry_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def insert_registry_entry(
    db: aiosqlite.Connection,
    entry_id: str,
    repo_url: str,
    description: str,
    now_iso: str,
) -> None:
    async with transaction(db):
        await db.execute(
            """
            INSERT INTO registry_entries (id, repo_url, description, added_at, last_seen_at, status)
            VALUES (?, ?, ?, ?, ?, 'active');
            """,
            (entry_id, repo_url, description, now_iso, now_iso),
        )


async def update_registry_entry(
    db: aiosqlite.Connection,
    repo_url: str,
    description: str,
) -> dict[str, Any] | None:
    """Update description of an active registry entry. Returns updated row or None."""
    cursor = await db.execute(
        "SELECT id FROM registry_entries WHERE repo_url = ? AND status = 'active';",
        (repo_url,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    entry_id = row[0]
    async with transaction(db):
        await db.execute(
            "UPDATE registry_entries SET description = ? WHERE id = ?;",
            (description, entry_id),
        )

    cursor = await db.execute(
        "SELECT * FROM registry_entries WHERE id = ?;",
        (entry_id,),
    )
    updated = await cursor.fetchone()
    return dict(updated) if updated else None


async def touch_registry_entry(
    db: aiosqlite.Connection,
    repo_url: str,
    now_iso: str,
) -> None:
    """Update last_seen_at for a registry entry."""
    async with transaction(db):
        await db.execute(
            "UPDATE registry_entries SET last_seen_at = ? WHERE repo_url = ? AND status = 'active';",
            (now_iso, repo_url),
        )


async def get_active_registry_entries(
    db: aiosqlite.Connection,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM registry_entries WHERE status = 'active';"
    )
    row = await cursor.fetchone()
    total = row[0]

    offset = (page - 1) * page_size
    cursor = await db.execute(
        """
        SELECT * FROM registry_entries
        WHERE status = 'active'
        ORDER BY last_seen_at DESC
        LIMIT ? OFFSET ?;
        """,
        (page_size, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows], total


async def soft_archive_stale_entries(
    db: aiosqlite.Connection,
    cutoff_iso: str,
    now_iso: str,
) -> int:
    """Soft-archive active entries with last_seen_at older than cutoff. Returns count."""
    cursor = await db.execute(
        """
        SELECT id FROM registry_entries
        WHERE status = 'active' AND last_seen_at < ?;
        """,
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    ids = [r[0] for r in rows]
    placeholders = ",".join("?" * len(ids))
    async with transaction(db):
        await db.execute(
            f"""
            UPDATE registry_entries
            SET status = 'soft_archived', soft_archived_at = ?
            WHERE id IN ({placeholders});
            """,
            [now_iso] + ids,
        )
    return len(ids)


async def hard_delete_stale_entries(
    db: aiosqlite.Connection,
    cutoff_iso: str,
    now_iso: str,
) -> int:
    """Hard-delete soft_archived entries older than cutoff. Returns count."""
    cursor = await db.execute(
        """
        SELECT id FROM registry_entries
        WHERE status = 'soft_archived' AND soft_archived_at < ?;
        """,
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    ids = [r[0] for r in rows]
    placeholders = ",".join("?" * len(ids))
    async with transaction(db):
        await db.execute(
            f"""
            UPDATE registry_entries
            SET status = 'hard_deleted', hard_deleted_at = ?
            WHERE id IN ({placeholders});
            """,
            [now_iso] + ids,
        )
    return len(ids)
