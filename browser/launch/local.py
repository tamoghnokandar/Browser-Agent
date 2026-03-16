"""
Launch local Chrome via Playwright. Port of src/browser/launch/local.ts.
Uses [Playwright for Python](https://github.com/microsoft/playwright-python) for reliable
browser launch and CDP access.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from browser.cdptab import CDPTab
from .playwright_adapter import PlaywrightSessionAdapter


async def launch_chrome(opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Launch Chromium via Playwright and return a CDP-compatible tab + cleanup.
    Returns { tab, cleanup, conn: None } to match the agent's expected shape.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "Playwright not installed. Run: uv add playwright && playwright install chromium"
        )

    opts = opts or {}
    headless = opts.get("headless", True) is not False

    # Stealth user agent (bypasses bot flows)
    stealth_user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )

    pw = await async_playwright().start()
    try:
        args = [
            "--disable-blink-features=AutomationControlled",
            f"--user-agent={stealth_user_agent}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--mute-audio",
            "--disable-audio-output",
            "--disable-audio-input",
        ]
        # Required for Chromium in Docker/Cloud Run
        if headless:
            args.append("--no-sandbox")
        browser = await pw.chromium.launch(headless=headless, args=args)
    except Exception as e:
        err_msg = str(e).lower()
        if "libasound" in err_msg or "targetclosed" in err_msg or "closed" in err_msg:
            raise RuntimeError(
                "Chromium failed to start (often due to missing system libraries on Linux). "
                "Run: playwright install-deps\n"
                "On Ubuntu/Debian: sudo playwright install-deps\n"
                "This installs libasound2 and other required libraries."
            ) from e
        raise

    context = await browser.new_context(
        user_agent=stealth_user_agent,
        viewport={"width": 1280, "height": 720},
    )
    page = await context.new_page()
    cdp_session = await context.new_cdp_session(page)

    adapter = PlaywrightSessionAdapter(cdp_session)
    tab = CDPTab(adapter, None)

    async def cleanup() -> None:
        try:
            await context.close()
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass

    return {
        "tab": tab,
        "cleanup": cleanup,
        "conn": None,
    }
