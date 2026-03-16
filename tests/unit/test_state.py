"""Tests for StateStore. Port of tests/unit/state.test.ts."""
import pytest

from loop.state import StateStore


MOCK_STATE = {
    "currentUrl": "https://example.com",
    "completedSteps": ["step1"],
    "nextStep": "step2",
    "data": {"key": "value"},
}


class TestStateStore:
    def test_returns_none_initially(self):
        store = StateStore()
        assert store.current() is None

    def test_returns_written_state(self):
        store = StateStore()
        store.write(MOCK_STATE)
        assert store.current() == MOCK_STATE

    def test_current_returns_copy_immutable(self):
        store = StateStore()
        store.write(MOCK_STATE)
        current = store.current()
        assert current is not None
        current["currentUrl"] = "https://modified.com"
        assert store.current()["currentUrl"] == "https://example.com"

    def test_load_sets_state_from_persisted_value(self):
        store = StateStore()
        store.load(MOCK_STATE)
        assert store.current() == MOCK_STATE

    def test_load_none_clears_state(self):
        store = StateStore()
        store.write(MOCK_STATE)
        store.load(None)
        assert store.current() is None
