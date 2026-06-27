"""
Phase 1 Test Suite — Browser Runtime & Session Verification
=============================================================
Tests for:
- Configuration loading and validation
- Session manifest parsing and state management
- Browser runtime initialization (headless mode)
- Stealth parameter verification
- Action driver foundational operations
- Profile persistence across restarts
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agent.core.config import Settings
from agent.core.session import SessionState, TaskManifest, TraceEntry


# =============================================================================
# Configuration Tests
# =============================================================================


class TestSettings:
    """Test configuration loading and validation."""

    def test_default_settings(self, test_settings: Settings):
        """Settings should load with valid defaults."""
        assert test_settings.headless is True
        assert test_settings.log_level == "DEBUG"
        assert test_settings.max_steps == 10
        assert test_settings.typing_delay_min_ms >= 0
        assert test_settings.typing_delay_max_ms >= test_settings.typing_delay_min_ms

    def test_viewport_dimensions_in_range(self, test_settings: Settings):
        """Viewport dimensions must be within allowed ranges."""
        assert 800 <= test_settings.default_viewport_width <= 3840
        assert 600 <= test_settings.default_viewport_height <= 2160

    def test_invalid_log_level_raises(self):
        """Invalid log level should raise a validation error."""
        with pytest.raises(Exception):
            Settings(log_level="INVALID")

    def test_invalid_viewport_width_raises(self):
        """Viewport width out of range should raise validation error."""
        with pytest.raises(Exception):
            Settings(default_viewport_width=100)

    def test_invalid_viewport_height_raises(self):
        """Viewport height out of range should raise validation error."""
        with pytest.raises(Exception):
            Settings(default_viewport_height=100)

    def test_negative_typing_delay_raises(self):
        """Negative typing delay should raise validation error."""
        with pytest.raises(Exception):
            Settings(typing_delay_min_ms=-10)

    def test_zero_max_steps_raises(self):
        """Zero max_steps should raise validation error."""
        with pytest.raises(Exception):
            Settings(max_steps=0)


# =============================================================================
# Task Manifest Tests
# =============================================================================


class TestTaskManifest:
    """Test manifest parsing and validation."""

    def test_from_dict_valid(self, sample_manifest_data: dict):
        """Valid manifest data should parse successfully."""
        manifest = TaskManifest.from_dict(sample_manifest_data)
        assert manifest.session_id == "test_sess_001"
        assert manifest.objective == "Test navigation and stealth verification"
        assert "example.com" in manifest.target_domains
        assert manifest.max_steps == 10
        assert "submit_application" in manifest.human_review_required

    def test_from_file(self, sample_manifest_file: Path):
        """Manifest should load correctly from a JSON file."""
        manifest = TaskManifest.from_file(sample_manifest_file)
        assert manifest.session_id == "test_sess_001"
        assert len(manifest.target_domains) == 2

    def test_missing_required_fields_raises(self):
        """Missing required fields should raise ValueError."""
        with pytest.raises(ValueError, match="missing required fields"):
            TaskManifest.from_dict({"session_id": "test"})

    def test_empty_target_domains_raises(self):
        """Empty target_domains list should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty list"):
            TaskManifest.from_dict(
                {
                    "session_id": "test",
                    "objective": "test",
                    "target_domains": [],
                }
            )

    def test_defaults_applied(self):
        """Omitted optional fields should use defaults."""
        manifest = TaskManifest.from_dict(
            {
                "session_id": "test",
                "objective": "test",
                "target_domains": ["example.com"],
            }
        )
        assert manifest.max_steps == 60
        assert manifest.human_review_required == []
        assert manifest.credentials_ref is None


# =============================================================================
# Session State Tests
# =============================================================================


class TestSessionState:
    """Test session lifecycle and state management."""

    @pytest.fixture
    def session(self, sample_manifest_data: dict) -> SessionState:
        """Create a test session."""
        manifest = TaskManifest.from_dict(sample_manifest_data)
        return SessionState(manifest)

    def test_initial_state(self, session: SessionState):
        """Session should start in 'initialising' state at step 0."""
        assert session.status == "initialising"
        assert session.current_step == 0
        assert len(session.trace) == 0

    def test_start_transitions_to_running(self, session: SessionState):
        """Calling start() should transition to 'running' state."""
        session.start()
        assert session.status == "running"

    def test_step_increment(self, session: SessionState):
        """Each increment should advance the step counter by 1."""
        session.start()
        assert session.increment_step() == 1
        assert session.increment_step() == 2
        assert session.current_step == 2

    def test_step_limit_enforcement(self, session: SessionState):
        """Exceeding max_steps should raise RuntimeError."""
        session.start()
        for _ in range(session.max_steps):
            session.increment_step()

        with pytest.raises(RuntimeError, match="Step limit reached"):
            session.increment_step()

    def test_record_action(self, session: SessionState):
        """Actions should be recorded in the trace history."""
        session.start()
        session.increment_step()
        entry = session.record_action(
            action={"action": "navigate", "value": "https://example.com"},
            observation="Page loaded successfully",
        )
        assert entry.step == 1
        assert entry.success is True
        assert len(session.trace) == 1

    def test_record_failed_action(self, session: SessionState):
        """Failed actions should be recorded with error details."""
        session.start()
        session.increment_step()
        entry = session.record_action(
            action={"action": "click", "selector": "#submit"},
            success=False,
            error="Element not found",
        )
        assert entry.success is False
        assert entry.error == "Element not found"

    def test_domain_validation_allowed(self, session: SessionState):
        """Allowed domains should pass validation."""
        assert session.is_domain_allowed("https://example.com/page") is True
        assert session.is_domain_allowed("https://httpbin.org/get") is True

    def test_domain_validation_subdomain(self, session: SessionState):
        """Subdomains of allowed domains should pass validation."""
        assert session.is_domain_allowed("https://careers.example.com/apply") is True
        assert session.is_domain_allowed("https://sub.httpbin.org/get") is True

    def test_domain_validation_blocked(self, session: SessionState):
        """Non-allowed domains should fail validation."""
        assert session.is_domain_allowed("https://malicious-site.com") is False
        assert session.is_domain_allowed("https://notexample.com") is False

    def test_human_review_check(self, session: SessionState):
        """Actions in human_review_required should be flagged."""
        assert session.requires_human_review("submit_application") is True
        assert session.requires_human_review("click") is False

    def test_pause_and_resume(self, session: SessionState):
        """Session should support pause and resume transitions."""
        session.start()
        session.pause()
        assert session.status == "paused"
        session.resume()
        assert session.status == "running"

    def test_resume_from_non_paused_raises(self, session: SessionState):
        """Resuming from non-paused state should raise RuntimeError."""
        session.start()
        with pytest.raises(RuntimeError, match="Cannot resume"):
            session.resume()

    def test_complete_session(self, session: SessionState):
        """Completing a session should set status to 'completed'."""
        session.start()
        session.complete()
        assert session.status == "completed"

    def test_fail_session(self, session: SessionState):
        """Failing a session should set status and record a trace entry."""
        session.start()
        session.fail("Critical error occurred")
        assert session.status == "failed"
        assert len(session.trace) == 1
        assert session.trace[0].error == "Critical error occurred"

    def test_session_summary(self, session: SessionState):
        """Summary should contain all key session information."""
        session.start()
        summary = session.to_summary()
        assert summary["session_id"] == "test_sess_001"
        assert summary["status"] == "running"
        assert summary["current_step"] == 0
        assert summary["max_steps"] == 10


# =============================================================================
# Trace Entry Tests
# =============================================================================


class TestTraceEntry:
    """Test trace entry serialisation."""

    def test_to_dict(self):
        """TraceEntry should serialise to a clean dictionary."""
        entry = TraceEntry(
            step=1,
            timestamp="2025-01-01T00:00:00Z",
            action={"action": "click", "selector": "#btn"},
            observation="Button clicked",
            success=True,
        )
        d = entry.to_dict()
        assert d["step"] == 1
        assert d["action"]["action"] == "click"
        assert d["success"] is True
        assert d["error"] is None


# =============================================================================
# Browser Runtime Tests (Structural — no actual browser launch)
# =============================================================================


class TestBrowserRuntimeStructure:
    """Test BrowserRuntime class structure without launching a browser."""

    def test_import(self):
        """BrowserRuntime should be importable."""
        from agent.core.browser import BrowserRuntime

        assert BrowserRuntime is not None

    def test_init_randomisation(self, test_settings: Settings):
        """BrowserRuntime should randomise viewport on init."""
        from agent.core.browser import BrowserRuntime

        rt = BrowserRuntime(settings=test_settings, profile_name="test")
        vp = rt.viewport_size
        assert 1280 <= vp["width"] <= 1920
        # Height is ~62.5% of width (16:10 ratio)
        expected_height = int(vp["width"] * 0.625)
        assert vp["height"] == expected_height

    def test_user_agent_is_realistic(self, test_settings: Settings):
        """BrowserRuntime should select a realistic user agent string."""
        from agent.core.browser import BrowserRuntime

        rt = BrowserRuntime(settings=test_settings, profile_name="test")
        ua = rt.user_agent
        assert "Mozilla" in ua
        assert "Chrome" in ua

    def test_page_property_before_init_raises(self, test_settings: Settings):
        """Accessing page before __aenter__ should raise RuntimeError."""
        from agent.core.browser import BrowserRuntime

        rt = BrowserRuntime(settings=test_settings)
        with pytest.raises(RuntimeError, match="not initialised"):
            _ = rt.page

    def test_context_property_before_init_raises(self, test_settings: Settings):
        """Accessing context before __aenter__ should raise RuntimeError."""
        from agent.core.browser import BrowserRuntime

        rt = BrowserRuntime(settings=test_settings)
        with pytest.raises(RuntimeError, match="not initialised"):
            _ = rt.context


# =============================================================================
# Action Driver Tests (Unit — mocked page)
# =============================================================================


class TestActionDriver:
    """Test ActionDriver with mocked Playwright page."""

    @pytest.fixture
    def mock_page(self) -> MagicMock:
        """Create a mock Playwright page object."""
        page = MagicMock()
        page.goto = AsyncMock(return_value=None)
        page.click = AsyncMock(return_value=None)
        page.type = AsyncMock(return_value=None)
        page.wait_for_timeout = AsyncMock(return_value=None)
        page.url = "https://example.com"

        # Mock mouse
        page.mouse = MagicMock()
        page.mouse.move = AsyncMock(return_value=None)
        page.mouse.click = AsyncMock(return_value=None)

        # Mock keyboard
        page.keyboard = MagicMock()
        page.keyboard.type = AsyncMock(return_value=None)

        return page

    @pytest.fixture
    def driver(self, mock_page: MagicMock, test_settings: Settings) -> "ActionDriver":
        """Create an ActionDriver with mocked dependencies."""
        from agent.core.driver import ActionDriver

        return ActionDriver(page=mock_page, settings=test_settings)

    def test_supported_actions(self, driver):
        """Driver should support navigate, click, type, wait."""
        supported = driver.supported_actions
        assert "navigate" in supported
        assert "click" in supported
        assert "type" in supported
        assert "wait" in supported

    @pytest.mark.asyncio
    async def test_navigate(self, driver, mock_page):
        """Navigate action should call page.goto."""
        result = await driver.execute({"action": "navigate", "value": "https://example.com"})
        assert result.success is True
        assert result.action_name == "navigate"
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_missing_url(self, driver):
        """Navigate without URL should fail."""
        result = await driver.execute({"action": "navigate"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_click_by_coordinates(self, driver, mock_page):
        """Click with coordinates should use mouse.click."""
        result = await driver.execute(
            {"action": "click", "coordinates": (100, 200)}
        )
        assert result.success is True
        mock_page.mouse.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_by_selector(self, driver, mock_page):
        """Click with selector should use page.click."""
        result = await driver.execute(
            {"action": "click", "selector": "#submit-btn"}
        )
        assert result.success is True
        mock_page.click.assert_called_once_with("#submit-btn")

    @pytest.mark.asyncio
    async def test_type_with_selector(self, driver, mock_page):
        """Type action should type per-character into the selector."""
        result = await driver.execute(
            {"action": "type", "selector": "#email", "value": "test@example.com"}
        )
        assert result.success is True
        # Should have typed each character individually
        assert mock_page.keyboard.type.call_count == len("test@example.com")

    @pytest.mark.asyncio
    async def test_type_missing_value(self, driver):
        """Type without value should fail."""
        result = await driver.execute({"action": "type", "selector": "#email"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_wait_action(self, driver, mock_page):
        """Wait action should call page.wait_for_timeout."""
        result = await driver.execute({"action": "wait", "value": 1000})
        assert result.success is True
        mock_page.wait_for_timeout.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_action(self, driver):
        """Unknown action should return failure."""
        result = await driver.execute({"action": "unknown_action"})
        assert result.success is False
        assert "Unsupported" in result.message

    @pytest.mark.asyncio
    async def test_missing_action_key(self, driver):
        """Missing 'action' key should return failure."""
        result = await driver.execute({"value": "test"})
        assert result.success is False


# =============================================================================
# Integration Test — Domain Enforcement in Driver
# =============================================================================


class TestDriverDomainEnforcement:
    """Test that ActionDriver enforces domain restrictions from session."""

    @pytest.mark.asyncio
    async def test_navigate_blocked_domain(self, test_settings: Settings):
        """Navigation to non-allowed domain should be blocked."""
        from agent.core.driver import ActionDriver
        from agent.core.session import SessionState, TaskManifest

        manifest = TaskManifest.from_dict(
            {
                "session_id": "test",
                "objective": "test",
                "target_domains": ["example.com"],
            }
        )
        session = SessionState(manifest)

        mock_page = MagicMock()
        mock_page.goto = AsyncMock()

        driver = ActionDriver(page=mock_page, settings=test_settings, session=session)
        result = await driver.execute(
            {"action": "navigate", "value": "https://malicious-site.com/phish"}
        )

        assert result.success is False
        assert "not in allowed list" in result.message
        mock_page.goto.assert_not_called()
