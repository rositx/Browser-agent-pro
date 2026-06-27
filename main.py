"""
Browser-Agent-Pro — Main Entrypoint
======================================
CLI entrypoint for launching the browser agent with a task manifest.

Usage:
    python main.py --manifest manifests/example_manifest.json
    python main.py --manifest manifests/example_manifest.json --profile custom_profile
    python main.py --manifest manifests/example_manifest.json --headless
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agent.core.browser import BrowserRuntime
from agent.core.config import Settings, get_settings
from agent.core.driver import ActionDriver
from agent.core.session import SessionState, TaskManifest, load_session


async def run_agent(
    manifest_path: Path,
    profile_name: str = "default",
    headless: bool | None = None,
) -> None:
    """
    Execute the agent loop for a given task manifest.

    Phase 1 implementation: bootstraps browser, loads manifest, and
    runs a simple navigation test to verify the pipeline works end-to-end.

    Args:
        manifest_path: Path to the task manifest JSON file.
        profile_name: Name of the browser profile directory.
        headless: Override headless mode (None = use .env setting).
    """
    settings = get_settings()

    # Override headless if explicitly requested
    if headless is not None:
        settings = Settings(
            headless=headless,
            profile_dir=settings.profile_dir,
            manifest_dir=settings.manifest_dir,
            log_level=settings.log_level,
            max_steps=settings.max_steps,
            human_delay_base_ms=settings.human_delay_base_ms,
            typing_delay_min_ms=settings.typing_delay_min_ms,
            typing_delay_max_ms=settings.typing_delay_max_ms,
        )

    # Load the task manifest and create session
    print(f"[*] Loading manifest: {manifest_path}")
    session = load_session(manifest_path, settings=settings)
    session.start()

    print(f"[*] Session ID: {session.session_id}")
    print(f"[*] Objective: {session.objective}")
    print(f"[*] Allowed domains: {session.manifest.target_domains}")
    print(f"[*] Max steps: {session.max_steps}")
    print()

    # Launch browser with stealth
    print(f"[*] Launching browser (headless={settings.headless}, profile={profile_name})")

    async with BrowserRuntime(settings=settings, profile_name=profile_name) as runtime:
        print(f"[✓] Browser launched successfully")
        print(f"    Viewport: {runtime.viewport_size}")
        print(f"    User-Agent: {runtime.user_agent[:60]}...")
        print()

        # Create the action driver
        driver = ActionDriver(
            page=runtime.page,
            settings=settings,
            session=session,
        )

        # Phase 1 demo: navigate to first allowed domain
        if session.manifest.target_domains:
            target_url = f"https://{session.manifest.target_domains[0]}"
            print(f"[*] Step 1: Navigating to {target_url}")

            session.increment_step()
            result = await driver.execute(
                {"action": "navigate", "value": target_url}
            )

            if result.success:
                print(f"[✓] {result.message}")
                session.record_action(
                    action={"action": "navigate", "value": target_url},
                    observation=result.message,
                    success=True,
                )
            else:
                print(f"[✗] Navigation failed: {result.message}")
                session.record_action(
                    action={"action": "navigate", "value": target_url},
                    success=False,
                    error=result.message,
                )

            # Wait for visual inspection (if not headless)
            if not settings.headless:
                print()
                print("[*] Browser is open for inspection. Press Ctrl+C to close.")
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    pass

        # Complete session
        session.complete()
        print()
        print(f"[✓] Session completed")
        print(f"    Steps taken: {session.current_step}/{session.max_steps}")
        print(f"    Actions recorded: {len(session.trace)}")

    print("[✓] Browser closed. Goodbye!")


def main() -> None:
    """Parse CLI arguments and launch the agent."""
    parser = argparse.ArgumentParser(
        description="Browser-Agent-Pro — Autonomous Browser Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --manifest manifests/example_manifest.json
  python main.py --manifest manifests/example_manifest.json --profile my_profile
  python main.py --manifest manifests/example_manifest.json --headless
        """,
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the task manifest JSON file",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Browser profile name (default: 'default')",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run browser in headless mode",
    )

    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Error: Manifest file not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        run_agent(
            manifest_path=args.manifest,
            profile_name=args.profile,
            headless=args.headless if args.headless else None,
        )
    )


if __name__ == "__main__":
    main()
