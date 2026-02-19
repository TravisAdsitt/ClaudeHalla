"""Unit tests for auth/jwt_manager.py."""

from datetime import datetime, timedelta, timezone

import pytest

from claude_halla.auth.jwt_manager import JWTError, JWTManager


@pytest.fixture
def manager():
    return JWTManager(secret="a" * 32, token_ttl_hours=8, refresh_window_hours=2)


def test_issue_and_decode_token(manager):
    token, exp = manager.issue_token("alice")
    payload = manager.decode_token(token)
    assert payload["sub"] == "alice"
    assert "jti" in payload
    assert isinstance(exp, datetime)


def test_expired_token_raises(manager):
    import jwt as pyjwt
    from claude_halla.util.time import utcnow

    now = utcnow()
    past = now - timedelta(hours=1)
    payload = {
        "sub": "alice",
        "iat": past,
        "exp": past - timedelta(seconds=1),
        "jti": "test-jti",
    }
    token = pyjwt.encode(payload, "a" * 32, algorithm="HS256")
    with pytest.raises(JWTError, match="expired"):
        manager.decode_token(token)


def test_invalid_token_raises(manager):
    with pytest.raises(JWTError):
        manager.decode_token("totally.invalid.token")


def test_refresh_window_true_when_near_expiry(manager):
    import jwt as pyjwt
    from claude_halla.util.time import utcnow

    now = utcnow()
    # expires in 1 hour — within 2h window
    exp = now + timedelta(hours=1)
    payload = {
        "sub": "alice",
        "iat": now,
        "exp": exp,
        "jti": "test-jti",
    }
    token = pyjwt.encode(payload, "a" * 32, algorithm="HS256")
    decoded = manager.decode_token(token)
    assert manager.is_in_refresh_window(decoded) is True


def test_refresh_window_false_when_far_from_expiry(manager):
    token, _ = manager.issue_token("alice")
    payload = manager.decode_token(token)
    # fresh token with 8h TTL is NOT within 2h window
    assert manager.is_in_refresh_window(payload) is False
