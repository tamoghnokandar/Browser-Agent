"""
CDPTab: BrowserTab implementation via CDP. Port of src/browser/cdptab.ts.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Optional

from .tab import BrowserTab, ClickOptions, DragOptions, TypeOptions
from .types import ActionOutcome, ScreenshotOptions, ScreenshotResult, ViewportSize

MOD_ALT = 1
MOD_CTRL = 2
MOD_META = 4
MOD_SHIFT = 8


class _NoopLogger:
    def browser(self, message: str, data: Optional[dict[str, Any]] = None) -> None:
        pass


SPECIAL_KEYS: dict[str, dict[str, Any]] = {
    "return": {"key": "Enter", "code": "Enter", "keyCode": 13, "text": "\r"},
    "enter": {"key": "Enter", "code": "Enter", "keyCode": 13, "text": "\r"},
    "tab": {"key": "Tab", "code": "Tab", "keyCode": 9, "text": "\t"},
    "backspace": {"key": "Backspace", "code": "Backspace", "keyCode": 8},
    "delete": {"key": "Delete", "code": "Delete", "keyCode": 46},
    "escape": {"key": "Escape", "code": "Escape", "keyCode": 27},
    "esc": {"key": "Escape", "code": "Escape", "keyCode": 27},
    "space": {"key": " ", "code": "Space", "keyCode": 32, "text": " "},
    "arrowup": {"key": "ArrowUp", "code": "ArrowUp", "keyCode": 38},
    "arrowdown": {"key": "ArrowDown", "code": "ArrowDown", "keyCode": 40},
    "arrowleft": {"key": "ArrowLeft", "code": "ArrowLeft", "keyCode": 37},
    "arrowright": {"key": "ArrowRight", "code": "ArrowRight", "keyCode": 39},
    "home": {"key": "Home", "code": "Home", "keyCode": 36},
    "end": {"key": "End", "code": "End", "keyCode": 35},
    "pageup": {"key": "PageUp", "code": "PageUp", "keyCode": 33},
    "pagedown": {"key": "PageDown", "code": "PageDown", "keyCode": 34},
    "insert": {"key": "Insert", "code": "Insert", "keyCode": 45},
    "f1": {"key": "F1", "code": "F1", "keyCode": 112},
    "f2": {"key": "F2", "code": "F2", "keyCode": 113},
    "f3": {"key": "F3", "code": "F3", "keyCode": 114},
    "f4": {"key": "F4", "code": "F4", "keyCode": 115},
    "f5": {"key": "F5", "code": "F5", "keyCode": 116},
    "f6": {"key": "F6", "code": "F6", "keyCode": 117},
    "f7": {"key": "F7", "code": "F7", "keyCode": 118},
    "f8": {"key": "F8", "code": "F8", "keyCode": 119},
    "f9": {"key": "F9", "code": "F9", "keyCode": 120},
    "f10": {"key": "F10", "code": "F10", "keyCode": 121},
    "f11": {"key": "F11", "code": "F11", "keyCode": 122},
    "f12": {"key": "F12", "code": "F12", "keyCode": 123},
}


class CDPTab(BrowserTab):
    """BrowserTab implemented via Chrome DevTools Protocol."""

    def __init__(self, session: Any, log: Optional[Any] = None) -> None:
        self._session = session
        self._log = log or _NoopLogger()
        self._current_url = "about:blank"
        self._current_viewport = ViewportSize(width=1280, height=720)
        self._last_click_px: Optional[dict[str, float]] = None
        self._url_bar = {"active": False, "buffer": ""}
        self._register_session_listeners(session)

    def _register_session_listeners(self, session: Any) -> None:
        def on_navigated_within_document(params: Any) -> None:
            if isinstance(params, dict):
                url = params.get("url")
                if isinstance(url, str):
                    self._current_url = url
                    self._log.browser(f"navigatedWithinDocument: {url}")

        def on_frame_navigated(params: Any) -> None:
            if not isinstance(params, dict):
                return
            frame = params.get("frame")
            if not isinstance(frame, dict):
                return
            if frame.get("parentId"):
                return
            url = frame.get("url")
            if isinstance(url, str):
                self._current_url = url
                self._log.browser(f"frameNavigated: {url}")

        if hasattr(session, "on"):
            session.on("Page.navigatedWithinDocument", on_navigated_within_document)
            session.on("Page.frameNavigated", on_frame_navigated)
        coro = session.send("Page.enable")
        if asyncio.iscoroutine(coro):
            asyncio.create_task(self._swallow(coro))

    async def _swallow(self, awaitable: Any) -> None:
        try:
            await awaitable
        except Exception:
            pass

    async def reconnect(self, new_session: Any) -> None:
        self._session = new_session
        self._current_url = "about:blank"
        self._url_bar = {"active": False, "buffer": ""}
        self._last_click_px = None
        self._register_session_listeners(new_session)
        self._log.browser("CDPTab reconnected to new CDP session")
        await self.sync_url()

    def reset_input_state(self) -> None:
        self._url_bar = {"active": False, "buffer": ""}
        self._last_click_px = None

    async def sync_url(self) -> None:
        try:
            href = await self.evaluate("window.location.href")
            if isinstance(href, str) and href:
                self._log.browser(f"syncUrl: {href}")
                self._current_url = href
        except Exception:
            pass

    async def screenshot(self, options: ScreenshotOptions | None = None) -> ScreenshotResult:
        opts = options or ScreenshotOptions()
        try:
            fmt = opts.format or "png"
            params: dict[str, Any] = {"format": fmt}
            if fmt == "jpeg" and opts.quality is not None:
                params["quality"] = opts.quality
            if opts.full_page:
                params["captureBeyondViewport"] = True

            result = await self._session.send("Page.captureScreenshot", params)
            raw = result.get("data", "") if isinstance(result, dict) else ""
            data = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
            size_kb = round(len(data) / 1024, 1)

            has_cursor = opts.cursor_overlay is not False and self._last_click_px is not None
            if has_cursor and self._last_click_px is not None:
                data = await self._compose_cursor(data, self._last_click_px["x"], self._last_click_px["y"])

            msg = (
                f"screenshot: {self._current_viewport.width}x{self._current_viewport.height} {fmt} {size_kb}KB"
            )
            if has_cursor and self._last_click_px is not None:
                msg += f' cursor=({self._last_click_px["x"]},{self._last_click_px["y"]})'
            self._log.browser(
                msg,
                {
                    "width": self._current_viewport.width,
                    "height": self._current_viewport.height,
                    "format": fmt,
                    "sizeKB": size_kb,
                },
            )
            return ScreenshotResult(
                data=data,
                width=self._current_viewport.width,
                height=self._current_viewport.height,
                mime_type="image/jpeg" if fmt == "jpeg" else "image/png",
            )
        except Exception as err:
            self._log.browser(f"screenshot FAILED: {err}", {"error": str(err)})
            raise RuntimeError(f"Screenshot failed: {err}") from err

    async def _compose_cursor(self, buf: bytes, x: float, y: float) -> bytes:
        try:
            from io import BytesIO

            from PIL import Image, ImageDraw

            base = Image.open(BytesIO(buf)).convert("RGBA")
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            circle_size = 12
            half = circle_size / 2
            left = max(0, round(x - half))
            top = max(0, round(y - half))
            draw.ellipse(
                (left, top, left + circle_size - 1, top + circle_size - 1),
                fill=(255, 0, 0, 204),
            )
            out = Image.alpha_composite(base, overlay)
            out_buf = BytesIO()
            out.save(out_buf, format="PNG")
            return out_buf.getvalue()
        except Exception:
            return buf

    async def click(self, x: float, y: float, options: ClickOptions | None = None) -> ActionOutcome:
        opts = options or {}
        button = opts.get("button", "left")
        click_count = opts.get("click_count", 1)
        self._log.browser(f"click: px({x},{y}) btn={button}")
        try:
            await self._session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": button})
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": click_count},
            )
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": click_count},
            )
            self._last_click_px = {"x": x, "y": y}
            click_info: Optional[str] = None
            try:
                click_info = await self.evaluate(
                    """
                    (() => {
                      const el = document.activeElement;
                      if (!el || el === document.body) return '';
                      const tag = el.tagName.toLowerCase();
                      const role = el.getAttribute('role') || '';
                      const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.textContent?.slice(0, 40)?.trim() || '';
                      return tag + (role ? '[role=' + role + ']' : '') + (label ? ': ' + label : '');
                    })()
                    """
                )
            except Exception:
                pass
            if click_info:
                self._log.browser(f"click focused: {click_info}")
            return ActionOutcome(ok=True, click_target=click_info or None)
        except Exception as err:
            self._log.browser(f"click FAILED: {err}", {"x": x, "y": y, "error": str(err)})
            return ActionOutcome(ok=False, error=str(err))

    async def double_click(self, x: float, y: float) -> ActionOutcome:
        self._log.browser(f"doubleClick: px({x},{y})")
        try:
            await self._session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 2},
            )
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 2},
            )
            self._last_click_px = {"x": x, "y": y}
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(f"doubleClick FAILED: {err}", {"x": x, "y": y, "error": str(err)})
            return ActionOutcome(ok=False, error=str(err))

    async def hover(self, x: float, y: float) -> ActionOutcome:
        self._log.browser(f"hover: px({x},{y})")
        try:
            await self._session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(f"hover FAILED: {err}", {"x": x, "y": y, "error": str(err)})
            return ActionOutcome(ok=False, error=str(err))

    async def drag(
        self,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        options: DragOptions | None = None,
    ) -> ActionOutcome:
        opts = options or {}
        steps = opts.get("steps", 10)
        self._log.browser(f"drag: px({from_x},{from_y}) → px({to_x},{to_y})")
        try:
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": from_x, "y": from_y, "button": "left"},
            )
            for i in range(1, steps + 1):
                mx = round(from_x + (to_x - from_x) * (i / steps))
                my = round(from_y + (to_y - from_y) * (i / steps))
                await self._session.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": mx, "y": my, "button": "left"},
                )
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": to_x, "y": to_y, "button": "left"},
            )
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(
                f"drag FAILED: {err}",
                {"fromX": from_x, "fromY": from_y, "toX": to_x, "toY": to_y, "error": str(err)},
            )
            return ActionOutcome(ok=False, error=str(err))

    async def scroll(self, x: float, y: float, delta_x: float, delta_y: float) -> ActionOutcome:
        self._log.browser(f"scroll: px({x},{y}) delta=({delta_x},{delta_y})")
        try:
            await self._session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            await self._session.send(
                "Input.dispatchMouseEvent",
                {"type": "mouseWheel", "x": x, "y": y, "deltaX": delta_x, "deltaY": delta_y},
            )
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(
                f"scroll FAILED: {err}",
                {"x": x, "y": y, "deltaX": delta_x, "deltaY": delta_y, "error": str(err)},
            )
            return ActionOutcome(ok=False, error=str(err))

    async def type(self, text: str, options: TypeOptions | None = None) -> ActionOutcome:
        opts = options or {}
        try:
            if self._url_bar["active"]:
                newline_idx = next((i for i, ch in enumerate(text) if ch in "\r\n"), -1)
                has_newline = newline_idx != -1
                self._url_bar["buffer"] += text[:newline_idx] if has_newline else text
                preview = text[:40]
                self._log.browser(
                    f'urlBar: buffered "{preview}" → buffer="{self._url_bar["buffer"][:80]}"'
                )
                if has_newline:
                    url = self._url_bar["buffer"].strip()
                    self._log.browser(f'urlBar: implicit Enter (newline in type) → "{url}"')
                    self._url_bar = {"active": False, "buffer": ""}
                    if url:
                        full_url = url if url.lower().startswith(("http://", "https://")) else f"https://{url}"
                        await self.goto(full_url)
                return ActionOutcome(ok=True)

            preview = text[:40]
            suffix = "..." if len(text) > 40 else ""
            self._log.browser(f'type: "{preview}{suffix}" ({len(text)} chars)')
            delay_ms = opts.get("delay_ms", 0)
            for ch in text:
                code = _char_to_code(ch)
                windows_virtual_key_code = ord(ch)
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": ch,
                        "code": code,
                        "windowsVirtualKeyCode": windows_virtual_key_code,
                    },
                )
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "char",
                        "key": ch,
                        "code": code,
                        "text": ch,
                        "unmodifiedText": ch,
                        "windowsVirtualKeyCode": windows_virtual_key_code,
                    },
                )
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyUp",
                        "key": ch,
                        "code": code,
                        "windowsVirtualKeyCode": windows_virtual_key_code,
                    },
                )
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)

            type_verification: Optional[str] = None
            try:
                type_verification = await self.evaluate(
                    """
                    (() => {
                      const el = document.activeElement;
                      if (!el) return '';
                      const tag = el.tagName.toLowerCase();
                      if (tag === 'input' || tag === 'textarea') {
                        return 'value:' + (el.value || '').slice(-60);
                      }
                      if (el.isContentEditable) {
                        return 'value:' + (el.textContent || '').slice(-60);
                      }
                      return 'no-input-focused';
                    })()
                    """
                )
            except Exception:
                pass

            if type_verification == "no-input-focused":
                warning = "WARNING: no input element was focused during typing — text may not have been captured"
                self._log.browser("type WARNING: no input element focused — text may not have been captured")
                return ActionOutcome(ok=True, error=warning)
            if type_verification:
                self._log.browser(f"type verified: {type_verification}")
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(f"type FAILED: {err}", {"error": str(err)})
            return ActionOutcome(ok=False, error=str(err))

    async def key_press(self, key: str | list[str]) -> ActionOutcome:
        try:
            keys = key if isinstance(key, list) else [key]
            lowers = [k.lower() for k in keys]
            has_ctrl = any(k in {"ctrl", "control"} for k in lowers)
            has_l = "l" in lowers
            has_f6 = "f6" in lowers
            if (has_ctrl and has_l) or has_f6:
                self._log.browser(f"urlBar: activated ({'+'.join(keys)})")
                self._url_bar = {"active": True, "buffer": ""}
                return ActionOutcome(ok=True)

            if any(k in {"escape", "esc"} for k in lowers):
                if self._url_bar["active"]:
                    self._log.browser("urlBar: cancelled")
                self._url_bar = {"active": False, "buffer": ""}

            if self._url_bar["active"] and any(k in {"return", "enter"} for k in lowers):
                url = self._url_bar["buffer"].strip()
                self._log.browser(f'urlBar: Enter → "{url}"')
                self._url_bar = {"active": False, "buffer": ""}
                if url:
                    full_url = url if url.lower().startswith(("http://", "https://")) else f"https://{url}"
                    await self.goto(full_url)
                return ActionOutcome(ok=True)

            if not self._url_bar["active"]:
                self._log.browser(f"keyPress: [{', '.join(keys)}]")

            mod_keys = [k for k in keys if _modifier_flag(k) > 0]
            main_keys = [k for k in keys if _modifier_flag(k) == 0]
            mod_bits = 0
            for k in mod_keys:
                mod_bits |= _modifier_flag(k)

            for mk in mod_keys:
                props = _resolve_key_props(mk)
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": props["key"],
                        "code": props["code"],
                        "windowsVirtualKeyCode": props["keyCode"],
                        "modifiers": mod_bits,
                    },
                )
            for mk in main_keys:
                props = _resolve_key_props(mk)
                payload = {
                    "type": "keyDown",
                    "key": props["key"],
                    "code": props["code"],
                    "windowsVirtualKeyCode": props["keyCode"],
                    "modifiers": mod_bits,
                }
                if props.get("text") is not None:
                    payload["text"] = props["text"]
                    payload["unmodifiedText"] = props["text"]
                await self._session.send("Input.dispatchKeyEvent", payload)
                if props.get("text") is not None:
                    await self._session.send(
                        "Input.dispatchKeyEvent",
                        {
                            "type": "char",
                            "key": props["key"],
                            "code": props["code"],
                            "text": props["text"],
                            "unmodifiedText": props["text"],
                            "windowsVirtualKeyCode": props["keyCode"],
                            "modifiers": mod_bits,
                        },
                    )
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyUp",
                        "key": props["key"],
                        "code": props["code"],
                        "windowsVirtualKeyCode": props["keyCode"],
                        "modifiers": mod_bits,
                    },
                )
            for mk in reversed(mod_keys):
                props = _resolve_key_props(mk)
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyUp",
                        "key": props["key"],
                        "code": props["code"],
                        "windowsVirtualKeyCode": props["keyCode"],
                        "modifiers": 0,
                    },
                )
            return ActionOutcome(ok=True)
        except Exception as err:
            self._log.browser(
                f"keyPress FAILED: {err}",
                {"keys": key if isinstance(key, list) else [key], "error": str(err)},
            )
            return ActionOutcome(ok=False, error=str(err))

    async def goto(self, url: str) -> None:
        if self._url_bar["active"]:
            self._url_bar = {"active": False, "buffer": ""}
        self._log.browser(f"goto: {url}")
        result = await self._session.send("Page.navigate", {"url": url})
        if isinstance(result, dict) and result.get("errorText"):
            error_text = str(result["errorText"])
            self._log.browser(f"goto FAILED: {error_text}", {"url": url, "error": error_text})
            raise RuntimeError(f"Navigation failed: {error_text}")
        self._current_url = url
        await self.wait_for_load(8000)

    async def wait_for_load(self, timeout_ms: int | None = None) -> None:
        timeout = 5000 if timeout_ms is None else timeout_ms
        try:
            await self._session.send("Page.setLifecycleEventsEnabled", {"enabled": True})
        except Exception:
            pass

        if not hasattr(self._session, "on") or not hasattr(self._session, "off"):
            await asyncio.sleep(timeout / 1000.0)
            return

        loop = asyncio.get_running_loop()
        done_fut: asyncio.Future[None] = loop.create_future()
        t0 = loop.time()

        def done(reason: str) -> None:
            if done_fut.done():
                return
            self._session.off("Page.lifecycleEvent", lifecycle_handler)
            self._session.off("Page.loadEventFired", load_handler)
            elapsed = round((loop.time() - t0) * 1000)
            if reason == "timeout":
                self._log.browser(f"waitForLoad: timed out after {elapsed}ms")
            else:
                self._log.browser(f"waitForLoad: {reason} after {elapsed}ms", {"reason": reason, "elapsed": elapsed})
            done_fut.set_result(None)

        def lifecycle_handler(params: Any) -> None:
            if isinstance(params, dict) and params.get("name") == "networkIdle":
                done("networkIdle")

        def load_handler(*_: Any) -> None:
            done("loadEventFired")

        timer = loop.call_later(timeout / 1000.0, lambda: done("timeout"))
        self._session.on("Page.lifecycleEvent", lifecycle_handler)
        self._session.on("Page.loadEventFired", load_handler)
        try:
            await done_fut
        finally:
            timer.cancel()

    def url(self) -> str:
        return self._current_url

    def viewport(self) -> ViewportSize:
        return ViewportSize(width=self._current_viewport.width, height=self._current_viewport.height)

    async def set_viewport(self, size: ViewportSize) -> None:
        self._log.browser(f"setViewport: {size.width}x{size.height}")
        await self._session.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": size.width,
                "height": size.height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        self._current_viewport = ViewportSize(width=size.width, height=size.height)

    async def evaluate(self, script: str) -> Any:
        result = await self._session.send(
            "Runtime.evaluate",
            {"expression": script, "returnByValue": True},
        )
        if isinstance(result, dict) and result.get("exceptionDetails") is not None:
            raise RuntimeError(f"Evaluate failed: {json.dumps(result['exceptionDetails'])}")
        if isinstance(result, dict):
            inner = result.get("result", {})
            if isinstance(inner, dict):
                return inner.get("value")
        return None

    async def close(self) -> None:
        try:
            await self._session.send("Target.closeTarget", {})
        except Exception:
            pass


def _resolve_key_props(key_name: str) -> dict[str, Any]:
    lower = key_name.lower()
    special = SPECIAL_KEYS.get(lower)
    if special is not None:
        return dict(special)
    if len(key_name) == 1:
        ch = key_name
        code = _char_to_code(ch)
        vk = ord(ch.upper())
        return {"key": ch, "code": code, "keyCode": vk, "text": ch}
    return {"key": key_name, "code": key_name, "keyCode": 0}


def _modifier_flag(key: str) -> int:
    k = key.lower()
    if k == "alt":
        return MOD_ALT
    if k in {"ctrl", "control"}:
        return MOD_CTRL
    if k in {"meta", "command", "cmd"}:
        return MOD_META
    if k == "shift":
        return MOD_SHIFT
    return 0


def _char_to_code(ch: str) -> str:
    if "a" <= ch <= "z":
        return f"Key{ch.upper()}"
    if "A" <= ch <= "Z":
        return f"Key{ch}"
    if "0" <= ch <= "9":
        return f"Digit{ch}"
    if ch == " ":
        return "Space"
    if ch in {"\n", "\r"}:
        return "Enter"
    if ch == "\t":
        return "Tab"
    punct = {
        "-": "Minus",
        "=": "Equal",
        "[": "BracketLeft",
        "]": "BracketRight",
        "\\": "Backslash",
        ";": "Semicolon",
        "'": "Quote",
        "`": "Backquote",
        ",": "Comma",
        ".": "Period",
        "/": "Slash",
    }
    return punct.get(ch, "")
