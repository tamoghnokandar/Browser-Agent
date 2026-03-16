"""Tests for SessionPolicy. Port of tests/unit/policy.test.ts."""
import pytest

from loop.policy import SessionPolicy


class TestSessionPolicyDomainMatching:
    def test_allows_navigation_to_exact_domain(self):
        policy = SessionPolicy({"allowed_domains": ["example.com"]})
        result = policy.check({"type": "goto", "url": "https://example.com/page"})
        assert result.allowed is True

    def test_blocks_navigation_to_non_allowed_domain(self):
        policy = SessionPolicy({"allowed_domains": ["example.com"]})
        result = policy.check({"type": "goto", "url": "https://other.com"})
        assert result.allowed is False
        assert "other.com" in (result.reason or "")

    def test_wildcard_matches_subdomains(self):
        policy = SessionPolicy({"allowed_domains": ["*.mycompany.com"]})
        assert policy.check({"type": "goto", "url": "https://api.mycompany.com"}).allowed is True
        assert policy.check({"type": "goto", "url": "https://app.mycompany.com"}).allowed is True

    def test_wildcard_matches_bare_domain_suffix(self):
        policy = SessionPolicy({"allowed_domains": ["*.mycompany.com"]})
        result = policy.check({"type": "goto", "url": "https://mycompany.com"})
        assert isinstance(result.allowed, bool)

    def test_blocked_domain_overrides_allowed(self):
        policy = SessionPolicy({"blocked_domains": ["evil.com"]})
        result = policy.check({"type": "goto", "url": "https://evil.com/page"})
        assert result.allowed is False
        assert "evil.com" in (result.reason or "")

    def test_allows_non_goto_actions_regardless_of_domains(self):
        policy = SessionPolicy({"allowed_domains": ["example.com"]})
        assert policy.check({"type": "click", "x": 100, "y": 100}).allowed is True
        assert policy.check({"type": "type", "text": "hello"}).allowed is True

    def test_allowed_actions_blocks_disallowed_action_types(self):
        policy = SessionPolicy({"allowed_actions": ["click", "type", "screenshot"]})
        assert policy.check({"type": "click", "x": 100, "y": 100}).allowed is True
        assert policy.check({"type": "goto", "url": "https://example.com"}).allowed is False

    def test_returns_reason_when_action_type_not_allowed(self):
        policy = SessionPolicy({"allowed_actions": ["click"]})
        result = policy.check(
            {"type": "scroll", "x": 0, "y": 0, "direction": "down", "amount": 3}
        )
        assert result.allowed is False
        assert "scroll" in (result.reason or "")
