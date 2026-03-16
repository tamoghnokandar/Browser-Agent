"""
SiteKB: site-specific knowledge base. Port of src/memory/site-kb.ts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, TypedDict
from urllib.parse import urlparse


class SiteRule(TypedDict):
    """A site rule: domain pattern and list of rule strings."""
    domain: str
    rules: List[str]


def _domain_matches(pattern: str, hostname: str, pathname: str) -> bool:
    full_path = hostname + pathname
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith(suffix) or suffix in full_path
    return pattern in full_path


class SiteKB:
    def __init__(self, rules: Optional[List[SiteRule]] = None) -> None:
        self._rules: List[SiteRule] = rules or []

    def to_json(self) -> List[SiteRule]:
        """Return the rules as a list of site rules."""
        return self._rules

    def save(self, path: str) -> None:
        """Save the rules to a JSON file."""
        Path(path).write_text(json.dumps(self._rules, indent=2), encoding="utf-8")

    @classmethod
    def from_file(cls, path: str) -> "SiteKB":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(data)
        except Exception:
            return cls()

    def match(self, url: str) -> List[str]:
        try:
            u = urlparse(url)
            hostname = u.hostname or ""
            pathname = u.path or ""
        except Exception:
            return []

        matched: List[str] = []
        for rule in self._rules:
            if _domain_matches(rule["domain"], hostname, pathname):
                matched.extend(rule["rules"])
        return matched

    def add_rule(self, domain: str, rule: str) -> None:
        existing = next((r for r in self._rules if r["domain"] == domain), None)
        if existing:
            if rule not in existing["rules"]:
                existing["rules"].append(rule)
        else:
            self._rules.append({"domain": domain, "rules": [rule]})

    def format_for_prompt(self, url: str) -> str | None:
        rules = self.match(url)
        if not rules:
            return None
        return "SITE-SPECIFIC TIPS:\n" + "\n".join(f"- {r}" for r in rules)
