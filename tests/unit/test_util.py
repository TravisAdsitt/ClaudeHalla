"""Unit tests for utility modules."""

import pytest

from claude_halla.util.project_key import classify_key, compute_provisional_key
from claude_halla.util.remote_allowlist import is_remote_allowed
from claude_halla.util.time import utcnow


def test_compute_provisional_key_is_64_hex():
    key = compute_provisional_key("alice", "/home/alice/myproject")
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_compute_provisional_key_deterministic():
    k1 = compute_provisional_key("alice", "/home/alice/myproject")
    k2 = compute_provisional_key("alice", "/home/alice/myproject")
    assert k1 == k2


def test_compute_provisional_key_differs_by_user():
    k1 = compute_provisional_key("alice", "/home/alice/myproject")
    k2 = compute_provisional_key("bob", "/home/alice/myproject")
    assert k1 != k2


def test_classify_key_provisional():
    key = compute_provisional_key("alice", "/home/alice/proj")
    assert classify_key(key) == "provisional"


def test_classify_key_repo():
    assert classify_key("https://git.company.com/org/repo") == "repo"


def test_is_remote_allowed_match():
    patterns = ("https://git.company.com/*",)
    assert is_remote_allowed("https://git.company.com/org/repo", patterns)


def test_is_remote_allowed_no_match():
    patterns = ("https://git.company.com/*",)
    assert not is_remote_allowed("https://github.com/org/repo", patterns)


def test_is_remote_allowed_empty_patterns():
    assert not is_remote_allowed("https://git.company.com/repo", ())


def test_utcnow_is_timezone_aware():
    from datetime import timezone
    now = utcnow()
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc
