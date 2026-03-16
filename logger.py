"""
Granular debug logger. Port of src/logger.ts.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from agent_types import LogLine

LogLevel = str  # "debug" | "info" | "warn" | "error" | "silent"

LEVELS: Dict[str, int] = {
    "debug": 0,
    "info": 1,
    "warn": 2,
    "error": 3,
    "silent": 99,
}


def _resolve_min_level(verbose: int) -> str:
    """Resolve the minimum console log level.

    Environment variable takes priority over the verbose constructor argument,
    matching the TypeScript behavior.
    """
    env = os.environ.get("BROWSER_AGENT_LOG", "").lower()
    if env in LEVELS:
        return env
    if verbose == 0:
        return "silent"
    return "info"


class BrowserAgentLogger:
    """Granular debug logger threaded through all Browser Agent layers."""

    NOOP: "BrowserAgentLogger"

    def __init__(
        self,
        verbose: int,
        callback: Optional[Callable[[LogLine], None]] = None,
    ) -> None:
        level = _resolve_min_level(verbose)
        self._min = LEVELS[level]
        self._callback = callback

        is_debug = level == "debug"
        v2 = verbose >= 2

        self.cdp_enabled = is_debug or bool(os.environ.get("BROWSER_AGENT_LOG_CDP"))
        self.actions_enabled = is_debug or v2 or bool(os.environ.get("BROWSER_AGENT_LOG_ACTIONS"))
        self.browser_enabled = is_debug or v2 or bool(os.environ.get("BROWSER_AGENT_LOG_BROWSER"))
        self.history_enabled = is_debug or v2 or bool(os.environ.get("BROWSER_AGENT_LOG_HISTORY"))
        self.adapter_enabled = is_debug or v2 or bool(os.environ.get("BROWSER_AGENT_LOG_ADAPTER"))
        self.loop_enabled = is_debug or v2 or bool(os.environ.get("BROWSER_AGENT_LOG_LOOP"))

    def _emit(
        self,
        level: str,
        msg: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Callback always receives emitted lines.
        if self._callback is not None:
            self._callback(
                LogLine(
                    level=level,
                    message=msg,
                    data=data,
                    timestamp=time.time() * 1000,
                )
            )

        # Console output is gated by the resolved minimum level.
        if LEVELS[level] < self._min:
            return

        ts = datetime.now().strftime("%H:%M:%S.%f")[:12]  # HH:MM:SS.mmm
        prefix = f"[browser-agent {ts}]"

        parts = [prefix, msg]
        if data is not None:
            parts.append(repr(data))
        line = " ".join(parts)

        if level == "error":
            print(line, file=sys.stderr)
        elif level == "warn":
            print(line, file=sys.stderr)
        else:
            print(line)

    # ─── Surface-specific debug emitters ──────────────────────────────────

    def cdp(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.cdp_enabled:
            self._emit("debug", f"[cdp] {msg}", data)

    def action(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.actions_enabled:
            self._emit("debug", f"[action] {msg}", data)

    def browser(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.browser_enabled:
            self._emit("debug", f"[browser] {msg}", data)

    def history(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.history_enabled:
            self._emit("debug", f"[history] {msg}", data)

    def adapter(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.adapter_enabled:
            self._emit("debug", f"[adapter] {msg}", data)

    def loop(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self.loop_enabled:
            self._emit("debug", f"[loop] {msg}", data)

    # ─── Level-based emitters ─────────────────────────────────────────────

    def info(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._emit("info", msg, data)

    def warn(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._emit("warn", msg, data)

    def error(self, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._emit("error", msg, data)

    @classmethod
    def noop(cls) -> "BrowserAgentLogger":
        """Compatibility helper for existing Python call sites."""
        return cls.NOOP


BrowserAgentLogger.NOOP = BrowserAgentLogger(0)
NOOP = BrowserAgentLogger.NOOP
