"""Wall tools: post_to_wall, retract_post, read_wall, get_user_summary."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import aiosqlite
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from claude_halla.config import AppConfig
from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.db.queries.archive import (
    get_projects_for_user,
    get_recent_archived_signals_for_user,
    insert_archived_signal,
    upsert_project,
)
from claude_halla.db.queries.registry import touch_registry_entry
from claude_halla.db.queries.wall import (
    get_active_wall_posts,
    get_wall_posts_for_user,
    insert_wall_post,
    retract_wall_post,
)
from claude_halla.models.schemas import (
    GetUserSummaryOutput,
    PostToWallOutput,
    ReadWallOutput,
    RetractPostOutput,
    WallPostItem,
)
from claude_halla.tools.guards import require_valid_token
from claude_halla.util.project_key import classify_key
from claude_halla.util.remote_allowlist import is_remote_allowed
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def post_to_wall(
    token: str,
    content: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
    config: AppConfig,
    project_key: str | None = None,
    ttl_hours: int | None = None,
) -> PostToWallOutput:
    username, _ = await require_valid_token(token, db, jwt_manager)

    if len(content) > 2000:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Content must be 2000 characters or fewer."))

    # Validate project_key if provided
    resolved_key: str | None = None
    if project_key:
        key_type = classify_key(project_key)
        if key_type == "repo":
            if not is_remote_allowed(project_key, config.allowed_remote_patterns):
                # Silently ignore non-allowed remotes
                resolved_key = None
            else:
                resolved_key = project_key
        else:
            resolved_key = project_key

    now = utcnow()
    effective_ttl = ttl_hours if ttl_hours is not None else config.wall.default_ttl_hours
    expires_at = now + timedelta(hours=effective_ttl)

    post_id = str(uuid.uuid4())
    now_iso = now.isoformat()
    expires_iso = expires_at.isoformat()

    await insert_wall_post(
        db,
        post_id=post_id,
        username=username,
        content=content,
        posted_at=now_iso,
        expires_at=expires_iso,
        project_key=resolved_key,
    )

    # Upsert project record and touch registry if applicable
    if resolved_key:
        key_type = classify_key(resolved_key)
        await upsert_project(db, resolved_key, key_type, username, now_iso)
        if key_type == "repo":
            await touch_registry_entry(db, resolved_key, now_iso)

    return PostToWallOutput(
        post_id=post_id,
        expires_at=expires_iso,
        project_key=resolved_key,
    )


async def retract_post(
    token: str,
    post_id: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
) -> RetractPostOutput:
    username, _ = await require_valid_token(token, db, jwt_manager)

    post = await retract_wall_post(db, post_id, username)
    if post is None:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message="Post not found, already retracted, or you do not own it.",
            )
        )

    # Archive the retracted post
    now_iso = utcnow().isoformat()
    project_key = post.get("project_key") or "unknown"
    await insert_archived_signal(
        db,
        signal_id=post_id,
        project_key=project_key,
        username=username,
        content=post["content"],
        posted_at=post["posted_at"],
        expired_at=now_iso,
        archive_reason="retracted",
    )

    return RetractPostOutput(retracted=True, post_id=post_id)


async def read_wall(
    token: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
    config: AppConfig,
    page: int = 1,
    page_size: int = 20,
    suppress_hint: bool = False,
) -> ReadWallOutput:
    await require_valid_token(token, db, jwt_manager)

    effective_page_size = min(page_size, config.wall.max_page_size)
    posts, total = await get_active_wall_posts(db, page, effective_page_size)

    has_more = (page * effective_page_size) < total
    post_items = [WallPostItem(**p) for p in posts]

    hint: str | None = None
    if has_more and not suppress_hint:
        hint = (
            "More posts are available. To retrieve additional pages, delegate "
            "pagination to a subagent using read_wall with suppress_hint=True "
            "and incrementing page numbers."
        )

    result = ReadWallOutput(
        posts=post_items,
        total_active=total,
        has_more=has_more,
    )
    # Attach hint via model_fields_set workaround (private field pattern)
    result_dict = result.model_dump()
    result_dict["_hint"] = hint
    return ReadWallOutput.model_validate(result_dict)


async def get_user_summary(
    token: str,
    target_username: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
) -> GetUserSummaryOutput:
    await require_valid_token(token, db, jwt_manager)

    active_posts = await get_wall_posts_for_user(db, target_username)
    recent_archived = await get_recent_archived_signals_for_user(db, target_username)
    projects = await get_projects_for_user(db, target_username)

    active_items = [WallPostItem(**p) for p in active_posts]

    return GetUserSummaryOutput(
        active_posts=active_items,
        recent_archived=recent_archived,
        projects=projects,
    )
