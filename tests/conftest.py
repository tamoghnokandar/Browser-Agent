"""Pytest configuration and shared fixtures."""
import pytest


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Temporary directory for action cache tests."""
    return str(tmp_path / "browser-agent-cache-test")
