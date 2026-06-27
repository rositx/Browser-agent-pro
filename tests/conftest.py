"""
Pytest Configuration & Shared Fixtures
=========================================
Provides reusable fixtures for Browser-Agent-Pro test suite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Ensure tests use a clean environment
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("HEADLESS", "true")
os.environ.setdefault("PROFILE_DIR", "./test_profiles")
os.environ.setdefault("MANIFEST_DIR", "./test_manifests")


# ── Path Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for test data."""
    return tmp_path


# ── Manifest Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def sample_manifest_data() -> dict:
    """Return a sample manifest dictionary for testing."""
    return {
        "session_id": "test_sess_001",
        "objective": "Test navigation and stealth verification",
        "target_domains": ["example.com", "httpbin.org"],
        "max_steps": 10,
        "human_review_required": ["submit_application"],
        "credentials_ref": None,
        "output_schema": None,
    }


@pytest.fixture
def sample_manifest_file(tmp_path: Path, sample_manifest_data: dict) -> Path:
    """Create a temporary manifest JSON file and return its path."""
    manifest_path = tmp_path / "test_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(sample_manifest_data, f, indent=2)
    return manifest_path


# ── Settings Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def test_settings():
    """Create a Settings instance configured for testing."""
    from agent.core.config import Settings

    return Settings(
        headless=True,
        profile_dir=Path("./test_profiles"),
        manifest_dir=Path("./test_manifests"),
        log_level="DEBUG",
        max_steps=10,
        human_delay_base_ms=50,  # Faster delays for tests
        typing_delay_min_ms=5,
        typing_delay_max_ms=10,
    )


# ── Cleanup ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def cleanup_test_dirs():
    """Clean up test directories after each test."""
    yield
    # Cleanup test profile directories if they were created
    import shutil

    for dir_name in ("test_profiles", "test_manifests"):
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
