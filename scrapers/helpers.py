"""
Shared scraping utilities. Plain functions, no classes.

- Browser initialization and cleanup
- Date parsing (relative and absolute)
- Location string cleaning
- Parallel job detail fetching
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Callable, Awaitable

from dateutil.parser import parse as dateutil_parse
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

from config import MAX_CONCURRENT_DETAILS, BROWSER_TIMEOUT_MS

logger = logging.getLogger("role_aggr")

# -- Browser management -----------------------------------------------------

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


async def launch_browser(playwright) -> Browser:
    """Launch a headless Chromium browser."""
    return await playwright.chromium.launch(headless=True)


async def new_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context that blocks images/CSS and looks like a real browser."""
    ctx = await browser.new_context(
        user_agent=USER_AGENT,
        no_viewport=True,
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers=BROWSER_HEADERS,
    )
    # Block heavy resources for speed
    await ctx.route("**/*.{png,jpg,jpeg,gif,svg,webp,css}", lambda route: route.abort())
    return ctx


async def navigate(page: Page, url: str, timeout: int = BROWSER_TIMEOUT_MS) -> bool:
    """Navigate to a URL, returning True on success."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        logger.warning(f"Timeout navigating to {url}")
        return False
    except Exception as e:
        logger.error(f"Navigation error for {url}: {e}")
        return False


# -- Date parsing -----------------------------------------------------------

_DAYS_AGO_RE = re.compile(r"(\d+)\s*\+?\s*days?\s*ago", re.IGNORECASE)


def parse_date(raw: str) -> datetime | None:
    """
    Parse job board date strings into datetime objects.

    Handles: "Posted today", "Posted yesterday", "Posted 3 days ago",
    "Posted 30+ days ago", "Posted Jan 10, 2024", and other dateutil formats.
    Returns None if unparseable.
    """
    if not raw:
        return None

    text = raw.lower().strip()
    # Strip common prefixes
    for prefix in ("posted on ", "posted "):
        if text.startswith(prefix):
            text = text[len(prefix):]

    now = datetime.now()

    if text in ("today", "just posted"):
        return now
    if text == "yesterday":
        return now - timedelta(days=1)

    m = _DAYS_AGO_RE.search(text)
    if m:
        return now - timedelta(days=int(m.group(1)))

    # Try dateutil for absolute dates
    try:
        return dateutil_parse(text)
    except Exception:
        return None


# -- Location parsing -------------------------------------------------------

_LOCATION_PREFIX_RE = re.compile(r"^\s*locations?\s*:?\s*", re.IGNORECASE)


def clean_location(raw: str) -> str:
    """Remove 'Locations:' prefix and clean whitespace."""
    if not raw:
        return ""
    return _LOCATION_PREFIX_RE.sub("", raw).strip()


def parse_job_id(raw: str) -> str:
    """Clean job ID strings -- remove 'Job ID:' and 'REQ-' prefixes."""
    if not raw:
        return ""
    cleaned = raw.strip()
    cleaned = re.sub(r"^job\s*id\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^req-?", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


# -- Parallel detail fetching -----------------------------------------------

async def fetch_details_parallel(
    browser: Browser,
    job_summaries: list[dict],
    detail_fetcher: Callable[[Page, str], Awaitable[dict]],
    max_concurrent: int = MAX_CONCURRENT_DETAILS,
) -> list[dict]:
    """
    Fetch job details in parallel using a semaphore for concurrency control.

    Args:
        browser: Playwright browser instance
        job_summaries: List of job summary dicts (must have 'detail_url')
        detail_fetcher: Async function(page, url) -> dict with detail fields
        max_concurrent: Max parallel browser contexts

    Returns:
        List of merged summary+detail dicts
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def process_one(summary: dict) -> dict | None:
        url = summary.get("detail_url")
        if not url or url == "N/A":
            return None

        async with semaphore:
            ctx = None
            page = None
            for attempt in range(3):
                try:
                    ctx = await new_stealth_context(browser)
                    page = await ctx.new_page()
                    details = await detail_fetcher(page, url)
                    merged = {**summary, **details}
                    return merged

                except PlaywrightTimeoutError:
                    logger.warning(f"Timeout attempt {attempt+1} for {url}")
                except PlaywrightError as e:
                    if "closed" in str(e).lower():
                        return None
                    logger.warning(f"Playwright error attempt {attempt+1} for {url}: {e}")
                except Exception as e:
                    logger.error(f"Error attempt {attempt+1} for {url}: {e}")
                finally:
                    if page:
                        try: await page.close()
                        except: pass
                    if ctx:
                        try: await ctx.close()
                        except: pass

                await asyncio.sleep(2 * (attempt + 1))  # exponential backoff

            return None

    # Filter to valid URLs
    valid = [s for s in job_summaries if s.get("detail_url") and s["detail_url"] != "N/A"]
    logger.info(f"Fetching details for {len(valid)} jobs ({max_concurrent} concurrent)")

    tasks = [process_one(s) for s in valid]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for result in completed:
        if isinstance(result, dict):
            results.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Task exception: {result}")

    logger.info(f"Fetched details for {len(results)}/{len(valid)} jobs")
    return results


# -- Job filtering ----------------------------------------------------------

def filter_jobs(jobs: list[dict]) -> list[dict]:
    """Remove duplicates (by URL) and jobs older than 30 days."""
    seen_urls = set()
    filtered = []
    for job in jobs:
        url = job.get("url")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        raw_date = job.get("date_posted_raw", "")
        if "30+ days ago" in str(raw_date).lower():
            continue

        filtered.append(job)

    removed = len(jobs) - len(filtered)
    if removed:
        logger.info(f"Filtered out {removed} jobs (duplicates + old)")
    return filtered
