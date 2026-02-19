"""Full tool round-trip integration tests with in-memory SQLite + mocked LDAP."""

from __future__ import annotations

import uuid

import pytest
from mcp.shared.exceptions import McpError

from claude_halla.tools.wall import post_to_wall, read_wall, retract_post, get_user_summary
from claude_halla.tools.registry import add_to_registry, read_registry, update_registry_entry


# ── Wall round-trips ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_to_wall_and_read(db, jwt_manager, app_config, valid_token):
    result = await post_to_wall(
        token=valid_token,
        content="Working on the auth module",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    assert result.post_id
    assert result.expires_at

    read_result = await read_wall(valid_token, db, jwt_manager, app_config)
    assert read_result.total_active == 1
    assert read_result.posts[0].content == "Working on the auth module"


@pytest.mark.asyncio
async def test_post_to_wall_content_too_long(db, jwt_manager, app_config, valid_token):
    with pytest.raises(McpError):
        await post_to_wall(
            token=valid_token,
            content="x" * 2001,
            db=db,
            jwt_manager=jwt_manager,
            config=app_config,
        )


@pytest.mark.asyncio
async def test_retract_post(db, jwt_manager, app_config, valid_token):
    post = await post_to_wall(
        token=valid_token,
        content="Signal to retract",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    retracted = await retract_post(valid_token, post.post_id, db, jwt_manager)
    assert retracted.retracted is True

    read_result = await read_wall(valid_token, db, jwt_manager, app_config)
    assert read_result.total_active == 0


@pytest.mark.asyncio
async def test_retract_nonexistent_post_raises(db, jwt_manager, app_config, valid_token):
    with pytest.raises(McpError):
        await retract_post(valid_token, str(uuid.uuid4()), db, jwt_manager)


@pytest.mark.asyncio
async def test_get_user_summary(db, jwt_manager, app_config, valid_token):
    await post_to_wall(
        token=valid_token,
        content="Active signal",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    summary = await get_user_summary(valid_token, "testuser", db, jwt_manager)
    assert len(summary.active_posts) == 1
    assert summary.active_posts[0].username == "testuser"


@pytest.mark.asyncio
async def test_read_wall_hint_when_more_pages(db, jwt_manager, app_config, valid_token):
    # Post 5 items, read with page_size=2
    for i in range(5):
        await post_to_wall(
            token=valid_token,
            content=f"Signal {i}",
            db=db,
            jwt_manager=jwt_manager,
            config=app_config,
        )

    result = await read_wall(valid_token, db, jwt_manager, app_config, page=1, page_size=2)
    assert result.has_more is True
    # Hint is in _hint field (model dict)
    result_dict = result.model_dump()
    # hint should be present when suppress_hint=False
    result_no_hint = await read_wall(valid_token, db, jwt_manager, app_config, page=1, page_size=2, suppress_hint=True)
    assert result_no_hint.has_more is True


@pytest.mark.asyncio
async def test_post_with_disallowed_repo_key_silently_ignored(db, jwt_manager, app_config, valid_token):
    result = await post_to_wall(
        token=valid_token,
        content="Working on external repo",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
        project_key="https://github.com/external/repo",
    )
    assert result.project_key is None


@pytest.mark.asyncio
async def test_post_with_allowed_repo_key(db, jwt_manager, app_config, valid_token):
    result = await post_to_wall(
        token=valid_token,
        content="Working on company repo",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
        project_key="https://git.company.com/org/repo",
    )
    assert result.project_key == "https://git.company.com/org/repo"


# ── Registry round-trips ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_read_registry(db, jwt_manager, app_config, valid_token):
    result = await add_to_registry(
        token=valid_token,
        repo_url="https://git.company.com/org/myrepo",
        description="My awesome repo",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    assert result.created is True
    assert result.entry_id

    reg = await read_registry(valid_token, db, jwt_manager, app_config)
    assert reg.total_active == 1
    assert reg.entries[0].repo_url == "https://git.company.com/org/myrepo"


@pytest.mark.asyncio
async def test_add_registry_disallowed_url_raises(db, jwt_manager, app_config, valid_token):
    with pytest.raises(McpError):
        await add_to_registry(
            token=valid_token,
            repo_url="https://github.com/external/repo",
            description="Not allowed",
            db=db,
            jwt_manager=jwt_manager,
            config=app_config,
        )


@pytest.mark.asyncio
async def test_update_registry_entry(db, jwt_manager, app_config, valid_token):
    await add_to_registry(
        token=valid_token,
        repo_url="https://git.company.com/org/repo",
        description="Original description",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    result = await update_registry_entry(
        token=valid_token,
        repo_url="https://git.company.com/org/repo",
        description="Updated description",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    assert result.updated is True


@pytest.mark.asyncio
async def test_update_nonexistent_registry_entry_raises(db, jwt_manager, app_config, valid_token):
    with pytest.raises(McpError):
        await update_registry_entry(
            token=valid_token,
            repo_url="https://git.company.com/org/nonexistent",
            description="desc",
            db=db,
            jwt_manager=jwt_manager,
            config=app_config,
        )


@pytest.mark.asyncio
async def test_add_registry_idempotent(db, jwt_manager, app_config, valid_token):
    """Adding the same repo twice should return created=False on second call."""
    await add_to_registry(
        token=valid_token,
        repo_url="https://git.company.com/org/repo",
        description="desc",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    result2 = await add_to_registry(
        token=valid_token,
        repo_url="https://git.company.com/org/repo",
        description="desc v2",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
    )
    assert result2.created is False


@pytest.mark.asyncio
async def test_graduation_of_provisional_key(db, jwt_manager, app_config, valid_token):
    """Adding a repo with a provisional project_key should graduate the project."""
    from claude_halla.util.project_key import compute_provisional_key
    pkey = compute_provisional_key("testuser", "/home/testuser/myproject")

    # First post with provisional key
    await post_to_wall(
        token=valid_token,
        content="Starting project",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
        project_key=pkey,
    )

    result = await add_to_registry(
        token=valid_token,
        repo_url="https://git.company.com/org/myproject",
        description="My project",
        db=db,
        jwt_manager=jwt_manager,
        config=app_config,
        project_key=pkey,
    )
    assert result.graduated is True
