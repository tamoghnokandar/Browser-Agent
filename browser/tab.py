"""
BrowserTab interface. Port of src/browser/tab.ts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence, TypedDict

from .types import ActionOutcome, ScreenshotOptions, ScreenshotResult, ViewportSize


class ClickOptions(TypedDict, total=False):
    button: str
    click_count: int
    delay_ms: int


class DragOptions(TypedDict, total=False):
    steps: int


class TypeOptions(TypedDict, total=False):
    delay_ms: int
    clear_first: bool


class BrowserTab(ABC):
    """The only browser abstraction exposed to the perception loop.

    All coordinate parameters are in viewport pixels (already denormalized).
    """

    @abstractmethod
    async def screenshot(self, options: ScreenshotOptions | None = None) -> ScreenshotResult:
        raise NotImplementedError

    @abstractmethod
    async def click(
        self,
        x: float,
        y: float,
        options: ClickOptions | None = None,
    ) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def double_click(self, x: float, y: float) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def hover(self, x: float, y: float) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def drag(
        self,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        options: DragOptions | None = None,
    ) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def scroll(
        self,
        x: float,
        y: float,
        delta_x: float,
        delta_y: float,
    ) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def type(
        self,
        text: str,
        options: TypeOptions | None = None,
    ) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def key_press(self, key: str | Sequence[str]) -> ActionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def goto(self, url: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_for_load(self, timeout_ms: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def viewport(self) -> ViewportSize:
        raise NotImplementedError

    @abstractmethod
    async def set_viewport(self, size: ViewportSize) -> None:
        raise NotImplementedError

    @abstractmethod
    async def evaluate(self, script: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
