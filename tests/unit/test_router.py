"""Tests for ActionRouter. Port of tests/unit/router.test.ts."""
from unittest.mock import AsyncMock, MagicMock
import pytest

from loop.router import ActionRouter, RouterTiming
from loop.state import StateStore


def make_mock_tab():
    """Create a mock BrowserTab for testing."""
    tab = MagicMock()
    tab.click = AsyncMock(return_value={"ok": True})
    tab.double_click = AsyncMock(return_value={"ok": True})
    tab.hover = AsyncMock(return_value={"ok": True})
    tab.drag = AsyncMock(return_value={"ok": True})
    tab.scroll = AsyncMock(return_value={"ok": True})
    tab.type = AsyncMock(return_value={"ok": True})
    tab.key_press = AsyncMock(return_value={"ok": True})
    tab.goto = AsyncMock(return_value=None)
    tab.wait_for_load = AsyncMock(return_value=None)
    tab.url = MagicMock(return_value="https://example.com")
    tab.viewport = MagicMock(return_value={"width": 1280, "height": 720})
    tab.set_viewport = AsyncMock(return_value=None)
    tab.evaluate = AsyncMock(return_value=None)
    tab.close = AsyncMock(return_value=None)
    return tab


class TestActionRouter:
    @pytest.mark.asyncio
    async def test_click_passes_pixel_coords_directly_to_browser(self):
        tab = make_mock_tab()
        router = ActionRouter(RouterTiming(after_click=0))
        state = StateStore()
        await router.execute({"type": "click", "x": 640, "y": 360}, tab, state)
        tab.click.assert_called_once_with(640, 360, {"button": "left"})

    @pytest.mark.asyncio
    async def test_scroll_direction_down_maps_to_positive_delta_y(self):
        tab = make_mock_tab()
        router = ActionRouter(RouterTiming(after_scroll=0))
        state = StateStore()
        await router.execute(
            {"type": "scroll", "x": 640, "y": 360, "direction": "down", "amount": 3},
            tab,
            state,
        )
        call_args = tab.scroll.call_args[0]
        delta_x, delta_y = call_args[2], call_args[3]
        assert delta_x == 0
        assert delta_y > 0

    @pytest.mark.asyncio
    async def test_scroll_direction_up_maps_to_negative_delta_y(self):
        tab = make_mock_tab()
        router = ActionRouter(RouterTiming(after_scroll=0))
        state = StateStore()
        await router.execute(
            {"type": "scroll", "x": 640, "y": 360, "direction": "up", "amount": 3},
            tab,
            state,
        )
        call_args = tab.scroll.call_args[0]
        delta_y = call_args[3]
        assert delta_y < 0

    @pytest.mark.asyncio
    async def test_write_state_calls_state_write(self):
        tab = make_mock_tab()
        router = ActionRouter()
        local_state = StateStore()
        await router.execute(
            {"type": "writeState", "data": {"min_price": "£3.49"}},
            tab,
            local_state,
        )
        assert local_state.current() == {"min_price": "£3.49"}

    @pytest.mark.asyncio
    async def test_terminate_returns_terminated_true(self):
        tab = make_mock_tab()
        router = ActionRouter()
        state = StateStore()
        result = await router.execute(
            {"type": "terminate", "status": "success", "result": "done"},
            tab,
            state,
        )
        assert result.terminated is True
        assert result.status == "success"
        assert result.result == "done"

    @pytest.mark.asyncio
    async def test_hover_passes_pixel_coords_directly(self):
        tab = make_mock_tab()
        router = ActionRouter(RouterTiming(after_click=0))
        state = StateStore()
        await router.execute({"type": "hover", "x": 640, "y": 360}, tab, state)
        tab.hover.assert_called_once_with(640, 360)

    @pytest.mark.asyncio
    async def test_delegate_returns_is_delegate_request_true(self):
        tab = make_mock_tab()
        router = ActionRouter()
        state = StateStore()
        result = await router.execute(
            {"type": "delegate", "instruction": "do something", "max_steps": 5},
            tab,
            state,
        )
        assert result.is_delegate_request is True
        assert result.delegate_instruction == "do something"
        assert result.delegate_max_steps == 5

    @pytest.mark.asyncio
    async def test_screenshot_returns_is_screenshot_request_true(self):
        tab = make_mock_tab()
        router = ActionRouter()
        state = StateStore()
        result = await router.execute({"type": "screenshot"}, tab, state)
        assert result.is_screenshot_request is True
