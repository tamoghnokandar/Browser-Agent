"""Tests for adapter utilities (denormalize, normalize). Port of tests/unit/normalize.test.ts."""
import pytest

from model.adapter import denormalize, normalize, denormalize_point
from agent_types import ViewportSize


class TestDenormalize:
    def test_converts_500_to_half_dimension(self):
        assert denormalize(500, 1280) == 640

    def test_converts_0_to_0(self):
        assert denormalize(0, 1000) == 0

    def test_converts_1000_to_full_dimension(self):
        assert denormalize(1000, 720) == 720

    def test_rounds_to_nearest_integer(self):
        assert denormalize(333, 1000) == 333
        assert isinstance(denormalize(1, 3), (int, float))


class TestNormalize:
    def test_converts_half_dimension_to_500(self):
        assert normalize(640, 1280) == 500

    def test_converts_0_to_0(self):
        assert normalize(0, 1000) == 0

    def test_converts_full_dimension_to_1000(self):
        assert normalize(720, 720) == 1000


class TestDenormalizePoint:
    def test_denormalizes_x_and_y_together(self):
        pt = denormalize_point(500, 500, ViewportSize(width=1280, height=720))
        assert pt.x == 640
        assert pt.y == 360
