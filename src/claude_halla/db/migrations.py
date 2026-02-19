"""Database schema creation and migrations."""

from __future__ import annotations

import aiosqlite


SCHEMA_VERSION = 1

_CREATE_WALL_POSTS = """
CREATE TABLE IF NOT EXISTS wall_posts (
    id          TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    content     TEXT NOT NULL,
    project_key TEXT,
    posted_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    retracted_at TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'retracted'))
);
"""

_CREATE_WALL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wall_status_expires ON wall_posts (status, expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_wall_username ON wall_posts (username);",
    "CREATE INDEX IF NOT EXISTS idx_wall_project_key ON wall_posts (project_key);",
]

_CREATE_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    key                          TEXT PRIMARY KEY,
    key_type                     TEXT NOT NULL CHECK (key_type IN ('repo', 'provisional')),
    canonical_username           TEXT,
    created_at                   TEXT NOT NULL,
    last_active_at               TEXT NOT NULL,
    provisional_status           TEXT NOT NULL DEFAULT 'active'
        CHECK (provisional_status IN ('active', 'flagged', 'soft_archived', 'hard_deleted')),
    provisional_flagged_at       TEXT,
    provisional_soft_archived_at TEXT,
    graduated_to_repo_key        TEXT
);
"""

_CREATE_ARCHIVED_SIGNALS = """
CREATE TABLE IF NOT EXISTS archived_signals (
    id             TEXT PRIMARY KEY,
    project_key    TEXT NOT NULL,
    username       TEXT NOT NULL,
    content        TEXT NOT NULL,
    posted_at      TEXT NOT NULL,
    expired_at     TEXT NOT NULL,
    archive_reason TEXT NOT NULL CHECK (archive_reason IN ('expired', 'retracted'))
);
"""

_CREATE_ARCHIVED_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_arch_project_key ON archived_signals (project_key);",
    "CREATE INDEX IF NOT EXISTS idx_arch_username ON archived_signals (username);",
]

_CREATE_REGISTRY_ENTRIES = """
CREATE TABLE IF NOT EXISTS registry_entries (
    id              TEXT PRIMARY KEY,
    repo_url        TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    added_at        TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'soft_archived', 'hard_deleted')),
    soft_archived_at TEXT,
    hard_deleted_at  TEXT
);
"""

_CREATE_TOKEN_REVOCATIONS = """
CREATE TABLE IF NOT EXISTS token_revocations (
    jti        TEXT PRIMARY KEY,
    revoked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Apply all schema migrations to the database."""
    # Enable WAL mode and foreign key enforcement
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")

    # Create schema_version table and check current version
    await db.execute(_CREATE_SCHEMA_VERSION)
    await db.commit()

    cursor = await db.execute("SELECT version FROM schema_version LIMIT 1;")
    row = await cursor.fetchone()
    current_version = row[0] if row else 0

    if current_version >= SCHEMA_VERSION:
        return

    # Apply all DDL
    await db.execute(_CREATE_WALL_POSTS)
    for idx in _CREATE_WALL_INDEXES:
        await db.execute(idx)

    await db.execute(_CREATE_PROJECTS)

    await db.execute(_CREATE_ARCHIVED_SIGNALS)
    for idx in _CREATE_ARCHIVED_INDEXES:
        await db.execute(idx)

    await db.execute(_CREATE_REGISTRY_ENTRIES)
    await db.execute(_CREATE_TOKEN_REVOCATIONS)

    if current_version == 0:
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,)
        )
    else:
        await db.execute(
            "UPDATE schema_version SET version = ?;", (SCHEMA_VERSION,)
        )

    await db.commit()
