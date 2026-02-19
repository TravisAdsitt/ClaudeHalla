"""authenticate tool: LDAP → JWT."""

from __future__ import annotations

import logging

import aiosqlite
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.auth.ldap_client import LDAPAuthError, LDAPClient
from claude_halla.models.schemas import AuthenticateOutput

logger = logging.getLogger(__name__)


async def authenticate(
    username: str,
    password: str,
    ldap_client: LDAPClient,
    jwt_manager: JWTManager,
) -> AuthenticateOutput:
    """Verify LDAP credentials and issue a JWT."""
    try:
        await ldap_client.verify_credentials(username, password)
    except LDAPAuthError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Authentication failed: invalid credentials."))
    except Exception:
        logger.exception("Unexpected LDAP error for user %s", username)
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Authentication service unavailable."))

    token, expires_at = jwt_manager.issue_token(username)
    return AuthenticateOutput(
        token=token,
        expires_at=expires_at.isoformat(),
        username=username,
    )
