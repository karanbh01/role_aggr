from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .config import (
    JOB_DESCRIPTION_SELECTOR,
    JOB_ID_DETAIL_SELECTOR,
)
from .common.logging import setup_scraper_logger

logger = setup_scraper_logger()
async def fetch_job_details(page,
                            job_url,
                            show_loading_bar=False):
    """Fetches and parses details from a single job posting page."""
    logger.info(f"Navigating to job detail page: {job_url}") # Replace conditional_print with logger.info
    job_details = {"url": job_url, "description": "N/A", "job_id": "N/A", "detail_page_title": "N/A"}
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=60000) # Increased timeout
        await page.wait_for_selector(JOB_DESCRIPTION_SELECTOR, timeout=10000) # Wait for description to be present

        title_element = await page.query_selector("h1[data-automation-id='jobPostingHeader']") # Common for title
        if title_element:
             job_details["detail_page_title"] = await title_element.inner_text()

        description_element = await page.query_selector(JOB_DESCRIPTION_SELECTOR)
        if description_element:
            # Get plain text content
            job_details["description"] = await description_element.inner_text()


        job_id_element = await page.query_selector(JOB_ID_DETAIL_SELECTOR)
        if not job_id_element: # Fallback for Job ID
             job_id_element = await page.query_selector("span:has-text('Job Id:') + span") # Example alternative
        if job_id_element:
             job_details["job_id"] = (await job_id_element.inner_text()).strip()

        # You can add more selectors here for other details like job type, full location details etc.
        # For example, to get all 'tags' or categories:
        # tags_elements = await page.query_selector_all("div[data-automation-id='pillContainer'] li")
        # job_details["tags"] = [await tag.inner_text() for tag in tags_elements]

    except PlaywrightTimeoutError:
        logger.warning(f"Timeout loading or finding elements on job detail page: {job_url}")
    except Exception as e:
        logger.error(f"Error processing job detail page {job_url}: {e}", exc_info=True)
    return job_details