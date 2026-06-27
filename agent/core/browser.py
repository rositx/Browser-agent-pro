"""
Browser Runtime & Stealth Engine
==================================
Manages Playwright browser lifecycle with persistent profiles and
stealth anti-detection measures.

Key features:
- Persistent browser context (cookies, history carry forward)
- playwright-stealth integration (canvas, WebGL, navigator spoofing)
- Randomised viewport within human-typical ranges
- Timezone and locale spoofing
- Async context manager for clean lifecycle management
"""

from __future__ import annotations

import random
from typing import Optional

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright_stealth import Stealth

from agent.core.config import Settings, get_settings

# Curated list of real-world Chrome User-Agent strings for spoofing.
# These should be periodically updated to match current browser versions.
_CHROME_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


class BrowserRuntime:
    """
    Async context manager for Playwright browser lifecycle.

    Usage::

        async with BrowserRuntime() as runtime:
            page = runtime.page
            await page.goto("https://example.com")
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        profile_name: str = "default",
    ) -> None:
        self._settings = settings or get_settings()
        self._profile_name = profile_name
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Randomise viewport once at init (must not change mid-session per rules)
        self._viewport_width = random.randint(1280, 1920)
        self._viewport_height = int(self._viewport_width * 0.625)  # ~16:10 ratio
        self._user_agent = random.choice(_CHROME_USER_AGENTS)

    # ── Async Context Manager ──────────────────────────────────────────

    async def __aenter__(self) -> BrowserRuntime:
        """Launch browser with persistent profile and stealth."""
        self._playwright = await async_playwright().start()

        profile_path = (
            self._settings.profile_dir / self._profile_name
        )
        profile_path.mkdir(parents=True, exist_ok=True)

        # launch_persistent_context creates a context tied to a user data dir,
        # preserving cookies, localStorage, and browsing history across sessions.
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=self._settings.headless,
            viewport={
                "width": self._viewport_width,
                "height": self._viewport_height,
            },
            locale=self._settings.default_locale,
            timezone_id=self._settings.default_timezone,
            user_agent=self._user_agent,
            # Additional stealth-supporting flags
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Use the first page if one already exists, otherwise create one
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        # Apply stealth patches to mask automation signals
        await Stealth().apply_stealth_async(self._page)

        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Clean shutdown: close context, stop playwright."""
        if self._context:
            await self._context.close()
            self._context = None
            self._page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def context(self) -> BrowserContext:
        """Return the active browser context."""
        if self._context is None:
            raise RuntimeError(
                "BrowserRuntime not initialised. Use 'async with BrowserRuntime() as rt:'"
            )
        return self._context

    @property
    def page(self) -> Page:
        """Return the active page."""
        if self._page is None:
            raise RuntimeError(
                "BrowserRuntime not initialised. Use 'async with BrowserRuntime() as rt:'"
            )
        return self._page

    @property
    def viewport_size(self) -> dict[str, int]:
        """Return the randomised viewport dimensions."""
        return {"width": self._viewport_width, "height": self._viewport_height}

    @property
    def user_agent(self) -> str:
        """Return the spoofed user-agent string."""
        return self._user_agent

    # ── Page Management ────────────────────────────────────────────────

    async def new_page(self) -> Page:
        """
        Create a new page in the persistent context and apply stealth.

        Returns the new page. The runtime's active page is updated.
        """
        if self._context is None:
            raise RuntimeError("BrowserRuntime not initialised.")

        page = await self._context.new_page()
        await Stealth().apply_stealth_async(page)
        self._page = page
        return page

    async def close_page(self, page: Page) -> None:
        """Close a specific page. Switch active page to the last remaining."""
        await page.close()
        remaining = self._context.pages if self._context else []
        self._page = remaining[-1] if remaining else None
