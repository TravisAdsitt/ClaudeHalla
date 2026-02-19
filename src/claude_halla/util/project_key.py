"""Provisional project key computation."""

import hashlib


def compute_provisional_key(username: str, abs_directory_path: str) -> str:
    """
    Compute a provisional project key from username and absolute directory path.

    Returns a 64-char lowercase hex string (SHA-256).
    Claude Code computes this client-side and passes it in tool calls.
    """
    payload = f"{username}:{abs_directory_path}"
    return hashlib.sha256(payload.encode()).hexdigest()


def classify_key(key: str) -> str:
    """
    Classify a project key as 'provisional' or 'repo'.

    A 64-char lowercase hex string is provisional; anything else (URL) is a repo key.
    """
    if len(key) == 64 and all(c in "0123456789abcdef" for c in key):
        return "provisional"
    return "repo"
