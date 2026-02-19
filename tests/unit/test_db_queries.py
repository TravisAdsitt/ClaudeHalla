"""Unit tests for database queries."""

from __future__ import annotations

import uuid

import pytest

from claude_halla.db.queries.auth import is_token_revoked, purge_expired_revocations, revoke_token
from claude_halla.db.queries.registry import (
    get_active_registry_entries,
    get_registry_entry_by_url,
    insert_registry_entry,
    soft_archive_stale_entries,
    update_registry_entry,
)
from claude_halla.db.queries.wall import (
    expire_overdue_posts,
    get_active_wall_posts,
    get_wall_posts_for_user,
    insert_wall_post,
    retract_wall_post,
)
from claude_halla.db.queries.archive import (
    get_projects_for_user,
    get_recent_archived_signals_for_user,
    insert_archived_signal,
    upsert_project,
)


# ── Wall tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_and_read_wall_post(db):
    post_id = str(uuid.uuid4())
    await insert_wall_post(
        db,
        post_id=post_id,
        username="alice",
        content="Working on auth module",
        posted_at="2024-01-01T00:00:00+00:00",
        expires_at="2024-01-03T00:00:00+00:00",
        project_key=None,
    )
    posts, total = await get_active_wall_posts(db, page=1, page_size=20)
    assert total == 1
    assert posts[0]["id"] == post_id
    assert posts[0]["username"] == "alice"


@pytest.mark.asyncio
async def test_retract_wall_post(db):
    post_id = str(uuid.uuid4())
    await insert_wall_post(
        db,
        post_id=post_id,
        username="alice",
        content="Signal",
        posted_at="2024-01-01T00:00:00+00:00",
        expires_at="2024-01-03T00:00:00+00:00",
        project_key=None,
    )
    result = await retract_wall_post(db, post_id, "alice")
    assert result is not None

    posts, total = await get_active_wall_posts(db, 1, 20)
    assert total == 0


@pytest.mark.asyncio
async def test_retract_other_users_post_returns_none(db):
    post_id = str(uuid.uuid4())
    await insert_wall_post(
        db,
        post_id=post_id,
        username="alice",
        content="Signal",
        posted_at="2024-01-01T00:00:00+00:00",
        expires_at="2024-01-03T00:00:00+00:00",
        project_key=None,
    )
    result = await retract_wall_post(db, post_id, "bob")
    assert result is None


@pytest.mark.asyncio
async def test_expire_overdue_posts(db):
    post_id = str(uuid.uuid4())
    await insert_wall_post(
        db,
        post_id=post_id,
        username="alice",
        content="Old post",
        posted_at="2024-01-01T00:00:00+00:00",
        expires_at="2024-01-02T00:00:00+00:00",
        project_key=None,
    )
    expired = await expire_overdue_posts(db, "2024-01-03T00:00:00+00:00")
    assert len(expired) == 1
    assert expired[0]["id"] == post_id

    posts, total = await get_active_wall_posts(db, 1, 20)
    assert total == 0


# ── Registry tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_and_read_registry_entry(db):
    entry_id = str(uuid.uuid4())
    await insert_registry_entry(
        db, entry_id, "https://git.company.com/org/repo", "A cool repo", "2024-01-01T00:00:00+00:00"
    )
    entries, total = await get_active_registry_entries(db, 1, 20)
    assert total == 1
    assert entries[0]["repo_url"] == "https://git.company.com/org/repo"


@pytest.mark.asyncio
async def test_update_registry_entry(db):
    entry_id = str(uuid.uuid4())
    await insert_registry_entry(db, entry_id, "https://git.company.com/repo", "Old desc", "2024-01-01T00:00:00+00:00")
    updated = await update_registry_entry(db, "https://git.company.com/repo", "New desc")
    assert updated is not None
    assert updated["description"] == "New desc"


@pytest.mark.asyncio
async def test_soft_archive_stale_registry_entries(db):
    entry_id = str(uuid.uuid4())
    await insert_registry_entry(
        db, entry_id, "https://git.company.com/repo", "desc", "2024-01-01T00:00:00+00:00"
    )
    count = await soft_archive_stale_entries(db, "2024-06-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00")
    assert count == 1

    entries, total = await get_active_registry_entries(db, 1, 20)
    assert total == 0


# ── Auth queries ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_and_check_token(db):
    jti = str(uuid.uuid4())
    assert not await is_token_revoked(db, jti)
    await revoke_token(db, jti, "2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00")
    assert await is_token_revoked(db, jti)


@pytest.mark.asyncio
async def test_purge_expired_revocations(db):
    jti = str(uuid.uuid4())
    await revoke_token(db, jti, "2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00")
    count = await purge_expired_revocations(db, "2024-01-03T00:00:00+00:00")
    assert count == 1
    assert not await is_token_revoked(db, jti)


# ── Archive queries ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_project(db):
    await upsert_project(db, "https://git.company.com/repo", "repo", "alice", "2024-01-01T00:00:00+00:00")
    projects = await get_projects_for_user(db, "alice")
    assert len(projects) == 1
    assert projects[0]["key"] == "https://git.company.com/repo"


@pytest.mark.asyncio
async def test_insert_archived_signal(db):
    signal_id = str(uuid.uuid4())
    await insert_archived_signal(
        db, signal_id, "proj-key", "alice", "content", "2024-01-01T00:00:00+00:00",
        "2024-01-03T00:00:00+00:00", "expired"
    )
    archived = await get_recent_archived_signals_for_user(db, "alice")
    assert len(archived) == 1
    assert archived[0]["id"] == signal_id
