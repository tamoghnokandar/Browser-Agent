"""
ActionVerifier: post-action heuristic checks. Port of src/loop/action-verifier.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from browser.tab import BrowserTab
from agent_types import Action, ActionExecution


@dataclass
class ActionVerification:
    success: bool
    hint: Optional[str] = None


class ActionVerifier:
    """BacktrackAgent-inspired post-action verifier."""

    async def verify(
        self,
        action: Action,
        outcome: ActionExecution,
        tab: BrowserTab,
        prev_url: str,
    ) -> ActionVerification:
        if not outcome.ok:
            return ActionVerification(success=False, hint=f'Action "{action["type"]}" failed: {outcome.error}')

        action_type = action["type"]
        if action_type in ("click", "doubleClick"):
            return await self._verify_click(action, outcome, tab, prev_url)
        if action_type == "type":
            return await self._verify_type(tab)
        if action_type == "goto":
            return await self._verify_goto(action, tab)
        return ActionVerification(success=True)

    async def _verify_click(
        self,
        action: Action,
        outcome: ActionExecution,
        tab: BrowserTab,
        prev_url: str,
    ) -> ActionVerification:
        click_target = (outcome.click_target or "").lower()
        if click_target:
            if any(x in click_target for x in ("input", "button", "link", "select", "a ", "checkbox", "radio", "textarea")):
                return ActionVerification(success=True)

        current_url = tab.url()
        if current_url != prev_url:
            return ActionVerification(success=True)

        return ActionVerification(success=True)

    async def _verify_type(self, tab: BrowserTab) -> ActionVerification:
        try:
            focus_info = await tab.evaluate("""
                (() => {
                  const el = document.activeElement;
                  if (!el) return 'none';
                  const tag = el.tagName.toLowerCase();
                  if (tag === 'input' || tag === 'textarea' || el.contentEditable === 'true') {
                    return 'input:' + (el.value || el.textContent || '').slice(0, 30);
                  }
                  return 'other:' + tag;
                })()
            """)
            if focus_info == "none" or (isinstance(focus_info, str) and focus_info.startswith("other:")):
                return ActionVerification(
                    success=False,
                    hint="Type action may have failed — no input element was focused. Try clicking the input field first.",
                )
            return ActionVerification(success=True)
        except Exception:
            return ActionVerification(success=True)

    async def _verify_goto(self, action: Action, tab: BrowserTab) -> ActionVerification:
        try:
            target_url = action["url"]
            current_url = tab.url()
            target_host = urlparse(target_url).hostname or ""
            current_host = urlparse(current_url).hostname or ""
            if target_host and target_host != current_host and target_host not in current_url:
                return ActionVerification(
                    success=False,
                    hint=f"Navigation may have failed — expected {target_host} but got {current_host}. Page may have blocked the redirect.",
                )
        except Exception:
            pass
        return ActionVerification(success=True)
