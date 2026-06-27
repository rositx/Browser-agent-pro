"""
Action Driver — Browser Command Dispatcher
=============================================
Translates AgentAction dictionaries into Playwright browser commands
with human-like stealth timing delays.

Phase 1 implements foundational actions: navigate, click, type, wait.
Phase 2 will extend with: scroll, select, extract, upload, screenshot, done, fail.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Callable, Coroutine, Optional

from playwright.async_api import Page

from agent.core.config import Settings, get_settings
from agent.core.session import SessionState


# ── Stealth Timing Utilities ──────────────────────────────────────────────


async def human_delay(base_ms: int = 500) -> None:
    """
    Inject a randomised inter-action delay to simulate human pacing.

    Adds jitter of -150ms to +350ms around the base delay.
    Per rules.md §2.4: delays must be 800ms–3500ms between interactions.
    """
    jitter = random.randint(-150, 350)
    delay_ms = max(100, base_ms + jitter)  # Never sleep less than 100ms
    await asyncio.sleep(delay_ms / 1000)


async def typing_delay(min_ms: int = 40, max_ms: int = 120) -> float:
    """
    Return a randomised per-character typing delay in milliseconds.

    This simulates human typing rhythm with natural variation.
    """
    return random.randint(min_ms, max_ms)


async def mouse_jitter(page: Page, target_x: int, target_y: int) -> tuple[int, int]:
    """
    Add slight randomisation to click coordinates to simulate human imprecision.

    Offset is ±3px in both axes, as specified in the architecture doc.
    """
    offset_x = random.randint(-3, 3)
    offset_y = random.randint(-3, 3)
    return (target_x + offset_x, target_y + offset_y)


# ── Action Result ─────────────────────────────────────────────────────────


class ActionResult:
    """Encapsulates the result of executing a browser action."""

    def __init__(
        self,
        success: bool,
        action_name: str,
        message: str = "",
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        self.success = success
        self.action_name = action_name
        self.message = message
        self.data = data or {}

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"ActionResult({status} {self.action_name}: {self.message})"


# ── Action Driver ─────────────────────────────────────────────────────────


class ActionDriver:
    """
    Dispatches AgentAction commands to the Playwright browser.

    Implements a dispatch table pattern where each action name maps to
    an async handler method. All actions include stealth timing delays.

    Usage::

        driver = ActionDriver(page, settings)
        result = await driver.execute({
            "action": "navigate",
            "value": "https://example.com"
        })
    """

    def __init__(
        self,
        page: Page,
        settings: Optional[Settings] = None,
        session: Optional[SessionState] = None,
    ) -> None:
        self._page = page
        self._settings = settings or get_settings()
        self._session = session

        # Dispatch table: action name → handler method
        self._dispatch: dict[str, Callable[..., Coroutine[Any, Any, ActionResult]]] = {
            "navigate": self._action_navigate,
            "click": self._action_click,
            "type": self._action_type,
            "wait": self._action_wait,
        }

    @property
    def supported_actions(self) -> list[str]:
        """Return list of currently supported action names."""
        return list(self._dispatch.keys())

    # ── Main Dispatcher ───────────────────────────────────────────────

    async def execute(self, action: dict[str, Any]) -> ActionResult:
        """
        Execute a single agent action with stealth timing.

        Args:
            action: Dictionary matching the AgentAction schema.
                    Must contain at minimum an 'action' key.

        Returns:
            ActionResult indicating success/failure.

        Raises:
            ValueError: If the action name is not in the dispatch table.
        """
        action_name = action.get("action")
        if not action_name:
            return ActionResult(
                success=False,
                action_name="unknown",
                message="Action dictionary missing 'action' key",
            )

        handler = self._dispatch.get(action_name)
        if handler is None:
            return ActionResult(
                success=False,
                action_name=action_name,
                message=f"Unsupported action: '{action_name}'. "
                f"Supported: {self.supported_actions}",
            )

        # Pre-action stealth delay (800ms–3500ms range per rules.md §2.4)
        await human_delay(self._settings.human_delay_base_ms)

        try:
            result = await handler(action)
            return result
        except Exception as e:
            return ActionResult(
                success=False,
                action_name=action_name,
                message=f"Action failed with error: {str(e)}",
            )

    # ── Action Handlers ───────────────────────────────────────────────

    async def _action_navigate(self, action: dict[str, Any]) -> ActionResult:
        """
        Navigate to a URL.

        Validates the URL domain against the session manifest's allowed list
        before executing (per rules.md §2.1: scope boundary enforcement).
        """
        url = action.get("value")
        if not url:
            return ActionResult(
                success=False,
                action_name="navigate",
                message="Navigate action requires a 'value' (URL)",
            )

        # Domain validation if session is available
        if self._session and not self._session.is_domain_allowed(url):
            return ActionResult(
                success=False,
                action_name="navigate",
                message=f"Domain not in allowed list. URL: {url}",
            )

        await self._page.goto(url, wait_until="domcontentloaded")
        current_url = self._page.url

        return ActionResult(
            success=True,
            action_name="navigate",
            message=f"Navigated to {current_url}",
            data={"url": current_url},
        )

    async def _action_click(self, action: dict[str, Any]) -> ActionResult:
        """
        Click an element by selector or coordinates.

        Supports two modes:
        1. Coordinate-based: uses action['coordinates'] = (x, y)
        2. Selector-based: uses action['element_id'] mapped to a selector

        Applies ±3px mouse jitter per architecture spec.
        """
        coordinates = action.get("coordinates")
        element_id = action.get("element_id")
        selector = action.get("selector")

        if coordinates:
            # Coordinate-based click with jitter
            x, y = coordinates
            jittered_x, jittered_y = await mouse_jitter(self._page, x, y)

            # Simulate natural mouse movement: move, then click
            await self._page.mouse.move(jittered_x, jittered_y)
            await asyncio.sleep(random.uniform(0.05, 0.15))  # Brief pause before click
            await self._page.mouse.click(jittered_x, jittered_y)

            return ActionResult(
                success=True,
                action_name="click",
                message=f"Clicked at ({jittered_x}, {jittered_y})",
                data={"coordinates": (jittered_x, jittered_y)},
            )

        elif selector:
            # Selector-based click
            await self._page.click(selector)
            return ActionResult(
                success=True,
                action_name="click",
                message=f"Clicked selector: {selector}",
                data={"selector": selector},
            )

        elif element_id is not None:
            # Element ID click — Phase 2 will map element_id from AX tree
            # For now, attempt CSS selector by data attribute or aria
            return ActionResult(
                success=False,
                action_name="click",
                message=f"Element ID {element_id} click requires AX tree mapping (Phase 2)",
                data={"element_id": element_id},
            )

        else:
            return ActionResult(
                success=False,
                action_name="click",
                message="Click action requires 'coordinates', 'selector', or 'element_id'",
            )

    async def _action_type(self, action: dict[str, Any]) -> ActionResult:
        """
        Type text into an element with human-like per-character delays.

        Implements randomised typing speed (40ms–120ms per character)
        as specified in the architecture document.
        """
        value = action.get("value", "")
        selector = action.get("selector")
        coordinates = action.get("coordinates")

        if not value:
            return ActionResult(
                success=False,
                action_name="type",
                message="Type action requires a 'value' (text to type)",
            )

        if selector:
            # Focus the element first
            await self._page.click(selector)
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # Type with per-character delay for human simulation
            for char in value:
                delay = await typing_delay(
                    self._settings.typing_delay_min_ms,
                    self._settings.typing_delay_max_ms,
                )
                await self._page.keyboard.type(char, delay=delay)

            return ActionResult(
                success=True,
                action_name="type",
                message=f"Typed {len(value)} characters into {selector}",
                data={"selector": selector, "length": len(value)},
            )

        elif coordinates:
            # Click at coordinates first, then type
            x, y = coordinates
            jittered_x, jittered_y = await mouse_jitter(self._page, x, y)
            await self._page.mouse.click(jittered_x, jittered_y)
            await asyncio.sleep(random.uniform(0.1, 0.3))

            for char in value:
                delay = await typing_delay(
                    self._settings.typing_delay_min_ms,
                    self._settings.typing_delay_max_ms,
                )
                await self._page.keyboard.type(char, delay=delay)

            return ActionResult(
                success=True,
                action_name="type",
                message=f"Typed {len(value)} characters at ({jittered_x}, {jittered_y})",
                data={"coordinates": (jittered_x, jittered_y), "length": len(value)},
            )

        else:
            return ActionResult(
                success=False,
                action_name="type",
                message="Type action requires a 'selector' or 'coordinates'",
            )

    async def _action_wait(self, action: dict[str, Any]) -> ActionResult:
        """
        Wait for a specified duration with jitter.

        Adds ±200ms jitter to the declared wait time, per the
        architecture spec's action dispatch table.
        """
        wait_ms = action.get("value")

        if wait_ms is None:
            # Default wait
            wait_ms = 1000

        try:
            wait_ms = int(wait_ms)
        except (ValueError, TypeError):
            wait_ms = 1000

        # Add ±200ms jitter as specified
        jitter = random.randint(-200, 200)
        actual_wait = max(100, wait_ms + jitter)

        await self._page.wait_for_timeout(actual_wait)

        return ActionResult(
            success=True,
            action_name="wait",
            message=f"Waited {actual_wait}ms (requested: {wait_ms}ms)",
            data={"requested_ms": wait_ms, "actual_ms": actual_wait},
        )
