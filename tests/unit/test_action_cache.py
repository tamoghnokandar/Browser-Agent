"""Tests for ActionCache. Port of tests/unit/action-cache.test.ts."""
import os
import tempfile
import pytest

from loop.action_cache import ActionCache, screenshot_hash


@pytest.fixture
def cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory(prefix="browser-agent-cache-test-") as d:
        yield d


@pytest.fixture
def cache(cache_dir):
    """ActionCache instance with temp directory."""
    return ActionCache(cache_dir)


class TestActionCache:
    @pytest.mark.asyncio
    async def test_returns_none_for_cache_miss(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_stores_and_retrieves_non_coordinate_action(self, cache):
        action = {"type": "goto", "url": "https://example.com"}
        key = cache.cache_key("goto", "https://example.com", "abc123")
        await cache.set(key, action, "https://example.com", "abc123")

        result = await cache.get(key)
        assert result is not None
        assert result["type"] == "goto"
        assert result["args"] == action

    @pytest.mark.asyncio
    async def test_stores_screenshot_hash_for_coordinate_actions(self, cache):
        action = {"type": "click", "x": 500, "y": 300}
        key = cache.cache_key("click", "https://example.com", "abc123")
        await cache.set(key, action, "https://example.com", "abc123", "screenhash123")

        result = await cache.get(key, "screenhash123")
        assert result is not None
        assert result["screenshotHash"] == "screenhash123"

    @pytest.mark.asyncio
    async def test_returns_none_when_screenshot_hash_doesnt_match(self, cache):
        action = {"type": "click", "x": 500, "y": 300}
        key = cache.cache_key("click", "https://example.com", "abc123")
        await cache.set(key, action, "https://example.com", "abc123", "screenhash_old")

        result = await cache.get(key, "screenhash_new")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_entry_when_screenshot_hash_matches(self, cache):
        action = {"type": "click", "x": 500, "y": 300}
        key = cache.cache_key("click", "https://example.com", "abc123")
        await cache.set(key, action, "https://example.com", "abc123", "same_hash")

        result = await cache.get(key, "same_hash")
        assert result is not None
        assert result["type"] == "click"

    @pytest.mark.asyncio
    async def test_non_coordinate_action_ignores_screenshot_hash(self, cache):
        action = {"type": "type", "text": "hello"}
        key = cache.cache_key("type", "https://example.com", "abc123")
        await cache.set(key, action, "https://example.com", "abc123", "some_hash")

        result = await cache.get(key)
        assert result is not None
        assert result.get("screenshotHash") is None

    def test_generates_deterministic_cache_keys(self, cache):
        key1 = cache.cache_key("click", "https://example.com", "abc123")
        key2 = cache.cache_key("click", "https://example.com", "abc123")
        assert key1 == key2

        key3 = cache.cache_key("click", "https://example.com", "different")
        assert key1 != key3


class TestScreenshotHash:
    def test_produces_deterministic_hash_for_same_data(self):
        data = b"hello world"
        assert screenshot_hash(data) == screenshot_hash(data)

    def test_produces_different_hashes_for_different_data(self):
        assert screenshot_hash(b"a") != screenshot_hash(b"b")
