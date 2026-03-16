"""
StateStore: last-write-wins agent memory. Port of src/loop/state.ts.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class StateStore:
    """Last-write-wins agent memory. Written by the model via writeState."""

    def __init__(self) -> None:
        self._data: Optional[Dict[str, Any]] = None

    def current(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data else None

    def write(self, data: Dict[str, Any]) -> None:
        self._data = dict(data)

    def load(self, data: Optional[Dict[str, Any]]) -> None:
        self._data = dict(data) if data else None
