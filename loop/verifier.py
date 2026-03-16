"""
Verifier: verifies terminate actions. Port of src/loop/verifier.ts.
"""
from __future__ import annotations

import base64
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Union

from model.adapter import ModelAdapter
from agent_types import ScreenshotResult

# Screenshot can be ScreenshotResult dataclass or dict from tab.screenshot()
ScreenshotLike = Union[ScreenshotResult, Dict[str, Any]]


@dataclass
class VerifyResult:
    passed: bool
    reason: Optional[str] = None


class Verifier(ABC):
    """Verifies that a terminate action actually corresponds to task completion."""

    @abstractmethod
    async def verify(self, screenshot: ScreenshotResult, url: str) -> VerifyResult:
        pass


class UrlMatchesGate(Verifier):
    """Passes if the current URL matches the given pattern."""

    def __init__(self, pattern: Any) -> None:  # re.Pattern or str
        import re
        self._pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    async def verify(self, screenshot: ScreenshotResult, url: str) -> VerifyResult:
        if self._pattern.search(url):
            return VerifyResult(passed=True)
        return VerifyResult(
            passed=False,
            reason=f'URL "{url}" does not match expected pattern {self._pattern.pattern}',
        )


class CustomGate(Verifier):
    """Passes based on a custom async predicate."""

    def __init__(
        self,
        fn: Callable[[ScreenshotLike, str], Any],
        failure_reason: str = "completion condition not met",
    ) -> None:
        self._fn = fn
        self._failure_reason = failure_reason

    async def verify(self, screenshot: ScreenshotResult, url: str) -> VerifyResult:
        passed = await self._fn(screenshot, url)
        return VerifyResult(passed=bool(passed)) if passed else VerifyResult(passed=False, reason=self._failure_reason)


class ModelVerifier(Verifier):
    """Uses the model to verify task completion from a screenshot."""

    def __init__(
        self,
        adapter: ModelAdapter,
        task: str,
        max_attempts: int = 2,
    ) -> None:
        self._adapter = adapter
        self._task = task
        self._max_attempts = max_attempts
        self._attempts = 0

    async def verify(self, screenshot: ScreenshotResult, url: str) -> VerifyResult:
        if self._attempts >= self._max_attempts:
            return VerifyResult(passed=True)
        self._attempts += 1

        data = screenshot.get("data", b"") if isinstance(screenshot, dict) else screenshot.data
        b64 = base64.b64encode(data).decode("ascii") if isinstance(data, bytes) else str(data)

        wire_history = [
            {
                "role": "screenshot",
                "base64": b64,
                "stepIndex": 0,
                "compressed": False,
            },
        ]

        context = {
            "screenshot": screenshot,
            "wire_history": wire_history,
            "agent_state": None,
            "step_index": 0,
            "max_steps": 1,
            "url": url,
            "system_prompt": "\n".join([
                "You are a task completion verifier.",
                f"Task: {self._task}",
                "Look at the current screenshot. Has the task been fully completed?",
                "Respond with exactly: YES or NO, followed by one sentence explaining why.",
            ]),
        }
        response = await self._adapter.step(context)

        resp: Dict[str, Any] = response
        thinking = resp.get("thinking")
        actions = resp.get("actions", [])
        text = thinking or " ".join(json.dumps(a) for a in actions)
        passed = bool(re.match(r"^yes\b", text.strip(), re.IGNORECASE))
        return VerifyResult(passed=passed) if passed else VerifyResult(passed=False, reason=text.strip()[:200])
