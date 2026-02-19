"""Configuration loading: YAML + ${ENV_VAR} substitution → frozen dataclass."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute_env(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""
    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        val = os.environ.get(var_name)
        if val is None:
            raise ValueError(
                f"Required environment variable '{var_name}' is not set"
            )
        return val

    return _ENV_VAR_RE.sub(replace, value)


def _walk_and_substitute(obj: Any) -> Any:
    """Recursively substitute env vars in all string values."""
    if isinstance(obj, str):
        return _substitute_env(obj)
    if isinstance(obj, dict):
        return {k: _walk_and_substitute(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_substitute(item) for item in obj]
    return obj


@dataclass(frozen=True)
class LdapConfig:
    url: str
    base_dn: str
    bind_dn: str
    bind_password: str
    user_dn_template: str


@dataclass(frozen=True)
class DatabaseConfig:
    path: str


@dataclass(frozen=True)
class SessionConfig:
    token_ttl_hours: int
    refresh_window_hours: int


@dataclass(frozen=True)
class WallConfig:
    default_ttl_hours: int
    max_page_size: int


@dataclass(frozen=True)
class RegistryConfig:
    soft_archive_after_days: int
    hard_delete_after_days: int
    max_page_size: int


@dataclass(frozen=True)
class ArchiveConfig:
    provisional_flag_after_days: int
    provisional_soft_archive_after_days: int
    provisional_hard_delete_after_days: int


@dataclass(frozen=True)
class JobsConfig:
    expiry_interval_minutes: int
    cleanup_interval_hours: int


@dataclass(frozen=True)
class AppConfig:
    ldap: LdapConfig
    database: DatabaseConfig
    session: SessionConfig
    wall: WallConfig
    registry: RegistryConfig
    archive: ArchiveConfig
    jobs: JobsConfig
    allowed_remote_patterns: tuple[str, ...]
    jwt_secret: str  # From CLAUDE_HALLA_JWT_SECRET env var


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate configuration from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    raw = _walk_and_substitute(raw)

    jwt_secret = os.environ.get("CLAUDE_HALLA_JWT_SECRET", "")
    if len(jwt_secret) < 32:
        raise ValueError(
            "CLAUDE_HALLA_JWT_SECRET must be set and at least 32 bytes long"
        )

    ldap_raw = raw["ldap"]
    ldap = LdapConfig(
        url=ldap_raw["url"],
        base_dn=ldap_raw["base_dn"],
        bind_dn=ldap_raw["bind_dn"],
        bind_password=ldap_raw["bind_password"],
        user_dn_template=ldap_raw["user_dn_template"],
    )

    db_raw = raw["database"]
    database = DatabaseConfig(path=db_raw["path"])

    sess_raw = raw["session"]
    session = SessionConfig(
        token_ttl_hours=int(sess_raw["token_ttl_hours"]),
        refresh_window_hours=int(sess_raw["refresh_window_hours"]),
    )

    wall_raw = raw["wall"]
    wall = WallConfig(
        default_ttl_hours=int(wall_raw["default_ttl_hours"]),
        max_page_size=int(wall_raw["max_page_size"]),
    )

    reg_raw = raw["registry"]
    registry = RegistryConfig(
        soft_archive_after_days=int(reg_raw["soft_archive_after_days"]),
        hard_delete_after_days=int(reg_raw["hard_delete_after_days"]),
        max_page_size=int(reg_raw["max_page_size"]),
    )

    arch_raw = raw["archive"]
    archive = ArchiveConfig(
        provisional_flag_after_days=int(arch_raw["provisional_flag_after_days"]),
        provisional_soft_archive_after_days=int(arch_raw["provisional_soft_archive_after_days"]),
        provisional_hard_delete_after_days=int(arch_raw["provisional_hard_delete_after_days"]),
    )

    jobs_raw = raw["jobs"]
    jobs = JobsConfig(
        expiry_interval_minutes=int(jobs_raw["expiry_interval_minutes"]),
        cleanup_interval_hours=int(jobs_raw["cleanup_interval_hours"]),
    )

    patterns = tuple(raw.get("allowed_remote_patterns", []))

    return AppConfig(
        ldap=ldap,
        database=database,
        session=session,
        wall=wall,
        registry=registry,
        archive=archive,
        jobs=jobs,
        allowed_remote_patterns=patterns,
        jwt_secret=jwt_secret,
    )
