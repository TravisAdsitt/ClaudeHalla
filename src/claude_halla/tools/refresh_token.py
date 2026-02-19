"""refresh_token tool: issue new JWT within the refresh window."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiosqlite
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.db.queries.auth import revoke_token
from claude_halla.models.schemas import RefreshTokenOutput
from claude_halla.tools.guards import require_valid_token
from claude_halla.util.time import utcnow

logger = logging.getLogger(__name__)


async def refresh_token(
    token: str,
    db: aiosqlite.Connection,
    jwt_manager: JWTManager,
) -> RefreshTokenOutput:
    """
    Refresh a JWT that is within its refresh window.

    Revokes the old token and issues a new one.
    """
    username, payload = await require_valid_token(token, db, jwt_manager)

    if not jwt_manager.is_in_refresh_window(payload):
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message="Token is not yet within the refresh window. Refresh is only allowed when less than refresh_window_hours remain.",
            )
        )

    old_jti = payload["jti"]
    old_exp = jwt_manager.token_exp_datetime(payload)
    # Keep the revocation record until 1 day after old token expires
    revocation_expires = old_exp + timedelta(days=1)
    now_iso = utcnow().isoformat()

    await revoke_token(db, old_jti, now_iso, revocation_expires.isoformat())

    new_token, new_expires = jwt_manager.issue_token(username)
    return RefreshTokenOutput(
        token=new_token,
        expires_at=new_expires.isoformat(),
        username=username,
    )
