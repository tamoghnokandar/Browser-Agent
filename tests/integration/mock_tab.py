"""Mock BrowserTab for integration tests. Port of tests/integration/mock-tab.ts."""
from typing import Any, Dict, List, Optional

from agent_types import ScreenshotResult


class MockBrowserTab:
    """Mock BrowserTab that records calls and returns success."""

    def __init__(
        self,
        url: str = "https://example.com",
        viewport: Optional[Dict[str, int]] = None,
        screenshot_data: Optional[bytes] = None,
    ):
        self._url = url
        self._viewport = viewport or {"width": 1280, "height": 720}
        self._screenshot_data = screenshot_data or bytes(100)
        self.calls: List[Dict[str, Any]] = []

    def _record(self, method: str, args: list) -> Dict[str, Any]:
        self.calls.append({"method": method, "args": args})
        return {"ok": True}

    async def screenshot(self, options: Optional[Dict[str, Any]] = None, **kwargs: Any) -> ScreenshotResult:
        self.calls.append({"method": "screenshot", "args": []})
        return ScreenshotResult(
            data=self._screenshot_data,
            width=self._viewport["width"],
            height=self._viewport["height"],
            mime_type="image/png",
        )

    async def click(self, x: float, y: float, button: str = "left", **kwargs) -> Dict[str, Any]:
        return self._record("click", [x, y, {"button": button, **kwargs}])

    async def double_click(self, x: float, y: float) -> Dict[str, Any]:
        return self._record("double_click", [x, y])

    async def hover(self, x: float, y: float) -> Dict[str, Any]:
        return self._record("hover", [x, y])

    async def drag(self, from_x: float, from_y: float, to_x: float, to_y: float, **kwargs) -> Dict[str, Any]:
        return self._record("drag", [from_x, from_y, to_x, to_y])

    async def scroll(self, x: float, y: float, delta_x: float, delta_y: float) -> Dict[str, Any]:
        return self._record("scroll", [x, y, delta_x, delta_y])

    async def type(self, text: str, delay_ms: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        return self._record("type", [text])

    async def key_press(self, keys: Any) -> Dict[str, Any]:
        return self._record("key_press", [keys])

    async def goto(self, url: str) -> None:
        self._record("goto", [url])
        self._url = url

    async def wait_for_load(self, timeout_ms: Optional[int] = None) -> None:
        self._record("wait_for_load", [timeout_ms])

    def url(self) -> str:
        return self._url

    def viewport(self) -> Dict[str, int]:
        return self._viewport.copy()

    async def set_viewport(self, size: Dict[str, int]) -> None:
        self._record("set_viewport", [size])

    async def evaluate(self, script: str) -> Any:
        return None

    async def close(self) -> None:
        pass
