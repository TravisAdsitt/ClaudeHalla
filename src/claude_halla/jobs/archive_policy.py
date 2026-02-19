"""Daily archive policy job: provisional key lifecycle management."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiosqlite

from claude_halla.config import AppConfig
from claude_halla.db.queries.archive import (
    flag_stale_provisional_projects,
    hard_delete_soft_archived_provisional_projects,
    soft_archive_flagged_provisional_projects,
)
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def archive_policy_job(db: aiosqlite.Connection, config: AppConfig) -> None:
    """
    Manage provisional project key lifecycle:
    1. Flag active provisional keys with no activity for flag_after_days.
    2. Soft-archive flagged keys after soft_archive_after_days.
    3. Hard-delete soft-archived keys (and their archived_signals) after hard_delete_after_days.
    """
    now = utcnow()
    now_iso = now.isoformat()

    try:
        flag_cutoff = (now - timedelta(days=config.archive.provisional_flag_after_days)).isoformat()
        flagged = await flag_stale_provisional_projects(db, flag_cutoff, now_iso)
        if flagged:
            logger.info("Flagged %d stale provisional projects", flagged)

        soft_cutoff = (now - timedelta(days=config.archive.provisional_soft_archive_after_days)).isoformat()
        soft_archived = await soft_archive_flagged_provisional_projects(db, soft_cutoff, now_iso)
        if soft_archived:
            logger.info("Soft-archived %d flagged provisional projects", soft_archived)

        hard_cutoff = (now - timedelta(days=config.archive.provisional_hard_delete_after_days)).isoformat()
        hard_deleted = await hard_delete_soft_archived_provisional_projects(db, hard_cutoff)
        if hard_deleted:
            logger.info("Hard-deleted %d soft-archived provisional projects", hard_deleted)

    except Exception:
        logger.exception("Error in archive_policy_job")
