"""
SessionPolicy: allowlist filter for actions. Port of src/loop/policy.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import urlparse

from agent_types import Action


@dataclass
class SessionPolicyResult:
    allowed: bool
    reason: Optional[str] = None


@dataclass
class SessionPolicyOptions:
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    allowed_actions: Optional[List[str]] = None


def _match_domain(hostname: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname == suffix or hostname.endswith(f".{suffix}")
    return hostname == pattern


def _opt(opts: Any, key: str, snake_key: str = None) -> Any:
    """Get option value, supporting both dataclass and dict (snake_case or camelCase)."""
    if opts is None:
        return None
    sk = snake_key or key
    ck = _camel(sk)
    if isinstance(opts, dict):
        if sk in opts:
            return opts[sk]
        if ck in opts:
            return opts[ck]
        return None
    if hasattr(opts, sk):
        return getattr(opts, sk)
    if hasattr(opts, ck):
        return getattr(opts, ck)
    return None


def _camel(s: str) -> str:
    """Convert snake_case to camelCase."""
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class SessionPolicy:
    """Allowlist filter checked before every model-emitted action."""

    def __init__(self, options: Any) -> None:
        self._options = options

    def check(self, action: Action) -> SessionPolicyResult:
        action_type = action.get("type", "")
        opts = self._options

        allowed_actions = _opt(opts, "allowed_actions")
        if allowed_actions and action_type not in allowed_actions:
            return SessionPolicyResult(
                allowed=False,
                reason=f'action type "{action_type}" is not permitted by session policy',
            )

        if action_type == "goto":
            url = action.get("url", "")
            result = self._check_domain(url)
            if not result.allowed:
                return result

        return SessionPolicyResult(allowed=True)

    def _check_domain(self, url: str) -> SessionPolicyResult:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("invalid URL")
            hostname = parsed.hostname
        except Exception:
            return SessionPolicyResult(allowed=False, reason=f"invalid URL: {url}")

        blocked_domains = _opt(self._options, "blocked_domains")
        if blocked_domains:
            for pattern in blocked_domains:
                if _match_domain(hostname, pattern):
                    return SessionPolicyResult(
                        allowed=False,
                        reason=f'navigation to "{hostname}" is blocked by session policy',
                    )

        allowed_domains = _opt(self._options, "allowed_domains")
        if allowed_domains:
            if not any(_match_domain(hostname, p) for p in allowed_domains):
                return SessionPolicyResult(
                    allowed=False,
                    reason=f'navigation to "{hostname}" is outside allowed domains — session policy only permits: {", ".join(allowed_domains)}',
                )

        return SessionPolicyResult(allowed=True)
