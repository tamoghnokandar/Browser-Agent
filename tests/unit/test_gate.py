"""Tests for Verification Gates. Port of tests/unit/gate.test.ts."""
import re

import pytest

from loop.verifier import CustomGate, UrlMatchesGate

# Mocking the ScreenshotResult type
MOCK_SCREENSHOT = {
    "data": b"",
    "width": 1280,
    "height": 720,
    "mimeType": "image/png",
}

class TestUrlMatchesGate:
    @pytest.mark.asyncio
    async def test_passes_when_url_matches_pattern(self):
        # Using Python's re.compile for regex matching
        gate = UrlMatchesGate(re.compile(r"example\.com/success"))
        result = await gate.verify(MOCK_SCREENSHOT, "https://example.com/success")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_fails_when_url_does_not_match_pattern(self):
        gate = UrlMatchesGate(re.compile(r"example\.com/success"))
        result = await gate.verify(MOCK_SCREENSHOT, "https://example.com/other")
        assert result.passed is False
        assert "does not match" in result.reason

class TestCustomGate:
    @pytest.mark.asyncio
    async def test_passes_when_predicate_returns_true(self):
        async def predicate(screenshot, url):
            return True
            
        gate = CustomGate(predicate)
        result = await gate.verify(MOCK_SCREENSHOT, "https://example.com")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_fails_when_predicate_returns_false(self):
        async def predicate(screenshot, url):
            return False
            
        gate = CustomGate(predicate, "custom failure reason")
        result = await gate.verify(MOCK_SCREENSHOT, "https://example.com")
        assert result.passed is False
        assert result.reason == "custom failure reason"

    @pytest.mark.asyncio
    async def test_receives_screenshot_and_url_in_predicate(self):
        captured_url = {"url": ""}
        
        async def predicate(screenshot, url):
            captured_url["url"] = url
            return True
            
        gate = CustomGate(predicate)
        await gate.verify(MOCK_SCREENSHOT, "https://test.com/page")
        assert captured_url["url"] == "https://test.com/page"