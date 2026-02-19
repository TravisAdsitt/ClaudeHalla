"""Integration tests: LDAP → JWT → refresh → revocation cycle."""

from __future__ import annotations

import pytest
from mcp.shared.exceptions import McpError

from claude_halla.tools.authenticate import authenticate
from claude_halla.tools.refresh_token import refresh_token
from claude_halla.tools.guards import require_valid_token


@pytest.mark.asyncio
async def test_authenticate_success(mock_ldap_client, jwt_manager):
    result = await authenticate("alice", "password", mock_ldap_client, jwt_manager)
    assert result.token
    assert result.username == "alice"
    assert result.expires_at


@pytest.mark.asyncio
async def test_authenticate_failure(mock_ldap_client_fail, jwt_manager):
    with pytest.raises(McpError):
        await authenticate("alice", "wrongpass", mock_ldap_client_fail, jwt_manager)


@pytest.mark.asyncio
async def test_require_valid_token(db, jwt_manager):
    token, _ = jwt_manager.issue_token("alice")
    username, payload = await require_valid_token(token, db, jwt_manager)
    assert username == "alice"
    assert payload["sub"] == "alice"


@pytest.mark.asyncio
async def test_require_valid_token_invalid(db, jwt_manager):
    with pytest.raises(McpError):
        await require_valid_token("bad.token.here", db, jwt_manager)


@pytest.mark.asyncio
async def test_refresh_token_outside_window_raises(db, jwt_manager):
    """Fresh token (8h TTL, 2h window) should not be refreshable."""
    token, _ = jwt_manager.issue_token("alice")
    with pytest.raises(McpError, match="not yet within"):
        await refresh_token(token, db, jwt_manager)


@pytest.mark.asyncio
async def test_refresh_token_in_window(db):
    """Token with 1h remaining should be refreshable."""
    import jwt as pyjwt
    from datetime import timedelta
    from claude_halla.util.time import utcnow

    manager = __import__("claude_halla.auth.jwt_manager", fromlist=["JWTManager"]).JWTManager(
        secret="a" * 32,
        token_ttl_hours=1,
        refresh_window_hours=2,
    )

    now = utcnow()
    exp = now + timedelta(hours=1)
    import uuid
    payload = {"sub": "alice", "iat": now, "exp": exp, "jti": str(uuid.uuid4())}
    token = pyjwt.encode(payload, "a" * 32, algorithm="HS256")

    result = await refresh_token(token, db, manager)
    assert result.token != token
    assert result.username == "alice"


@pytest.mark.asyncio
async def test_revoked_token_rejected(db, jwt_manager):
    """After refresh, old token should be rejected."""
    import jwt as pyjwt
    from datetime import timedelta
    from claude_halla.util.time import utcnow
    import uuid

    now = utcnow()
    exp = now + timedelta(hours=1)
    payload = {"sub": "alice", "iat": now, "exp": exp, "jti": str(uuid.uuid4())}
    old_token = pyjwt.encode(payload, "a" * 32, algorithm="HS256")

    manager = __import__("claude_halla.auth.jwt_manager", fromlist=["JWTManager"]).JWTManager(
        secret="a" * 32,
        token_ttl_hours=1,
        refresh_window_hours=2,
    )

    await refresh_token(old_token, db, manager)

    with pytest.raises(McpError, match="revoked"):
        await require_valid_token(old_token, db, manager)
