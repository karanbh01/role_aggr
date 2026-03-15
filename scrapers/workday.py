"""
Workday job board scraper.

One public function: scrape_workday()
Everything else is a private helper. No classes.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    TimeoutError as PlaywrightTimeoutError,
)

from config import WORKDAY_SELECTORS as SEL, BROWSER_TIMEOUT_MS, PAGE_DELAY_MS
from .helpers import (
    launch_browser,
    new_stealth_context,
    navigate,
    parse_date,
    clean_location,
    parse_job_id,
    fetch_details_parallel,
    filter_jobs,
)

logger = logging.getLogger("role_aggr")


# -- Public API -------------------------------------------------------------

async def scrape_workday(
    url: str,
    company: str,
    max_pages: int | None = None,
    show_progress: bool = False,
) -> list[dict]:
    """
    Scrape a Workday job board and return a list of job dicts.

    This is the only function you need to call. It handles browser lifecycle,
    pagination, detail fetching, and filtering.

    Args:
        url: The Workday job board URL
        company: Company name (used for labeling)
        max_pages: Max pages to scrape (None = all)
        show_progress: Print progress to stdout

    Returns:
        List of job dicts ready for db.save_jobs()
    """
    logger.info(f"Starting Workday scrape: {company} @ {url}")

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        ctx = await new_stealth_context(browser)
        page = await ctx.new_page()

        try:
            if not await navigate(page, url, timeout=BROWSER_TIMEOUT_MS):
                logger.error(f"Failed to navigate to {url}")
                return []

            # Step 1: Extract job summaries from all pages
            summaries = await _paginate_and_extract(page, url, company, max_pages, show_progress)
            if not summaries:
                logger.warning(f"No job summaries found for {company}")
                return []

            logger.info(f"Extracted {len(summaries)} summaries for {company}")

            # Step 2: Fetch details in parallel (uses separate browser contexts)
            jobs = await fetch_details_parallel(browser, summaries, _fetch_one_detail)

            # Step 3: Stamp metadata
            for job in jobs:
                job["company"] = company
                job["job_board_url"] = url
                job["platform"] = "workday"

            # Step 4: Filter duplicates and old jobs
            jobs = filter_jobs(jobs)

            logger.info(f"Workday scrape complete: {company} -> {len(jobs)} jobs")
            return jobs

        except Exception as e:
            logger.error(f"Workday scrape failed for {company}: {e}", exc_info=True)
            return []

        finally:
            await ctx.close()
            await browser.close()


# -- Pagination -------------------------------------------------------------

async def _paginate_and_extract(
    page: Page,
    base_url: str,
    company: str,
    max_pages: int | None,
    show_progress: bool,
) -> list[dict]:
    """Walk through all pages (or scroll infinite list) and extract summaries."""
    all_summaries = []

    try:
        await page.wait_for_selector(SEL["job_list"], timeout=BROWSER_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.error(f"Job list never loaded for {company}")
        return []

    has_pagination = await _check_pagination(page)

    if has_pagination:
        page_num = 0
        while True:
            page_num += 1
            if max_pages and page_num > max_pages:
                break

            if show_progress:
                print(f"  [{company}] Page {page_num}...")

            summaries = await _extract_summaries(page, base_url)
            all_summaries.extend(summaries)

            if not await _go_next_page(page):
                break

            await page.wait_for_timeout(PAGE_DELAY_MS)
    else:
        # Infinite scroll
        await _scroll_to_bottom(page)
        all_summaries = await _extract_summaries(page, base_url)

    return all_summaries


async def _check_pagination(page: Page) -> bool:
    """Check whether traditional pagination controls exist."""
    try:
        await page.wait_for_selector(SEL["pagination"], timeout=5000)
        return True
    except PlaywrightTimeoutError:
        return False


async def _go_next_page(page: Page) -> bool:
    """Click the next-page button. Returns False if no more pages."""
    try:
        btn = await page.query_selector(SEL["next_page"])
        if btn and not await btn.is_disabled():
            await btn.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            return True
        return False
    except Exception as e:
        logger.warning(f"Next page navigation failed: {e}")
        return False


async def _scroll_to_bottom(page: Page, max_attempts: int = 20):
    """Scroll an infinite-scroll page until no new content loads."""
    stale_count = 0
    prev_count = 0

    for _ in range(max_attempts * 5):
        items = await page.query_selector_all(SEL["job_item"])
        current_count = len(items)

        if current_count > prev_count:
            stale_count = 0
            prev_count = current_count
        else:
            stale_count += 1
            if stale_count >= 5:
                break

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)

    logger.info(f"Scroll complete: {prev_count} items loaded")


# -- Summary extraction -----------------------------------------------------

async def _extract_summaries(page: Page, base_url: str) -> list[dict]:
    """Extract job summaries from the current page state."""
    summaries = []
    elements = await page.query_selector_all(SEL["job_item"])

    for el in elements:
        try:
            summary = await _parse_one_summary(el, base_url)
            if summary:
                summaries.append(summary)
        except Exception as e:
            logger.debug(f"Failed to parse summary element: {e}")

    return summaries


async def _parse_one_summary(el, base_url: str) -> dict | None:
    """Parse a single job element into a summary dict."""
    title_el = await el.query_selector(SEL["job_title"])
    if not title_el:
        return None

    title = (await title_el.inner_text()).strip()
    href = await title_el.get_attribute("href")

    if not href or not title:
        return None

    # Build absolute URL
    if href.startswith("/"):
        domain = base_url.split(".com")[0] + ".com"
        detail_url = domain + href
    elif href.startswith("http"):
        detail_url = href
    else:
        detail_url = href

    # Location
    loc_el = await el.query_selector(SEL["job_location"])
    location_raw = (await loc_el.inner_text()).strip() if loc_el else ""

    # Date
    date_el = await el.query_selector(SEL["job_date"])
    date_raw = (await date_el.inner_text()).strip() if date_el else ""

    return {
        "title": title,
        "detail_url": detail_url,
        "location_raw": date_raw,  # Keep raw for filtering
        "location": clean_location(location_raw),
        "date_posted_raw": date_raw,
        "date_posted": parse_date(date_raw).isoformat() if parse_date(date_raw) else None,
    }


# -- Detail fetching --------------------------------------------------------

async def _fetch_one_detail(page: Page, url: str) -> dict:
    """Fetch details from a single Workday job detail page."""
    details = {
        "url": url,
        "description": "",
        "job_id": "",
        "detail_page_title": "",
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
        await page.wait_for_selector(SEL["description"], timeout=10000)

        # Title
        title_el = await page.query_selector(SEL["title_header"])
        if title_el:
            details["detail_page_title"] = await title_el.inner_text()

        # Description
        desc_el = await page.query_selector(SEL["description"])
        if desc_el:
            details["description"] = await desc_el.inner_text()

        # Job ID (with fallback)
        jid_el = await page.query_selector(SEL["job_id"])
        if not jid_el:
            jid_el = await page.query_selector(SEL["job_id_fallback"])
        if jid_el:
            details["job_id"] = parse_job_id((await jid_el.inner_text()).strip())

    except PlaywrightTimeoutError:
        logger.warning(f"Timeout on detail page: {url}")
    except Exception as e:
        logger.error(f"Error on detail page {url}: {e}")

    return details
