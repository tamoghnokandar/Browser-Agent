"""
Adapter interface and helpers. Port of src/model/adapter.ts.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterable, Optional, Protocol, runtime_checkable

from agent_types import (
    Action,
    Point,
    ScreenshotResult,
    TaskState,
    TokenUsage,
    ViewportSize,
    WireMessage,
)

# ─── Retry utility ────────────────────────────────────────────────────────────

async def retry_sleep(ms: int) -> None:
    await asyncio.sleep(ms / 1000.0)


def is_retryable(e: BaseException) -> bool:
    if isinstance(e, Exception):
        msg = str(e)
        if (
            "429" in msg
            or "529" in msg
            or "overloaded" in msg
            or "500" in msg
            or "503" in msg
        ):
            return True

    status = getattr(e, "status", None)
    return status in (429, 500, 503, 529)


async def with_retry(fn, attempts: int = 3):
    for i in range(attempts):
        try:
            return await fn()
        except BaseException as e:
            if i == attempts - 1 or not is_retryable(e):
                raise
            await retry_sleep(1000 * (2 ** i))
    raise RuntimeError("unreachable")


# ─── Adapter types ────────────────────────────────────────────────────────────

@dataclass
class StepContext:
    screenshot: ScreenshotResult
    wire_history: list[WireMessage]
    agent_state: Optional[TaskState]
    step_index: int
    max_steps: int
    url: str
    system_prompt: Optional[str] = None
    # Optional temperature override (used by ConfidenceGate for multi-sampling)
    temperature: Optional[float] = None


@dataclass
class ModelResponse:
    actions: list[Action]
    usage: TokenUsage
    raw_response: Any = None
    # Stable IDs assigned to each tool call, parallel to actions[]
    tool_call_ids: Optional[list[str]] = None
    thinking: Optional[str] = None


@runtime_checkable
class ModelAdapter(Protocol):
    model_id: str
    provider: str

    # Capabilities — used by ViewportManager and HistoryManager
    patch_size: Optional[int]
    max_image_dimension: Optional[int]
    supports_thinking: Optional[bool]
    native_computer_use: bool

    @property
    def context_window_tokens(self) -> int: ...

    async def stream(self, context: StepContext) -> AsyncIterable[Action]: ...
    async def step(self, context: StepContext) -> ModelResponse: ...
    def estimate_tokens(self, context: StepContext) -> int: ...
    async def summarize(
        self,
        wire_history: list[WireMessage],
        agent_state: Optional[TaskState],
    ) -> str: ...


# ─── Coordinate helpers ───────────────────────────────────────────────────────

def denormalize(coord: float, dimension: int) -> int:
    """Model-space (0–1000) → viewport pixels."""
    return round((coord / 1000.0) * dimension)


def normalize(pixel: float, dimension: int) -> int:
    """Viewport pixels → model-space (0–1000)."""
    return round((pixel / float(dimension)) * 1000.0)


def denormalize_point(x: float, y: float, viewport: ViewportSize) -> Point:
    return Point(
        x=denormalize(x, viewport.width),
        y=denormalize(y, viewport.height),
    )