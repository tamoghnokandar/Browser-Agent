"""
CdpSession / CdpConnection: Chrome DevTools Protocol transport.
Port of src/browser/cdp.ts.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, Set, TypeVar, cast

import websockets
from websockets import ConnectionClosed

T = TypeVar("T")


class CDPSessionLike(Protocol):
    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any: ...
    def on(self, event: str, handler: Callable[[Any], None]) -> None: ...
    def off(self, event: str, handler: Callable[[Any], None]) -> None: ...


SKIP_CDP_CMDS = {
    "Page.captureScreenshot",
    "Runtime.evaluate",
    "Input.dispatchMouseEvent",
    "Input.dispatchKeyEvent",
    "Input.insertText",
}

SKIP_CDP_EVENTS = {
    "Page.frameStartedLoading",
    "Page.frameStoppedLoading",
    "Page.domContentEventFired",
    "Page.lifecycleEvent",
}


class _NoopLogger:
    def cdp(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warn(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@dataclass
class _PendingCall:
    future: asyncio.Future[Any]
    method: str
    started_at: float
    should_log: bool


class CdpSession:
    def __init__(
        self,
        send_fn: Callable[[Dict[str, Any]], Any],
        session_id: Optional[str] = None,
        log: Optional[Any] = None,
    ) -> None:
        self._send_fn = send_fn
        self._session_id = session_id
        self._log = log or _NoopLogger()
        self._next_id = 1
        self._pending: Dict[int, _PendingCall] = {}
        self._listeners: Dict[str, Set[Callable[[Any], None]]] = {}

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        msg_id = self._next_id
        self._next_id += 1

        msg: Dict[str, Any] = {"id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        if self._session_id:
            msg["sessionId"] = self._session_id

        should_log = method not in SKIP_CDP_CMDS
        if should_log:
            p_str = json.dumps(params or {}, default=str)[:200] if params else ""
            self._log.cdp(f"→ {method}{' ' + p_str if p_str else ''}", {"id": msg_id})

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[msg_id] = _PendingCall(
            future=future,
            method=method,
            started_at=loop.time(),
            should_log=should_log,
        )

        try:
            result = self._send_fn(msg)
            if asyncio.iscoroutine(result):
                await cast("asyncio.Future[Any]", result)
        except Exception as e:
            pending = self._pending.pop(msg_id, None)
            if pending and not pending.future.done():
                pending.future.set_exception(e)
            raise

        return await future

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        self._listeners.setdefault(event, set()).add(handler)

    def off(self, event: str, handler: Callable[[Any], None]) -> None:
        self._listeners.get(event, set()).discard(handler)

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        if msg.get("id") is not None:
            msg_id = cast(int, msg["id"])
            pending = self._pending.pop(msg_id, None)
            if pending is None or pending.future.done():
                return

            elapsed = int((asyncio.get_running_loop().time() - pending.started_at) * 1000)
            if msg.get("error") is not None:
                err_obj = cast(Dict[str, Any], msg["error"])
                err = RuntimeError(
                    f"CDP error {err_obj.get('code')}: {err_obj.get('message')}"
                )
                if pending.should_log:
                    self._log.cdp(
                        f"✗ {pending.method} ({elapsed}ms) ERROR: {err}",
                        {"id": msg_id, "elapsed": elapsed, "error": str(err)},
                    )
                pending.future.set_exception(err)
            else:
                result = msg.get("result")
                if pending.should_log:
                    r_str = json.dumps(result if result is not None else {}, default=str)[:200]
                    self._log.cdp(
                        f"← {pending.method} ({elapsed}ms) {r_str}",
                        {"id": msg_id, "elapsed": elapsed},
                    )
                pending.future.set_result(result)
            return

        method = msg.get("method")
        if not method:
            return

        params = msg.get("params")
        if method == "Page.lifecycleEvent":
            name = params.get("name") if isinstance(params, dict) else None
            if name in {"networkIdle", "load", "commit"}:
                self._log.cdp(f"ev Page.lifecycleEvent name={name}")
        elif method not in SKIP_CDP_EVENTS:
            p_str = json.dumps(params if params is not None else {}, default=str)[:200]
            self._log.cdp(f"ev {method} {p_str}")

        handlers = tuple(self._listeners.get(method, set()))
        for handler in handlers:
            handler(params)

    def _reject_all(self, err: Exception) -> None:
        if self._pending:
            self._log.cdp(
                f"_rejectAll: rejecting {len(self._pending)} pending call(s): {err}"
            )
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(err)
        self._pending.clear()


class CdpConnection:
    def __init__(self, ws: Any, main: CdpSession, log: Optional[Any] = None) -> None:
        self._ws = ws
        self._main = main
        self._sessions: Dict[str, CdpSession] = {}
        self._log = log or _NoopLogger()
        self._recv_task: Optional[asyncio.Task[None]] = None
        self._closed = False

    @classmethod
    async def connect(cls, ws_url: str, log: Optional[Any] = None) -> "CdpConnection":
        if websockets is None:
            raise RuntimeError("websockets package is required for CdpConnection.connect()")

        logger = log or _NoopLogger()
        try:
            ws = await asyncio.wait_for(websockets.connect(ws_url), timeout=15.0)
        except asyncio.TimeoutError as e:
            raise RuntimeError(f"CDP connection timeout: {ws_url}") from e

        logger.cdp(f"connected: {ws_url}")

        async def send_(msg: Dict[str, Any]) -> None:
            await ws.send(json.dumps(msg))

        main_session = CdpSession(send_, None, logger)
        conn = cls(ws, main_session, logger)
        conn._recv_task = asyncio.create_task(conn._recv_loop())
        return conn

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                except Exception:
                    continue

                session_id = msg.get("sessionId")
                if session_id and session_id in self._sessions:
                    self._sessions[session_id]._handle_message(msg)
                else:
                    self._main._handle_message(msg)
        except ConnectionClosed:
            err = RuntimeError("CDP WebSocket closed")
            self._log.warn("[cdp] WebSocket closed", {})
            self._reject_all_sessions(err)
        except Exception as e:
            self._log.error(f"[cdp] WebSocket error: {e}", {})
            self._reject_all_sessions(e)
        finally:
            self._closed = True

    def _reject_all_sessions(self, err: Exception) -> None:
        self._main._reject_all(err)
        for session in self._sessions.values():
            session._reject_all(err)

    def main_session(self) -> CdpSession:
        return self._main

    async def new_session(self, target_id: str) -> CdpSession:
        result = await self._main.send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = cast(str, result["sessionId"])

        async def send_(msg: Dict[str, Any]) -> None:
            await self._ws.send(json.dumps(msg))

        session = CdpSession(send_, session_id, self._log)
        self._sessions[session_id] = session
        return session

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._ws.close()
        if self._recv_task is not None and self._recv_task is not asyncio.current_task():
            try:
                await self._recv_task
            except Exception:
                pass
