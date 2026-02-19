"""LDAP authentication client using ldap3 via asyncio.to_thread."""

from __future__ import annotations

import asyncio
import logging

import ldap3

logger = logging.getLogger(__name__)


class LDAPAuthError(Exception):
    """Raised when LDAP authentication fails."""


class LDAPClient:
    def __init__(
        self,
        url: str,
        base_dn: str,
        bind_dn: str,
        bind_password: str,
        user_dn_template: str,
    ) -> None:
        self._url = url
        self._base_dn = base_dn
        self._bind_dn = bind_dn
        self._bind_password = bind_password
        self._user_dn_template = user_dn_template

    def _sync_verify(self, username: str, password: str) -> None:
        """
        Synchronous LDAP bind verification (runs in thread pool).

        Raises LDAPAuthError if credentials are invalid.
        """
        user_dn = self._user_dn_template.format(
            username=username,
            base_dn=self._base_dn,
        )

        server = ldap3.Server(self._url, get_info=ldap3.NONE)
        try:
            conn = ldap3.Connection(
                server,
                user=user_dn,
                password=password,
                authentication=ldap3.SIMPLE,
                raise_exceptions=True,
            )
            conn.bind()
            if not conn.bound:
                raise LDAPAuthError("Invalid credentials.")
            conn.unbind()
        except ldap3.core.exceptions.LDAPBindError as e:
            raise LDAPAuthError(f"LDAP bind failed: {e}") from e
        except ldap3.core.exceptions.LDAPException as e:
            logger.error("LDAP error for user %s: %s", username, e)
            raise LDAPAuthError(f"LDAP error: {e}") from e

    async def verify_credentials(self, username: str, password: str) -> None:
        """
        Verify LDAP credentials asynchronously.

        Raises LDAPAuthError if authentication fails.
        """
        await asyncio.to_thread(self._sync_verify, username, password)
