"""Daily registry cleanup job: soft-archive and hard-delete stale entries."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiosqlite

from claude_halla.config import AppConfig
from claude_halla.db.queries.registry import hard_delete_stale_entries, soft_archive_stale_entries
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def registry_cleanup_job(db: aiosqlite.Connection, config: AppConfig) -> None:
    """
    Soft-archive registry entries with no activity for soft_archive_after_days.
    Hard-delete entries that have been soft-archived for hard_delete_after_days.
    """
    now = utcnow()
    now_iso = now.isoformat()

    try:
        soft_cutoff = (now - timedelta(days=config.registry.soft_archive_after_days)).isoformat()
        soft_count = await soft_archive_stale_entries(db, soft_cutoff, now_iso)
        if soft_count:
            logger.info("Soft-archived %d stale registry entries", soft_count)

        hard_cutoff = (now - timedelta(days=config.registry.hard_delete_after_days)).isoformat()
        hard_count = await hard_delete_stale_entries(db, hard_cutoff, now_iso)
        if hard_count:
            logger.info("Hard-deleted %d stale registry entries", hard_count)

    except Exception:
        logger.exception("Error in registry_cleanup_job")
