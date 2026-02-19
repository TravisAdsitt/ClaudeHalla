"""Shared test fixtures: in-memory SQLite, mock LDAP, authed token."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import aiosqlite

from claude_halla.auth.jwt_manager import JWTManager
from claude_halla.auth.ldap_client import LDAPClient
from claude_halla.config import AppConfig, ArchiveConfig, DatabaseConfig, JobsConfig, LdapConfig, RegistryConfig, SessionConfig, WallConfig
from claude_halla.db.migrations import run_migrations


TEST_JWT_SECRET = "test-secret-that-is-at-least-32-chars-long!!"

_DEFAULT_CONFIG = AppConfig(
    ldap=LdapConfig(
        url="ldap://localhost",
        base_dn="dc=test,dc=com",
        bind_dn="cn=admin,dc=test,dc=com",
        bind_password="adminpass",
        user_dn_template="uid={username},ou=people,{base_dn}",
    ),
    database=DatabaseConfig(path=":memory:"),
    session=SessionConfig(token_ttl_hours=8, refresh_window_hours=2),
    wall=WallConfig(default_ttl_hours=48, max_page_size=20),
    registry=RegistryConfig(
        soft_archive_after_days=180,
        hard_delete_after_days=365,
        max_page_size=20,
    ),
    archive=ArchiveConfig(
        provisional_flag_after_days=7,
        provisional_soft_archive_after_days=30,
        provisional_hard_delete_after_days=180,
    ),
    jobs=JobsConfig(expiry_interval_minutes=5, cleanup_interval_hours=24),
    allowed_remote_patterns=("https://git.company.com/*",),
    jwt_secret=TEST_JWT_SECRET,
)


@pytest.fixture
def app_config() -> AppConfig:
    return _DEFAULT_CONFIG


@pytest_asyncio.fixture
async def db() -> aiosqlite.Connection:
    """In-memory SQLite with full schema applied."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
def jwt_manager(app_config: AppConfig) -> JWTManager:
    return JWTManager(
        secret=app_config.jwt_secret,
        token_ttl_hours=app_config.session.token_ttl_hours,
        refresh_window_hours=app_config.session.refresh_window_hours,
    )


@pytest.fixture
def valid_token(jwt_manager: JWTManager) -> str:
    """Return a valid JWT for 'testuser'."""
    token, _ = jwt_manager.issue_token("testuser")
    return token


@pytest.fixture
def mock_ldap_client() -> LDAPClient:
    """LDAP client that always succeeds."""
    client = MagicMock(spec=LDAPClient)
    client.verify_credentials = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_ldap_client_fail() -> LDAPClient:
    """LDAP client that always raises LDAPAuthError."""
    from claude_halla.auth.ldap_client import LDAPAuthError
    client = MagicMock(spec=LDAPClient)
    client.verify_credentials = AsyncMock(side_effect=LDAPAuthError("Invalid credentials."))
    return client
