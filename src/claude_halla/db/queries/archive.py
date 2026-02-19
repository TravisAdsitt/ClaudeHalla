"""Archival, graduation, and project memory queries."""

from __future__ import annotations

from typing import Any

import aiosqlite

from claude_halla.db.connection import transaction
from claude_halla.util.time import utcnow_iso


async def upsert_project(
    db: aiosqlite.Connection,
    key: str,
    key_type: str,
    canonical_username: str,
    now_iso: str,
) -> None:
    """Insert or update a project row, touching last_active_at."""
    async with transaction(db):
        await db.execute(
            """
            INSERT INTO projects (key, key_type, canonical_username, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                last_active_at = excluded.last_active_at;
            """,
            (key, key_type, canonical_username, now_iso, now_iso),
        )


async def get_project(
    db: aiosqlite.Connection,
    key: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM projects WHERE key = ?;",
        (key,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_projects_for_user(
    db: aiosqlite.Connection,
    username: str,
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT * FROM projects
        WHERE canonical_username = ?
        ORDER BY last_active_at DESC;
        """,
        (username,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def insert_archived_signal(
    db: aiosqlite.Connection,
    signal_id: str,
    project_key: str,
    username: str,
    content: str,
    posted_at: str,
    expired_at: str,
    archive_reason: str,
) -> None:
    async with transaction(db):
        await db.execute(
            """
            INSERT OR IGNORE INTO archived_signals
            (id, project_key, username, content, posted_at, expired_at, archive_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (signal_id, project_key, username, content, posted_at, expired_at, archive_reason),
        )


async def get_recent_archived_signals_for_user(
    db: aiosqlite.Connection,
    username: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT * FROM archived_signals
        WHERE username = ?
        ORDER BY expired_at DESC
        LIMIT ?;
        """,
        (username, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def touch_project_last_active(
    db: aiosqlite.Connection,
    key: str,
    now_iso: str,
) -> None:
    async with transaction(db):
        await db.execute(
            "UPDATE projects SET last_active_at = ? WHERE key = ?;",
            (now_iso, key),
        )


# --- Provisional key lifecycle ---

async def flag_stale_provisional_projects(
    db: aiosqlite.Connection,
    cutoff_iso: str,
    now_iso: str,
) -> int:
    """Flag active provisional projects with no activity since cutoff. Returns count."""
    cursor = await db.execute(
        """
        SELECT key FROM projects
        WHERE key_type = 'provisional'
          AND provisional_status = 'active'
          AND last_active_at < ?;
        """,
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    keys = [r[0] for r in rows]
    placeholders = ",".join("?" * len(keys))
    async with transaction(db):
        await db.execute(
            f"""
            UPDATE projects
            SET provisional_status = 'flagged', provisional_flagged_at = ?
            WHERE key IN ({placeholders});
            """,
            [now_iso] + keys,
        )
    return len(keys)


async def soft_archive_flagged_provisional_projects(
    db: aiosqlite.Connection,
    cutoff_iso: str,
    now_iso: str,
) -> int:
    """Soft-archive provisional projects flagged before cutoff. Returns count."""
    cursor = await db.execute(
        """
        SELECT key FROM projects
        WHERE key_type = 'provisional'
          AND provisional_status = 'flagged'
          AND provisional_flagged_at < ?;
        """,
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    keys = [r[0] for r in rows]
    placeholders = ",".join("?" * len(keys))
    async with transaction(db):
        await db.execute(
            f"""
            UPDATE projects
            SET provisional_status = 'soft_archived', provisional_soft_archived_at = ?
            WHERE key IN ({placeholders});
            """,
            [now_iso] + keys,
        )
    return len(keys)


async def hard_delete_soft_archived_provisional_projects(
    db: aiosqlite.Connection,
    cutoff_iso: str,
) -> int:
    """Hard-delete soft_archived provisional projects older than cutoff. Returns count."""
    cursor = await db.execute(
        """
        SELECT key FROM projects
        WHERE key_type = 'provisional'
          AND provisional_status = 'soft_archived'
          AND provisional_soft_archived_at < ?;
        """,
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    keys = [r[0] for r in rows]
    placeholders = ",".join("?" * len(keys))
    async with transaction(db):
        # Cascade delete archived_signals for these project keys
        await db.execute(
            f"DELETE FROM archived_signals WHERE project_key IN ({placeholders});",
            keys,
        )
        await db.execute(
            f"UPDATE projects SET provisional_status = 'hard_deleted' WHERE key IN ({placeholders});",
            keys,
        )
    return len(keys)
