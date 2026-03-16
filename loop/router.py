"""
ActionRouter: translates Action objects (pixel coords) into browser operations.
Port of src/loop/router.ts. Coordinates are in viewport pixels.
Errors are returned as ActionExecution, never raised.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from browser.tab import BrowserTab
from logger import BrowserAgentLogger
from agent_types import Action, ActionExecution
from .state import StateStore


@dataclass
class RouterTiming:
    """Timing delays after browser operations (milliseconds)."""
    after_click: Optional[int] = None       # Default: 200
    after_type: Optional[int] = None        # Default: 500
    after_scroll: Optional[int] = None       # Default: 300
    after_navigation: Optional[int] = None  # Default: 2000 for waitForLoad


def _sleep(ms: int):
    return asyncio.sleep(ms / 1000.0)


def _outcome_ok(o: Any) -> bool:
    return o.get("ok", True) if isinstance(o, dict) else getattr(o, "ok", True)


def _outcome_error(o: Any) -> Optional[str]:
    return o.get("error") if isinstance(o, dict) else getattr(o, "error", None)


def _outcome_click_target(o: Any) -> Optional[str]:
    if isinstance(o, dict):
        return o.get("clickTarget") or o.get("click_target")
    return getattr(o, "click_target", None) or getattr(o, "clickTarget", None)


class ActionRouter:
    """Translates Action objects (pixel coords) into browser operations."""

    def __init__(
        self,
        timing: Optional[RouterTiming] = None,
        log: Optional[BrowserAgentLogger] = None,
    ) -> None:
        self._timing = timing if timing is not None else RouterTiming()
        self._log = log
        self._last_click_px: Optional[tuple[int, int]] = None

    def _log_action(self, msg: str, data: Optional[dict] = None) -> None:
        if self._log is not None and hasattr(self._log, "action"):
            self._log.action(msg, data)

    async def execute(
        self,
        action: Action,
        tab: BrowserTab,
        state: StateStore,
    ) -> ActionExecution:
        t0 = time.time()
        action_type = action["type"]

        if action_type == "click":
            x = action.get("x", 0)
            y = action.get("y", 0)
            button = action.get("button")
            if button is None:
                button = "left"
            self._log_action(f"click px({x},{y}) btn={button}")
            outcome: Dict[str, Any] = await tab.click(x, y, {"button": button})
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            click_target = _outcome_click_target(outcome)
            if not ok:
                self._log_action(f"click FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"click ok ({elapsed}ms)", {"elapsed": elapsed})
            self._last_click_px = (x, y)
            delay = getattr(self._timing, "after_click", None)
            await _sleep(200 if delay is None else delay)
            return ActionExecution(ok=ok, error=err, click_target=click_target)

        if action_type == "doubleClick":
            x = action.get("x", 0)
            y = action.get("y", 0)
            self._log_action(f"doubleClick px({x},{y})")
            outcome = await tab.double_click(x, y)
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            click_target = _outcome_click_target(outcome)
            if not ok:
                self._log_action(f"doubleClick FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"doubleClick ok ({elapsed}ms)", {"elapsed": elapsed})
            self._last_click_px = (x, y)
            delay = getattr(self._timing, "after_click", None)
            await _sleep(200 if delay is None else delay)
            return ActionExecution(ok=ok, error=err, click_target=click_target)

        if action_type == "drag":
            from_x = action.get("startX", 0)
            from_y = action.get("startY", 0)
            to_x = action.get("endX", 0)
            to_y = action.get("endY", 0)
            self._log_action(f"drag px({from_x},{from_y})→({to_x},{to_y})")
            outcome = await tab.drag(from_x, from_y, to_x, to_y)
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            if not ok:
                self._log_action(f"drag FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"drag ok ({elapsed}ms)", {"elapsed": elapsed})
            delay = getattr(self._timing, "after_click", None)
            await _sleep(200 if delay is None else delay)
            return ActionExecution(ok=ok, error=err)

        if action_type == "scroll":
            x = action.get("x", 0)
            y = action.get("y", 0)
            direction = action.get("direction", "up")
            amount = action.get("amount", 1) * 100
            if direction == "right":
                delta_x, delta_y = amount, 0
            elif direction == "left":
                delta_x, delta_y = -amount, 0
            elif direction == "down":
                delta_x, delta_y = 0, amount
            else:
                delta_x, delta_y = 0, -amount
            self._log_action(f"scroll px({x},{y}) dir={direction} amount={action.get('amount')}")
            outcome: Dict[str, Any] = await tab.scroll(x, y, delta_x, delta_y)
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            if not ok:
                self._log_action(f"scroll FAILED ({elapsed}ms): {_outcome_error(outcome)}", {"elapsed": elapsed, "error": _outcome_error(outcome)})
            else:
                self._log_action(f"scroll ok ({elapsed}ms)", {"elapsed": elapsed})
            delay = getattr(self._timing, "after_scroll", None)
            await _sleep(300 if delay is None else delay)
            return ActionExecution(ok=ok, error=_outcome_error(outcome))

        if action_type == "type":
            text = action.get("text", "")
            preview = text[:40] + ("..." if len(text) > 40 else "")
            self._log_action(f'type "{preview}" ({len(text)} chars)')
            outcome = await tab.type(text, {"delay_ms": 30})
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            if not ok:
                self._log_action(f"type FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"type ok ({elapsed}ms)", {"elapsed": elapsed})
            delay = getattr(self._timing, "after_type", None)
            await _sleep(500 if delay is None else delay)
            return ActionExecution(ok=ok, error=err)

        if action_type == "keyPress":
            keys = action.get("keys", [])
            self._log_action(f"keyPress [{', '.join(keys)}]")
            outcome = await tab.key_press(keys)
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            if not ok:
                self._log_action(f"keyPress FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"keyPress ok ({elapsed}ms)", {"elapsed": elapsed})
            await _sleep(100)
            return ActionExecution(ok=ok, error=err)

        if action_type == "goto":
            url = action.get("url", "")
            self._log_action(f"goto {url}")
            try:
                await tab.goto(url)
                timeout = getattr(self._timing, "after_navigation", None)
                timeout = 2000 if timeout is None else timeout
                await tab.wait_for_load(timeout_ms=timeout)
                elapsed = int((time.time() - t0) * 1000)
                self._log_action(f"goto ok ({elapsed}ms)", {"elapsed": elapsed, "url": url})
                return ActionExecution(ok=True)
            except Exception as err:
                elapsed = int((time.time() - t0) * 1000)
                self._log_action(f"goto FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "url": url, "error": str(err)})
                return ActionExecution(ok=False, error=str(err))

        if action_type == "wait":
            ms = action.get("ms", 0)
            self._log_action(f"wait {ms}ms")
            await _sleep(ms)
            return ActionExecution(ok=True)

        if action_type == "writeState":
            data = action.get("data", {})
            self._log_action(f"writeState {str(data)[:80]}")
            state.write(data)
            return ActionExecution(ok=True)

        if action_type == "screenshot":
            self._log_action("screenshot (noop — loop will capture next step)")
            return ActionExecution(ok=True, is_screenshot_request=True)

        if action_type == "terminate":
            status = action.get("status", "success")
            result = action.get("result", "")
            self._log_action(f"terminate status={status}: \"{result[:80]}\"")
            return ActionExecution(
                ok=True,
                terminated=True,
                status=status,
                result=result,
            )

        if action_type == "hover":
            x = action.get("x", 0)
            y = action.get("y", 0)
            self._log_action(f"hover px({x},{y})")
            outcome = await tab.hover(x, y)
            elapsed = int((time.time() - t0) * 1000)
            ok = _outcome_ok(outcome)
            err = _outcome_error(outcome)
            if not ok:
                self._log_action(f"hover FAILED ({elapsed}ms): {err}", {"elapsed": elapsed, "error": err})
            else:
                self._log_action(f"hover ok ({elapsed}ms)", {"elapsed": elapsed})
            delay = getattr(self._timing, "after_click", None)
            await _sleep(200 if delay is None else delay)
            return ActionExecution(ok=ok, error=err)

        if action_type == "delegate":
            instruction = action.get("instruction", "")
            max_steps = action.get("max_steps")
            log_max_steps = 20 if max_steps is None else max_steps
            instr_preview = instruction[:80] + ("..." if len(instruction) > 80 else "")
            self._log_action(f'delegate "{instr_preview}" max_steps={log_max_steps}')
            return ActionExecution(
                ok=True,
                is_delegate_request=True,
                delegate_instruction=instruction,
                delegate_max_steps=max_steps,
            )

        if action_type == "fold":
            summary = action.get("summary", "")
            self._log_action(f'fold "{summary[:60]}"')
            return ActionExecution(ok=True)

        return ActionExecution(ok=False, error=f"Unknown action type: {action_type}")


    def last_click(self) -> Optional[tuple[int, int]]:
        """Last click coordinates (x, y) or None."""
        return self._last_click_px
