"""Perception cache tests (stepKey, viewportMismatch). Port of perception-cache.test.ts."""
import tempfile
import pytest

from loop.action_cache import ActionCache, viewport_mismatch


class TestActionCacheStepKey:
    @pytest.fixture
    def cache(self):
        with tempfile.TemporaryDirectory() as d:
            yield ActionCache(d)

    def test_produces_deterministic_keys(self, cache):
        key1 = cache.step_key("https://example.com", "abc123")
        key2 = cache.step_key("https://example.com", "abc123")
        assert key1 == key2
        assert len(key1) == 16

    def test_differs_when_url_differs(self, cache):
        key1 = cache.step_key("https://a.com", "abc123")
        key2 = cache.step_key("https://b.com", "abc123")
        assert key1 != key2

    def test_differs_when_instruction_hash_differs(self, cache):
        key1 = cache.step_key("https://example.com", "hash1")
        key2 = cache.step_key("https://example.com", "hash2")
        assert key1 != key2

    def test_does_not_include_action_type_unlike_cache_key(self, cache):
        step_key = cache.step_key("https://example.com", "abc123")
        cache_key = cache.cache_key("click", "https://example.com", "abc123")
        assert step_key != cache_key


class TestViewportMismatch:
    def test_returns_false_when_cached_has_no_viewport(self):
        cached = {
            "version": 1,
            "type": "click",
            "url": "",
            "instructionHash": "",
            "args": {},
        }
        assert viewport_mismatch(cached, {"width": 1280, "height": 720}) is False

    def test_returns_false_when_viewports_match(self):
        cached = {
            "version": 1,
            "type": "click",
            "url": "",
            "instructionHash": "",
            "viewport": {"width": 1280, "height": 720},
            "args": {},
        }
        assert viewport_mismatch(cached, {"width": 1280, "height": 720}) is False

    def test_returns_true_when_width_differs(self):
        cached = {
            "version": 1,
            "type": "click",
            "url": "",
            "instructionHash": "",
            "viewport": {"width": 1280, "height": 720},
            "args": {},
        }
        assert viewport_mismatch(cached, {"width": 1920, "height": 720}) is True

    def test_returns_true_when_height_differs(self):
        cached = {
            "version": 1,
            "type": "click",
            "url": "",
            "instructionHash": "",
            "viewport": {"width": 1280, "height": 720},
            "args": {},
        }
        assert viewport_mismatch(cached, {"width": 1280, "height": 1080}) is True


class TestActionCacheWithViewport:
    @pytest.fixture
    def cache_dir(self):
        with tempfile.TemporaryDirectory(prefix="browser-agent-cache-test-") as d:
            yield d

    @pytest.fixture
    def cache(self, cache_dir):
        return ActionCache(cache_dir)

    @pytest.mark.asyncio
    async def test_stores_and_retrieves_viewport_in_cache_entry(self, cache):
        action = {"type": "click", "x": 100, "y": 200}
        key = cache.step_key("https://example.com", "abc")
        await cache.set(
            key, action, "https://example.com", "abc",
            current_screenshot_hash=None,
            viewport={"width": 1280, "height": 720},
        )
        result = await cache.get(key)
        assert result is not None
        assert result["viewport"] == {"width": 1280, "height": 720}

    @pytest.mark.asyncio
    async def test_retrieves_entry_without_viewport_backward_compat(self, cache):
        action = {"type": "goto", "url": "https://example.com"}
        key = cache.step_key("https://example.com", "abc")
        await cache.set(key, action, "https://example.com", "abc")
        result = await cache.get(key)
        assert result is not None
        assert result.get("viewport") is None

    @pytest.mark.asyncio
    async def test_step_key_cache_hit_works_without_screenshot_hash_validation(self, cache):
        action = {"type": "click", "x": 100, "y": 200}
        key = cache.step_key("https://example.com", "abc")
        await cache.set(
            key, action, "https://example.com", "abc",
            current_screenshot_hash="hash_at_record_time",
            viewport={"width": 1280, "height": 720},
        )
        result = await cache.get(key)
        assert result is not None
        assert result["type"] == "click"
