"""
ViewportManager: aligns viewport to model patch size. Port of src/browser/viewport.ts.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from .tab import BrowserTab
from .types import ViewportSize


def _round_up(n: float, step: int) -> int:
    return math.ceil(n / step) * step


def _vp_to_dict(vp: Any) -> Dict[str, int]:
    """Convert ViewportSize (dataclass) or dict to {width, height}."""
    if hasattr(vp, "width") and hasattr(vp, "height"):
        return {"width": vp.width, "height": vp.height}
    return {"width": vp.get("width", 1280), "height": vp.get("height", 720)}


class ViewportManager:
    def __init__(self, tab: BrowserTab) -> None:
        self._tab = tab
        vp = tab.viewport()
        self._current = _vp_to_dict(vp)
        self._original = dict(self._current)

    async def align_to_model(self, patch_size: int = 28, max_dim: int = 1344) -> Dict[str, int]:
        vp = self._tab.viewport()
        vp_dict = _vp_to_dict(vp)
        width = _round_up(vp_dict.get("width", 1280), patch_size)
        height = _round_up(vp_dict.get("height", 720), patch_size)
        width = min(width, max_dim)
        height = min(height, max_dim)
        aligned = {"width": width, "height": height}
        await self._tab.set_viewport(ViewportSize(width=width, height=height))
        self._current = dict(aligned)
        return aligned

    async def restore_original(self) -> None:
        await self._tab.set_viewport(ViewportSize(**self._original))
        self._current = dict(self._original)

    def current(self) -> Dict[str, int]:
        return dict(self._current)
