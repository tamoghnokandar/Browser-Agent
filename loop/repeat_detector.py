"""
RepeatDetector: detects stuck/repeating actions. Port of src/loop/repeat-detector.ts.
"""
from __future__ import annotations

import hashlib
import math
from typing import Optional
from urllib.parse import urlparse

from agent_types import Action


def _get_action_attr(action: Action, key: str, default: object = None) -> object:
    """Get attribute from action."""
    return action.get(key, default)


class RepeatDetector:
    """Detects when the agent is stuck repeating actions or stalling on one page."""

    def __init__(self, url_stall_threshold: int = 10) -> None:
        self._window: list[str] = []
        self._category_window: list[str] = []
        self._window_size = 20
        self._thresholds = (5, 8, 12)

        self._current_url = ""
        self._steps_on_url = 0
        self._url_stall_threshold = url_stall_threshold

    def record(self, action: Action) -> Optional[int]:
        norm = self._normalize(action)
        h = hashlib.sha256(norm.encode()).hexdigest()
        category = self._categorize(action)

        self._window.append(h)
        if len(self._window) > self._window_size:
            self._window.pop(0)

        self._category_window.append(category)
        if len(self._category_window) > self._window_size:
            self._category_window.pop(0)

        # Layer 1: Exact action repeat
        repeats = sum(1 for x in self._window if x == h)
        for t in self._thresholds:
            if repeats == t:
                return t

        # Layer 2: Category dominance
        category_count = sum(1 for c in self._category_window if c == category)
        for t in self._thresholds:
            if category_count == t and category != "productive":
                return t

        return None

    def record_url(self, url: str) -> Optional[int]:
        normalized = self._normalize_url(url)
        if normalized != self._current_url:
            self._current_url = normalized
            self._steps_on_url = 0
            return None

        self._steps_on_url += 1

        # Match TS Math.round(urlStallThreshold * 1.5)
        mid_threshold = math.floor(self._url_stall_threshold * 1.5 + 0.5)

        if self._steps_on_url == self._url_stall_threshold:
            return 5
        if self._steps_on_url == mid_threshold:
            return 8
        if self._steps_on_url == self._url_stall_threshold * 2:
            return 12

        return None

    def reset(self) -> None:
        self._window.clear()
        self._category_window.clear()
        self._steps_on_url = 0
        self._current_url = ""

    def _categorize(self, action: Action) -> str:
        t = _get_action_attr(action, "type", "")

        if t in ("scroll", "wait", "hover"):
            return "passive"
        if t == "screenshot":
            return "noop"
        if t in (
            "click",
            "doubleClick",
            "type",
            "keyPress",
            "goto",
            "writeState",
            "terminate",
            "delegate",
            "drag",
        ):
            return "productive"

        return "passive"

    def _normalize_url(self, url: str) -> str:
        try:
            u = urlparse(url)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}{u.path}"
            return url
        except Exception:
            return url

    def _normalize(self, action: Action) -> str:
        # Bucket size: 64px ≈ 5% of a 1280px viewport
        bucket = 64
        t = _get_action_attr(action, "type", "")

        if t in ("click", "doubleClick", "hover"):
            x = _get_action_attr(action, "x", 0)
            y = _get_action_attr(action, "y", 0)
            bx = math.floor(x / bucket + 0.5) * bucket
            by = math.floor(y / bucket + 0.5) * bucket
            return f"{t}:{bx},{by}"

        if t == "type":
            return f"type:{_get_action_attr(action, 'text', '')}"

        if t == "goto":
            return f"goto:{_get_action_attr(action, 'url', '')}"

        if t == "keyPress":
            keys = _get_action_attr(action, "keys", []) or []
            return f"keyPress:{'+'.join(keys)}"

        if t == "scroll":
            x = _get_action_attr(action, "x", 0)
            y = _get_action_attr(action, "y", 0)
            direction = _get_action_attr(action, "direction", "")
            bx = math.floor(x / bucket + 0.5) * bucket
            by = math.floor(y / bucket + 0.5) * bucket
            return f"scroll:{bx},{by},{direction}"

        return t


def nudge_message(level: int, context: Optional[str] = None) -> str:
    if context == "url":
        if level >= 12:
            return (
                "CRITICAL STRATEGY RESET: You have spent far too many steps on this page. "
                "You MUST: 1) Save everything you've found with update_state RIGHT NOW. "
                "2) Then either navigate to a different page, try a completely different approach, "
                "or call task_complete with your best answer based on what you have. "
                "Do NOT continue with the same approach — it is not working."
            )
        if level >= 8:
            return (
                "WARNING: You have been on this same page for many steps without saving progress. "
                "Use update_state to save what you've done so far before continuing. "
                "If you're stuck on an interaction, try a completely different approach — "
                "click elsewhere, or skip this step and move on."
            )
        return (
            "You have been on this page for a while. "
            "Consider using update_state to checkpoint your progress before continuing."
        )

    if level >= 12:
        return (
            "STRATEGY RESET: You have repeated the same action many times and the page has not changed. "
            "Stop completely and try a DIFFERENT approach: "
            "1) Save everything you've found so far with update_state. "
            "2) If clicking isn't working, try keyboard navigation (Tab, Enter, Page_Down). "
            "3) If a form is stuck, try navigating directly to a URL with parameters instead. "
            "4) If you have enough information to answer, call task_complete NOW with your best answer."
        )

    if level >= 8:
        return (
            "You are repeating the same action. The page does not appear to be changing. "
            "Try a different approach — click a different element, navigate to a different page, "
            "or save your progress and move on."
        )

    return "You seem to be repeating an action. If the page is not responding, try something different."