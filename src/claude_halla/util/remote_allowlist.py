"""Remote URL allowlist checking via fnmatch patterns."""

import fnmatch


def is_remote_allowed(url: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """
    Return True if the URL matches any of the allowed_remote_patterns.

    Uses fnmatch for glob-style matching (e.g. 'https://git.company.com/*').
    """
    return any(fnmatch.fnmatch(url, pattern) for pattern in patterns)
