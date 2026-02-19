"""Registry tools: read_registry, add_to_registry, update_registry_entry."""

from __future__ import annotations

import logging
import uuid

import aiosqlite
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.config import AppConfig
from claude_halla.db.queries.archive import upsert_project
from claude_halla.db.queries.registry import (
    get_active_registry_entries,
    get_registry_entry_by_url,
    insert_registry_entry,
    update_registry_entry as db_update_registry_entry,
)
from claude_halla.models.schemas import (
    AddToRegistryOutput,
    ReadRegistryOutput,
    RegistryEntryItem,
    UpdateRegistryEntryOutput,
)
from claude_halla.tools.guards import require_valid_token
from claude_halla.util.project_key import classify_key
from claude_halla.util.remote_allowlist import is_remote_allowed
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def read_registry(
    token: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
    config: AppConfig,
    page: int = 1,
    page_size: int = 20,
    suppress_hint: bool = False,
) -> ReadRegistryOutput:
    await require_valid_token(token, db, jwt_manager)

    effective_page_size = min(page_size, config.registry.max_page_size)
    entries, total = await get_active_registry_entries(db, page, effective_page_size)

    has_more = (page * effective_page_size) < total
    entry_items = [RegistryEntryItem(**e) for e in entries]

    hint: str | None = None
    if has_more and not suppress_hint:
        hint = (
            "More registry entries are available. Delegate further pagination "
            "to a subagent using read_registry with suppress_hint=True and "
            "incrementing page numbers."
        )

    result = ReadRegistryOutput(
        entries=entry_items,
        total_active=total,
        has_more=has_more,
    )
    result_dict = result.model_dump()
    result_dict["_hint"] = hint
    return ReadRegistryOutput.model_validate(result_dict)


async def add_to_registry(
    token: str,
    repo_url: str,
    description: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
    config: AppConfig,
    project_key: str | None = None,
) -> AddToRegistryOutput:
    username, _ = await require_valid_token(token, db, jwt_manager)

    if len(description) > 1000:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Description must be 1000 characters or fewer."))

    if not is_remote_allowed(repo_url, config.allowed_remote_patterns):
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"Repository URL '{repo_url}' does not match any allowed remote patterns.",
            )
        )

    now_iso = utcnow().isoformat()
    graduated = False

    # Check if entry already exists
    existing = await get_registry_entry_by_url(db, repo_url)
    if existing:
        entry_id = existing["id"]
        created = False
    else:
        entry_id = str(uuid.uuid4())
        await insert_registry_entry(db, entry_id, repo_url, description, now_iso)
        created = True

    # If a provisional project_key was provided, graduate it to the repo key
    if project_key:
        key_type = classify_key(project_key)
        if key_type == "provisional":
            # Update the project row to point to the real repo URL
            await db.execute(
                """
                UPDATE projects
                SET key_type = 'repo', graduated_to_repo_key = ?
                WHERE key = ?;
                """,
                (repo_url, project_key),
            )
            await db.commit()
            graduated = True

        # Upsert the repo project
        await upsert_project(db, repo_url, "repo", username, now_iso)

    return AddToRegistryOutput(
        entry_id=entry_id,
        created=created,
        graduated=graduated,
    )


async def update_registry_entry(
    token: str,
    repo_url: str,
    description: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
    config: AppConfig,
) -> UpdateRegistryEntryOutput:
    await require_valid_token(token, db, jwt_manager)

    if len(description) > 1000:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Description must be 1000 characters or fewer."))

    updated_row = await db_update_registry_entry(db, repo_url, description)
    if updated_row is None:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"Active registry entry for '{repo_url}' not found.",
            )
        )

    return UpdateRegistryEntryOutput(
        entry_id=updated_row["id"],
        updated=True,
    )
