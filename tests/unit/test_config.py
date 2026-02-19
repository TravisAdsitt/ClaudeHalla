"""Unit tests for config.py."""

import os
import tempfile

import pytest
import yaml

from claude_halla.config import load_config


def write_config(path: str, data: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f)


BASE_CONFIG = {
    "ldap": {
        "url": "ldap://localhost",
        "base_dn": "dc=test,dc=com",
        "bind_dn": "cn=admin,dc=test,dc=com",
        "bind_password": "${LDAP_BIND_PASSWORD}",
        "user_dn_template": "uid={username},ou=people,{base_dn}",
    },
    "database": {"path": "/data/test.db"},
    "session": {"token_ttl_hours": 8, "refresh_window_hours": 2},
    "wall": {"default_ttl_hours": 48, "max_page_size": 20},
    "registry": {
        "soft_archive_after_days": 180,
        "hard_delete_after_days": 365,
        "max_page_size": 20,
    },
    "archive": {
        "provisional_flag_after_days": 7,
        "provisional_soft_archive_after_days": 30,
        "provisional_hard_delete_after_days": 180,
    },
    "jobs": {"expiry_interval_minutes": 5, "cleanup_interval_hours": 24},
    "allowed_remote_patterns": ["https://git.company.com/*"],
}


def test_load_config_substitutes_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "secretpass")
    monkeypatch.setenv("CLAUDE_HALLA_JWT_SECRET", "a" * 32)
    config_file = tmp_path / "config.yaml"
    write_config(str(config_file), BASE_CONFIG)

    cfg = load_config(str(config_file))
    assert cfg.ldap.bind_password == "secretpass"


def test_load_config_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("LDAP_BIND_PASSWORD", raising=False)
    monkeypatch.setenv("CLAUDE_HALLA_JWT_SECRET", "a" * 32)
    config_file = tmp_path / "config.yaml"
    write_config(str(config_file), BASE_CONFIG)

    with pytest.raises(ValueError, match="LDAP_BIND_PASSWORD"):
        load_config(str(config_file))


def test_load_config_short_jwt_secret_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "pass")
    monkeypatch.setenv("CLAUDE_HALLA_JWT_SECRET", "tooshort")
    config_file = tmp_path / "config.yaml"
    write_config(str(config_file), BASE_CONFIG)

    with pytest.raises(ValueError, match="CLAUDE_HALLA_JWT_SECRET"):
        load_config(str(config_file))


def test_load_config_patterns_tuple(tmp_path, monkeypatch):
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "pass")
    monkeypatch.setenv("CLAUDE_HALLA_JWT_SECRET", "a" * 32)
    config_file = tmp_path / "config.yaml"
    write_config(str(config_file), BASE_CONFIG)

    cfg = load_config(str(config_file))
    assert isinstance(cfg.allowed_remote_patterns, tuple)
    assert "https://git.company.com/*" in cfg.allowed_remote_patterns
