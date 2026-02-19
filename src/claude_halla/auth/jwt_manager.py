"""JWT token issuance, decoding, and refresh-window logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from claude_halla.util.time import utcnow


class JWTError(Exception):
    """Raised when token validation fails."""


class JWTManager:
    ALGORITHM = "HS256"

    def __init__(self, secret: str, token_ttl_hours: int, refresh_window_hours: int) -> None:
        self._secret = secret
        self._ttl = timedelta(hours=token_ttl_hours)
        self._refresh_window = timedelta(hours=refresh_window_hours)

    def issue_token(self, username: str) -> tuple[str, datetime]:
        """
        Issue a signed JWT for the given username.

        Returns (token_str, expires_at_datetime).
        """
        now = utcnow()
        exp = now + self._ttl
        payload: dict[str, Any] = {
            "sub": username,
            "iat": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self.ALGORITHM)
        return token, exp

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and verify a JWT. Raises JWTError on failure.

        Returns the payload dict including 'sub', 'jti', 'exp', 'iat'.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self.ALGORITHM],
                options={"require": ["sub", "jti", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            raise JWTError("Token has expired.")
        except jwt.InvalidTokenError as e:
            raise JWTError(f"Invalid token: {e}")
        return payload

    def is_in_refresh_window(self, payload: dict[str, Any]) -> bool:
        """
        Return True if the token is within the refresh window.

        Refresh is allowed when: (exp - now) < refresh_window_hours.
        """
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = utcnow()
        return (exp - now) < self._refresh_window

    def token_exp_datetime(self, payload: dict[str, Any]) -> datetime:
        """Return the expiry datetime from a decoded payload."""
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
