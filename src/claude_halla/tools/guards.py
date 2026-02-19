"""Authentication guard used by every authenticated tool."""

from __future__ import annotations

import aiosqlite
from mcp.server.fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from claude_halla.auth.jwt_manager import JWTError, JWTManager
from claude_halla.config import AppConfig
from claude_halla.db.queries.auth import is_token_revoked


async def require_valid_token(
    token: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
) -> tuple[str, dict]:
    """
    Validate the provided JWT token.

    Returns (username, payload) on success.
    Raises McpError (ToolError equivalent) on failure.
    """
    try:
        payload = jwt_manager.decode_token(token)
    except JWTError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))

    jti = payload.get("jti", "")
    if await is_token_revoked(db, jti):
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Token has been revoked."))

    username: str = payload["sub"]
    return username, payload
