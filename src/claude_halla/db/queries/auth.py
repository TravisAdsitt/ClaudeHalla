"""Token revocation table queries."""

from __future__ import annotations

import aiosqlite

from claude_halla.db.connection import transaction


async def revoke_token(
    db: aiosqlite.Connection,
    jti: str,
    revoked_at: str,
    expires_at: str,
) -> None:
    """Insert a revoked token JTI into the revocations table."""
    async with transaction(db):
        await db.execute(
            """
            INSERT OR IGNORE INTO token_revocations (jti, revoked_at, expires_at)
            VALUES (?, ?, ?);
            """,
            (jti, revoked_at, expires_at),
        )


async def is_token_revoked(db: aiosqlite.Connection, jti: str) -> bool:
    """Return True if the given JTI has been revoked."""
    cursor = await db.execute(
        "SELECT 1 FROM token_revocations WHERE jti = ?;",
        (jti,),
    )
    row = await cursor.fetchone()
    return row is not None


async def purge_expired_revocations(
    db: aiosqlite.Connection,
    cutoff_iso: str,
) -> int:
    """Delete revocation records whose tokens have long expired. Returns count removed."""
    cursor = await db.execute(
        "SELECT jti FROM token_revocations WHERE expires_at < ?;",
        (cutoff_iso,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    jtis = [r[0] for r in rows]
    placeholders = ",".join("?" * len(jtis))
    async with transaction(db):
        await db.execute(
            f"DELETE FROM token_revocations WHERE jti IN ({placeholders});",
            jtis,
        )
    return len(jtis)
