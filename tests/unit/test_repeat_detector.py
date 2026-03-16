"""Tests for RepeatDetector and nudge_message. Port of tests/unit/repeat-detector.test.ts."""
import pytest

from loop.repeat_detector import RepeatDetector, nudge_message


class TestRepeatDetector:
    def test_returns_none_when_no_repeats(self):
        detector = RepeatDetector()
        result = detector.record({"type": "click", "x": 100, "y": 200})
        assert result is None

    def test_returns_5_after_5_identical_actions(self):
        detector = RepeatDetector()
        action = {"type": "click", "x": 100, "y": 200}
        for _ in range(4):
            assert detector.record(action) is None
        assert detector.record(action) == 5

    def test_returns_8_after_8_identical_actions(self):
        detector = RepeatDetector()
        action = {"type": "type", "text": "hello"}
        for _ in range(7):
            detector.record(action)
        assert detector.record(action) == 8

    def test_returns_12_after_12_identical_actions(self):
        detector = RepeatDetector()
        action = {"type": "goto", "url": "https://example.com"}
        for _ in range(11):
            detector.record(action)
        assert detector.record(action) == 12

    def test_buckets_nearby_clicks_as_same_action(self):
        detector = RepeatDetector()
        for i in range(4):
            detector.record({"type": "click", "x": 640 + i, "y": 360 + i})
        assert detector.record({"type": "click", "x": 650, "y": 370}) == 5

    def test_respects_rolling_window_of_20(self):
        detector = RepeatDetector()
        for _ in range(4):
            detector.record({"type": "click", "x": 100, "y": 200})
        for i in range(20):
            detector.record({"type": "goto", "url": f"https://example.com/page-{i}"})
        result = detector.record({"type": "click", "x": 100, "y": 200})
        assert result is None

    def test_reset_clears_window(self):
        detector = RepeatDetector()
        for _ in range(4):
            detector.record({"type": "click", "x": 100, "y": 200})
        detector.reset()
        assert detector.record({"type": "click", "x": 100, "y": 200}) is None

    def test_normalizes_key_press_by_joined_keys(self):
        detector = RepeatDetector()
        for _ in range(4):
            detector.record({"type": "keyPress", "keys": ["Enter"]})
        assert detector.record({"type": "keyPress", "keys": ["Enter"]}) == 5


class TestRepeatDetectorCategoryDetection:
    def test_detects_interleaved_scroll_noop_as_stuck(self):
        detector = RepeatDetector()
        for i in range(4):
            detector.record(
                {
                    "type": "scroll",
                    "x": 500,
                    "y": 500,
                    "direction": "down",
                    "amount": 100 + i * 10,
                }
            )
            detector.record({"type": "screenshot"})
        result = detector.record(
            {
                "type": "scroll",
                "x": 500,
                "y": 500,
                "direction": "down",
                "amount": 200,
            }
        )
        assert result == 5

    def test_does_not_trigger_on_productive_actions(self):
        detector = RepeatDetector()
        detector.record({"type": "click", "x": 100, "y": 200})
        detector.record({"type": "click", "x": 200, "y": 300})
        detector.record({"type": "click", "x": 300, "y": 400})
        detector.record({"type": "click", "x": 400, "y": 500})
        result = detector.record({"type": "goto", "url": "https://example.com"})
        assert result is None

    def test_detects_pure_noop_runs(self):
        detector = RepeatDetector()
        for _ in range(4):
            detector.record({"type": "screenshot"})
        assert detector.record({"type": "screenshot"}) == 5


class TestRepeatDetectorUrlStall:
    def test_returns_none_when_url_changes(self):
        detector = RepeatDetector()
        assert detector.record_url("https://a.com") is None
        assert detector.record_url("https://b.com") is None
        assert detector.record_url("https://c.com") is None

    def test_triggers_at_url_stall_threshold_default_10(self):
        detector = RepeatDetector()
        detector.record_url("https://example.com")
        for _ in range(9):
            assert detector.record_url("https://example.com") is None
        assert detector.record_url("https://example.com") == 5

    def test_triggers_at_custom_url_stall_threshold(self):
        detector = RepeatDetector(5)
        detector.record_url("https://example.com")
        for _ in range(4):
            assert detector.record_url("https://example.com") is None
        assert detector.record_url("https://example.com") == 5

    def test_escalates_at_1_5x_and_2x_threshold(self):
        detector = RepeatDetector(4)
        detector.record_url("https://example.com")
        for _ in range(3):
            detector.record_url("https://example.com")
        assert detector.record_url("https://example.com") == 5
        assert detector.record_url("https://example.com") is None
        assert detector.record_url("https://example.com") == 8
        assert detector.record_url("https://example.com") is None
        assert detector.record_url("https://example.com") == 12

    def test_resets_counter_when_url_changes(self):
        detector = RepeatDetector(3)
        detector.record_url("https://a.com")
        detector.record_url("https://a.com")
        detector.record_url("https://a.com")
        detector.record_url("https://b.com")
        assert detector.record_url("https://b.com") is None
        assert detector.record_url("https://b.com") is None
        assert detector.record_url("https://b.com") == 5

    def test_reset_clears_url_tracking(self):
        detector = RepeatDetector(3)
        detector.record_url("https://example.com")
        detector.record_url("https://example.com")
        detector.reset()
        assert detector.record_url("https://example.com") is None

    def test_normalizes_urls_ignores_query_params(self):
        detector = RepeatDetector(3)
        detector.record_url("https://www.booking.com/index.html?sid=abc&srpvid=111")
        detector.record_url("https://www.booking.com/index.html?sid=def&srpvid=222")
        detector.record_url("https://www.booking.com/index.html?sid=ghi&srpvid=333")
        assert (
            detector.record_url(
                "https://www.booking.com/index.html?sid=jkl&srpvid=444"
            )
            == 5
        )

    def test_treats_different_pathnames_as_different_urls(self):
        detector = RepeatDetector(3)
        detector.record_url("https://example.com/page-a?q=1")
        detector.record_url("https://example.com/page-b?q=2")
        detector.record_url("https://example.com/page-c?q=3")
        assert (
            detector.record_url("https://example.com/page-d?q=4") is None
        )


class TestNudgeMessage:
    def test_returns_mild_nudge_at_level_5(self):
        msg = nudge_message(5)
        assert "repeating" in msg

    def test_returns_medium_nudge_at_level_8(self):
        msg = nudge_message(8)
        assert "different approach" in msg

    def test_returns_strong_nudge_at_level_12(self):
        msg = nudge_message(12)
        assert "STRATEGY RESET" in msg

    def test_returns_url_specific_nudge_with_context(self):
        msg5 = nudge_message(5, "url")
        assert "page for a while" in msg5 or "page" in msg5

        msg8 = nudge_message(8, "url")
        assert "same page" in msg8 or "many steps" in msg8

        msg12 = nudge_message(12, "url")
        assert "STRATEGY RESET" in msg12
        assert "update_state" in msg12 or "RIGHT NOW" in msg12
