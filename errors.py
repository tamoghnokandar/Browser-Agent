"""
Browser Agent error types. Port of src/errors.ts.
"""
from __future__ import annotations

from typing import Literal, Optional

BrowserAgentErrorCode = Literal[
    "BROWSER_DISCONNECTED",
    "MODEL_API_ERROR",
    "SESSION_TIMEOUT",
    "MAX_RETRIES_EXCEEDED",
    "POLICY_VIOLATION",
    "CHILD_LOOP_FAILED",
]


class BrowserAgentError(Exception):
    code: BrowserAgentErrorCode
    step: Optional[int]

    def __init__(
        self,
        code: BrowserAgentErrorCode,
        message: str,
        step: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.name = "BrowserAgentError"
        self.code = code
        self.step = step
