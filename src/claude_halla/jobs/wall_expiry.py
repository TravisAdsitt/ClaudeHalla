"""Wall post TTL expiry + archival job."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiosqlite

from claude_halla.db.queries.archive import insert_archived_signal, touch_project_last_active
from claude_halla.db.queries.auth import purge_expired_revocations
from claude_halla.db.queries.wall import expire_overdue_posts
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def wall_expiry_job(db: aiosqlite.Connection) -> None:
    """
    Expire wall posts past their TTL:
    1. Move expired posts to archived_signals.
    2. Touch projects.last_active_at for affected project keys.
    3. Purge token_revocations rows whose tokens expired > 1 day ago.
    """
    now = utcnow()
    now_iso = now.isoformat()

    try:
        expired_posts = await expire_overdue_posts(db, now_iso)
        if expired_posts:
            logger.info("Expired %d wall posts", len(expired_posts))

        for post in expired_posts:
            project_key = post.get("project_key") or "unknown"
            await insert_archived_signal(
                db,
                signal_id=post["id"],
                project_key=project_key,
                username=post["username"],
                content=post["content"],
                posted_at=post["posted_at"],
                expired_at=now_iso,
                archive_reason="expired",
            )
            if post.get("project_key"):
                await touch_project_last_active(db, post["project_key"], now_iso)

        # Purge revocation records for tokens that expired more than 1 day ago
        cutoff = (now - timedelta(days=1)).isoformat()
        purged = await purge_expired_revocations(db, cutoff)
        if purged:
            logger.info("Purged %d expired token revocations", purged)

    except Exception:
        logger.exception("Error in wall_expiry_job")
