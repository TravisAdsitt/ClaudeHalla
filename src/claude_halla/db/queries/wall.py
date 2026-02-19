"""Wall post CRUD queries."""

from __future__ import annotations

from typing import Any

import aiosqlite

from claude_halla.db.connection import transaction
from claude_halla.util.time import utcnow_iso


async def insert_wall_post(
    db: aiosqlite.Connection,
    post_id: str,
    username: str,
    content: str,
    posted_at: str,
    expires_at: str,
    project_key: str | None,
) -> None:
    async with transaction(db):
        await db.execute(
            """
            INSERT INTO wall_posts (id, username, content, project_key, posted_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active');
            """,
            (post_id, username, content, project_key, posted_at, expires_at),
        )


async def retract_wall_post(
    db: aiosqlite.Connection,
    post_id: str,
    username: str,
) -> dict[str, Any] | None:
    """
    Retract a post owned by username. Returns the post row or None if not found/not owned.
    """
    cursor = await db.execute(
        "SELECT * FROM wall_posts WHERE id = ? AND username = ? AND status = 'active';",
        (post_id, username),
    )
    row = cursor.fetchone if False else await cursor.fetchone()
    if row is None:
        return None

    retracted_at = utcnow_iso()
    async with transaction(db):
        await db.execute(
            """
            UPDATE wall_posts
            SET status = 'retracted', retracted_at = ?
            WHERE id = ?;
            """,
            (retracted_at, post_id),
        )
    return dict(row)


async def get_active_wall_posts(
    db: aiosqlite.Connection,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """Return a page of active wall posts and the total active count."""
    cursor = await db.execute(
        "SELECT COUNT(*) FROM wall_posts WHERE status = 'active';"
    )
    row = await cursor.fetchone()
    total = row[0]

    offset = (page - 1) * page_size
    cursor = await db.execute(
        """
        SELECT * FROM wall_posts
        WHERE status = 'active'
        ORDER BY posted_at DESC
        LIMIT ? OFFSET ?;
        """,
        (page_size, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows], total


async def get_wall_posts_for_user(
    db: aiosqlite.Connection,
    username: str,
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        "SELECT * FROM wall_posts WHERE username = ? AND status = 'active' ORDER BY posted_at DESC;",
        (username,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def expire_overdue_posts(
    db: aiosqlite.Connection,
    now_iso: str,
) -> list[dict[str, Any]]:
    """
    Find all active posts past their expires_at, mark them expired, and return them.
    """
    cursor = await db.execute(
        "SELECT * FROM wall_posts WHERE status = 'active' AND expires_at <= ?;",
        (now_iso,),
    )
    rows = await cursor.fetchall()
    posts = [dict(r) for r in rows]

    if not posts:
        return []

    ids = [p["id"] for p in posts]
    placeholders = ",".join("?" * len(ids))
    async with transaction(db):
        await db.execute(
            f"UPDATE wall_posts SET status = 'expired' WHERE id IN ({placeholders});",
            ids,
        )
    return posts


async def get_wall_post_by_id(
    db: aiosqlite.Connection,
    post_id: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM wall_posts WHERE id = ?;",
        (post_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None
