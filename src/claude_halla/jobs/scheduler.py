"""APScheduler AsyncIOScheduler wired into the FastMCP lifespan."""

from __future__ import annotations

import logging

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_halla.config import AppConfig
from claude_halla.jobs.archive_policy import archive_policy_job
from claude_halla.jobs.registry_cleanup import registry_cleanup_job
from claude_halla.jobs.wall_expiry import wall_expiry_job

logger = logging.getLogger(__name__)


def build_scheduler(db: aiosqlite.Connection, config: AppConfig) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance (not yet started)."""
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        wall_expiry_job,
        trigger="interval",
        minutes=config.jobs.expiry_interval_minutes,
        kwargs={"db": db},
        id="wall_expiry",
        replace_existing=True,
    )

    scheduler.add_job(
        registry_cleanup_job,
        trigger="interval",
        hours=config.jobs.cleanup_interval_hours,
        kwargs={"db": db, "config": config},
        id="registry_cleanup",
        replace_existing=True,
    )

    scheduler.add_job(
        archive_policy_job,
        trigger="interval",
        hours=config.jobs.cleanup_interval_hours,
        kwargs={"db": db, "config": config},
        id="archive_policy",
        replace_existing=True,
    )

    return scheduler
