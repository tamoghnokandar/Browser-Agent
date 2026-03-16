"""Tests for ActionDecoder. Port of tests/unit/decoder.test.ts."""
import pytest

from model.decoder import ActionDecoder
from agent_types import ViewportSize


@pytest.fixture
def decoder():
    return ActionDecoder()


@pytest.fixture
def viewport():
    return ViewportSize(width=1280, height=720)

class TestActionDecoderFromGoogle:
    def test_denormalizes_0_1000_coordinates_to_pixels(self, decoder, viewport):
        action = decoder.from_google(
            {"name": "computer_use", "args": {"action": "click", "x": 500, "y": 500, "button": "left"}},
            viewport,
        )
        assert action["type"] == "click"
        assert action["x"] == 640  # 500/1000 * 1280
        assert action["y"] == 360  # 500/1000 * 720

    def test_decodes_navigate_to_goto(self, decoder, viewport):
        action = decoder.from_google(
            {"name": "computer_use", "args": {"action": "navigate", "url": "https://example.com"}},
            viewport,
        )
        assert action["type"] == "goto"
        assert action["url"] == "https://example.com"

    def test_falls_back_to_screenshot_for_unknown_action(self, decoder, viewport):
        action = decoder.from_google(
            {"name": "unknown", "args": {"action": "unknown"}}, 
            viewport,
        )
        assert action["type"] == "screenshot"