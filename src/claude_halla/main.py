"""
Claude Halla MCP server entry point.

Wires together: FastMCP, Starlette, uvicorn, lifespan (DB + scheduler).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.auth.ldap_client import LDAPClient
from claude_halla.config import AppConfig, load_config
from claude_halla.db.connection import close_db, get_db, open_db
from claude_halla.jobs.scheduler import build_scheduler
from claude_halla.tools.authenticate import authenticate as _authenticate
from claude_halla.tools.refresh_token import refresh_token as _refresh_token
from claude_halla.tools.wall import (
    get_user_summary as _get_user_summary,
    post_to_wall as _post_to_wall,
    read_wall as _read_wall,
    retract_post as _retract_post,
)
from claude_halla.tools.registry import (
    add_to_registry as _add_to_registry,
    read_registry as _read_registry,
    update_registry_entry as _update_registry_entry,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load config at module level so it's available for tool registration ---
_config_path = os.environ.get("CLAUDE_HALLA_CONFIG", "config.yaml")
config: AppConfig = load_config(_config_path)

jwt_manager = JWTManager(
    secret=config.jwt_secret,
    token_ttl_hours=config.session.token_ttl_hours,
    refresh_window_hours=config.session.refresh_window_hours,
)

ldap_client = LDAPClient(
    url=config.ldap.url,
    base_dn=config.ldap.base_dn,
    bind_dn=config.ldap.bind_dn,
    bind_password=config.ldap.bind_password,
    user_dn_template=config.ldap.user_dn_template,
)

# --- FastMCP app ---
mcp = FastMCP(name="claude-halla")


# ── Health endpoint ──────────────────────────────────────────────────────────

async def healthz(request: Request) -> JSONResponse:
    """Return 200 if DB is reachable, 503 otherwise."""
    try:
        db = get_db()
        await db.execute("SELECT 1;")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


# ── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
async def authenticate(username: str, password: str) -> dict:
    """Authenticate with LDAP credentials and receive a JWT token."""
    result = await _authenticate(username, password, ldap_client, jwt_manager)
    return result.model_dump()


@mcp.tool()
async def refresh_token(token: str) -> dict:
    """Refresh a JWT token that is within its refresh window."""
    db = get_db()
    result = await _refresh_token(token, db, jwt_manager)
    return result.model_dump()


@mcp.tool()
async def post_to_wall(
    token: str,
    content: str,
    project_key: str | None = None,
    ttl_hours: int | None = None,
) -> dict:
    """Post a natural-language signal to the shared Wall."""
    db = get_db()
    result = await _post_to_wall(token, content, db, jwt_manager, config, project_key, ttl_hours)
    return result.model_dump()


@mcp.tool()
async def retract_post(token: str, post_id: str) -> dict:
    """Retract (remove) one of your active wall posts."""
    db = get_db()
    result = await _retract_post(token, post_id, db, jwt_manager)
    return result.model_dump()


@mcp.tool()
async def read_wall(
    token: str,
    page: int = 1,
    page_size: int = 20,
    suppress_hint: bool = False,
) -> dict:
    """Read active posts from the Wall. Returns paginated results."""
    db = get_db()
    result = await _read_wall(token, db, jwt_manager, config, page, page_size, suppress_hint)
    return result.model_dump()


@mcp.tool()
async def get_user_summary(token: str, target_username: str) -> dict:
    """Get a summary of a user's active posts, recent archived signals, and projects."""
    db = get_db()
    result = await _get_user_summary(token, target_username, db, jwt_manager)
    return result.model_dump()


@mcp.tool()
async def read_registry(
    token: str,
    page: int = 1,
    page_size: int = 20,
    suppress_hint: bool = False,
) -> dict:
    """Read the repository registry. Returns paginated results."""
    db = get_db()
    result = await _read_registry(token, db, jwt_manager, config, page, page_size, suppress_hint)
    return result.model_dump()


@mcp.tool()
async def add_to_registry(
    token: str,
    repo_url: str,
    description: str,
    project_key: str | None = None,
) -> dict:
    """Add a repository to the permanent registry (or graduate a provisional project)."""
    db = get_db()
    result = await _add_to_registry(token, repo_url, description, db, jwt_manager, config, project_key)
    return result.model_dump()


@mcp.tool()
async def update_registry_entry(
    token: str,
    repo_url: str,
    description: str,
) -> dict:
    """Update the description of an existing active registry entry."""
    db = get_db()
    result = await _update_registry_entry(token, repo_url, description, db, jwt_manager, config)
    return result.model_dump()


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    """Open DB, run migrations, start scheduler; clean up on shutdown."""
    db_path = config.database.path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    await open_db(db_path)
    logger.info("Database opened at %s", db_path)

    db = get_db()
    scheduler = build_scheduler(db, config)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        await close_db()
        logger.info("Database closed")


# ── Starlette app ─────────────────────────────────────────────────────────────

def build_app() -> Starlette:
    mcp_app = mcp.streamable_http_app()

    async def _healthz(request: Request) -> JSONResponse:
        return await healthz(request)

    starlette = Starlette(
        routes=[
            Route("/healthz", endpoint=_healthz),
        ],
        lifespan=lifespan,
    )

    # Mount the MCP app at /mcp
    from starlette.routing import Mount
    starlette.routes.append(Mount("/mcp", app=mcp_app))

    return starlette


def run() -> None:
    """Entry point for the claude-halla CLI script."""
    app = build_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )


if __name__ == "__main__":
    run()
