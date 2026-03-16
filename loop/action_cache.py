"""
ActionCache: on-disk action replay. Port of src/loop/action-cache.ts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from agent_types import Action


def _action_to_args(action: Action) -> Dict[str, Any]:
    """Convert action to dict for storage."""
    return dict(action)

COORD_ACTIONS = {"click", "doubleClick", "hover", "scroll", "drag"}
SIMILARITY_THRESHOLD = 0.92


def viewport_mismatch(cached: Dict[str, Any], current: Dict[str, int]) -> bool:
    vp = cached.get("viewport")
    if not vp:
        return False
    return vp.get("width") != current.get("width") or vp.get("height") != current.get("height")


def _similarity(a: str, b: str) -> float:
    return 1.0 if a == b else 0.0


def screenshot_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ActionCache:
    def __init__(self, cache_dir: str = ".browser-agent-cache") -> None:
        self._dir = cache_dir

    def cache_key(self, action_type: str, url: str, instruction_hash: str) -> str:
        sig = f"{action_type}:{url}:{instruction_hash}"
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    def step_key(self, url: str, instruction_hash: str) -> str:
        sig = f"{url}:{instruction_hash}"
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    async def get(self, key: str, current_screenshot_hash: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            path = Path(self._dir) / f"{key}.json"
            raw = path.read_text(encoding="utf-8")
            entry = json.loads(raw)
            if entry.get("version") != 1:
                return None
            if entry.get("screenshotHash") and current_screenshot_hash:
                if _similarity(entry["screenshotHash"], current_screenshot_hash) < SIMILARITY_THRESHOLD:
                    return None
            return entry
        except Exception:
            return None

    async def set(
        self,
        key: str,
        action: Action,
        url: str,
        instruction_hash: str,
        current_screenshot_hash: Optional[str] = None,
        viewport: Optional[Dict[str, int]] = None,
    ) -> None:
        os.makedirs(self._dir, exist_ok=True)
        action_type = action.get("type", "?")
        args = _action_to_args(action)
        entry = {
            "version": 1,
            "type": action_type,
            "url": url,
            "instructionHash": instruction_hash,
            "screenshotHash": current_screenshot_hash if action_type in COORD_ACTIONS else None,
            "viewport": viewport,
            "args": args,
        }
        path = Path(self._dir) / f"{key}.json"
        path.write_text(json.dumps(entry, default=str), encoding="utf-8")
