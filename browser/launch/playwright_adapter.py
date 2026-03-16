"""
Adapter that wraps Playwright's CDPSession to match the CDPSessionLike protocol
expected by CDPTab (send, on, off).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class PlaywrightSessionAdapter:
    """
    Wraps Playwright's CDPSession so it can be used with CDPTab.
    Playwright uses send(method, **kwargs) and remove_listener; we expose
    send(method, params) and off(event, handler).
    """

    def __init__(self, cdp_session: Any) -> None:
        self._cdp = cdp_session
        self._handlers: Dict[str, Dict[int, Callable[..., None]]] = {}
        self._handler_id = 0

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        # Playwright CDPSession.send(method, params) expects params as a single dict
        if params:
            return await self._cdp.send(method, params)
        return await self._cdp.send(method)

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        def wrapper(params: Any) -> None:
            handler(params)

        if event not in self._handlers:
            self._handlers[event] = {}
        self._handler_id += 1
        hid = self._handler_id
        self._handlers[event][hid] = (handler, wrapper)
        self._cdp.on(event, wrapper)

    def off(self, event: str, handler: Callable[[Any], None]) -> None:
        if event not in self._handlers:
            return
        for hid, (h, wrapper) in list(self._handlers[event].items()):
            if h is handler:
                if hasattr(self._cdp, "remove_listener"):
                    self._cdp.remove_listener(event, wrapper)
                del self._handlers[event][hid]
                break
