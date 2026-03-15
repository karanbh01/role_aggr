"""
LinkedIn job board scraper.

Strategy: Use LinkedIn's public job search pages which don't require login.
LinkedIn job URLs follow the pattern:
  https://www.linkedin.com/jobs/search/?keywords=...&location=...

NOTE: LinkedIn actively blocks scrapers. This module uses several mitigations:
- Realistic browser fingerprinting
- Rate limiting between requests
- Retry with backoff
- Rotating through search result pages slowly

If LinkedIn blocks too aggressively, consider:
1. LinkedIn Job Search API (requires partner access)
2. RSS feeds from LinkedIn job alerts
3. Using a third-party job data provider
"""

import asyncio
import logging
import re
from urllib.parse import urlencode, quote_plus

from playwright.async_api import (
    async_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .helpers import (
    launch_browser,
    navigate,
    parse_date,
    clean_location,
    filter_jobs,
)
from config import BROWSER_TIMEOUT_MS

logger = logging.getLogger("role_aggr")

# LinkedIn public job search selectors
LINKEDIN_SELECTORS = {
    "job_list":     "ul.jobs-search__results-list",
    "job_card":     "li div.base-card",
    "title":        "h3.base-search-card__title",
    "subtitle":     "h4.base-search-card__subtitle",  # company name
    "location":     "span.job-search-card__location",
    "date":         "time.job-search-card__listdate",
    "link":         "a.base-card__full-link",
    # Detail page selectors
    "description":  "div.show-more-less-html__markup",
    "detail_title": "h1.top-card-layout__title",
    "criteria_list": "ul.description__job-criteria-list",
}

# Default search configuration for finance jobs
DEFAULT_KEYWORDS = [
    "finance",
    "investment banking",
    "asset management",
    "portfolio manager",
    "quantitative analyst",
    "risk analyst",
    "financial analyst",
]

DEFAULT_LOCATION = "United Kingdom"


# -- Public API -------------------------------------------------------------

async def scrape_linkedin(
    url: str = None,
    company: str = "LinkedIn",
    max_pages: int = 5,
    keywords: list[str] = None,
    location: str = None,
    show_progress: bool = False,
) -> list[dict]:
    """
    Scrape LinkedIn public job search results.

    Args:
        url: Direct LinkedIn jobs URL (if None, builds from keywords/location)
        company: Label for this scrape source
        max_pages: Max result pages to scrape (25 jobs per page)
        keywords: Search keywords (default: finance-related terms)
        location: Location filter (default: United Kingdom)
        show_progress: Print progress to stdout

    Returns:
        List of job dicts ready for db.save_jobs()
    """
    keywords = keywords or DEFAULT_KEYWORDS
    location = location or DEFAULT_LOCATION

    logger.info(f"Starting LinkedIn scrape: {len(keywords)} keyword groups, location={location}")
    all_jobs = []

    async with async_playwright() as pw:
        browser = await launch_browser(pw)

        try:
            for kw in keywords:
                if show_progress:
                    print(f"  [LinkedIn] Searching: {kw}")

                search_url = url or _build_search_url(kw, location)
                jobs = await _scrape_search_results(browser, search_url, kw, max_pages, show_progress)

                for job in jobs:
                    job["company"] = job.get("company") or company
                    job["job_board_url"] = "https://www.linkedin.com/jobs/"
                    job["platform"] = "linkedin"

                all_jobs.extend(jobs)

                # Rate limit between keyword searches
                await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"LinkedIn scrape failed: {e}", exc_info=True)
        finally:
            await browser.close()

    all_jobs = filter_jobs(all_jobs)
    logger.info(f"LinkedIn scrape complete: {len(all_jobs)} total jobs")
    return all_jobs


# -- Search URL builder -----------------------------------------------------

def _build_search_url(keywords: str, location: str, start: int = 0) -> str:
    """Build a LinkedIn public job search URL."""
    params = {
        "keywords": keywords,
        "location": location,
        "trk": "public_jobs_jobs-search-bar_search-submit",
        "position": 1,
        "pageNum": 0,
        "start": start,
    }
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


# -- Search result scraping -------------------------------------------------

async def _scrape_search_results(
    browser, base_url: str, keyword: str, max_pages: int, show_progress: bool
) -> list[dict]:
    """Scrape multiple pages of LinkedIn search results."""
    all_summaries = []
    sel = LINKEDIN_SELECTORS

    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        java_script_enabled=True,
    )

    page = await ctx.new_page()

    try:
        for page_num in range(max_pages):
            start = page_num * 25
            url = base_url if page_num == 0 else re.sub(r"start=\d+", f"start={start}", base_url)
            if "start=" not in url:
                url += f"&start={start}"

            if show_progress:
                print(f"    Page {page_num + 1}/{max_pages}...")

            if not await navigate(page, url, timeout=BROWSER_TIMEOUT_MS):
                break

            # Wait for results to load
            try:
                await page.wait_for_selector(sel["job_list"], timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning(f"No results found for '{keyword}' page {page_num + 1}")
                break

            # Scroll down to load lazy content
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

            # Extract job cards
            cards = await page.query_selector_all(sel["job_card"])
            if not cards:
                break

            for card in cards:
                try:
                    summary = await _parse_linkedin_card(card, sel)
                    if summary:
                        all_summaries.append(summary)
                except Exception as e:
                    logger.debug(f"Failed to parse LinkedIn card: {e}")

            logger.info(f"LinkedIn '{keyword}' page {page_num+1}: {len(cards)} cards")

            # Rate limit between pages
            await asyncio.sleep(2 + page_num)  # increasingly slow

    except Exception as e:
        logger.error(f"Error scraping LinkedIn search results: {e}")
    finally:
        await page.close()
        await ctx.close()

    return all_summaries


async def _parse_linkedin_card(card, sel: dict) -> dict | None:
    """Parse a single LinkedIn job card element."""
    # Title + URL
    link_el = await card.query_selector(sel["link"])
    if not link_el:
        # Try alternative: the card itself may be a link
        link_el = await card.query_selector("a")
    if not link_el:
        return None

    title_el = await card.query_selector(sel["title"])
    title = (await title_el.inner_text()).strip() if title_el else ""
    href = await link_el.get_attribute("href")

    if not title or not href:
        return None

    # Clean URL (remove tracking params)
    url = href.split("?")[0] if href else ""

    # Company
    company_el = await card.query_selector(sel["subtitle"])
    company_name = (await company_el.inner_text()).strip() if company_el else ""

    # Location
    loc_el = await card.query_selector(sel["location"])
    location = (await loc_el.inner_text()).strip() if loc_el else ""

    # Date
    date_el = await card.query_selector(sel["date"])
    date_raw = ""
    if date_el:
        date_raw = await date_el.get_attribute("datetime") or (await date_el.inner_text()).strip()

    return {
        "title": title,
        "detail_url": url,
        "url": url,
        "company": company_name,
        "location": clean_location(location),
        "date_posted_raw": date_raw,
        "date_posted": parse_date(date_raw).isoformat() if parse_date(date_raw) else None,
        "description": "",  # Would need to visit detail page
        "job_id": "",
    }
