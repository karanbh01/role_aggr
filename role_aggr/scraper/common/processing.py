"""
High-Level Processing Module for Job Scraping

This module has been refactored as part of EIP-001 Task 7 to implement a generic orchestrator
that works with abstract base classes instead of platform-specific logic.

Key Changes:
- extract_job_summaries() is now platform-agnostic and uses Scraper ABC interface
- All processing functions now accept a Scraper instance instead of platform-specific parameters
- Legacy functions are preserved for backward compatibility during transition
- New orchestrator functions provide complete pipeline processing

Migration Guide:
- Old: extract_job_summaries(page, selectors...)
- New: extract_job_summaries(scraper, page, company_name, target_url, ...)
- Use extract_job_summaries_with_selectors() for backward compatibility

The refactored functions maintain the same async/await patterns, error handling, and logging
while providing a clean abstraction layer for different job board platforms.
"""

import asyncio
from typing import Optional, List, Dict, Any
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from tqdm.asyncio import tqdm_asyncio
from .config import JOB_DETAIL_CONCURRENCY
from .utils import parse_relative_date, parse_location
from .logging import setup_scraper_logger

logger = setup_scraper_logger()

async def process_job_details_sequential(scraper,
                                         page,
                                         company_name,
                                         job_summaries,
                                         show_loading_bar=False):
    """
    Sequentially navigates to job detail pages, fetches details, and merges with summaries.
    
    Refactored to use the Scraper ABC interface for platform-agnostic detail fetching.
    
    Args:
        scraper: Instance of a platform-specific Scraper (implementing the Scraper ABC)
        page: Playwright page object for browser interaction
        company_name: Name of the company/job board being scraped
        job_summaries: List of job summary dictionaries
        show_loading_bar: Whether to display progress indicators
        
    Returns:
        List of complete job data dictionaries with details merged
    """
    from .base import Scraper
    
    # Validate that the scraper implements the required interface
    if not isinstance(scraper, Scraper):
        raise TypeError(
            f"Expected scraper to be an instance of Scraper ABC, "
            f"got {type(scraper).__name__}"
        )
    
    all_job_data = []
    
    # Process all job summaries
    for i, summary in enumerate(job_summaries):
        if summary.get("detail_url") and summary["detail_url"] != "N/A":
            logger.info(f"Processing job {i+1}/{len(job_summaries)} (sequential): {summary.get('title', 'N/A')}")
            
            try:
                detail_data = await scraper.fetch_job_details(
                    page=page,
                    job_url=summary["detail_url"],
                    show_loading_bar=show_loading_bar
                )
                
                # Merge summary and detail data
                full_job_info = {**summary, **detail_data}
                full_job_info["company_name"] = company_name
                all_job_data.append(full_job_info)
                
                # Small delay between sequential requests
                await page.wait_for_timeout(300)
                
            except Exception as e:
                logger.error(
                    f"Error processing job details for {summary.get('title', 'N/A')}: {e}",
                    exc_info=True
                )
        else:
            logger.info(f"Skipping job with no detail URL: {summary.get('title', 'N/A')}")
    
    return all_job_data

async def process_single_job(scraper,
                             browser,
                             job_summary,
                             company_name,
                             semaphore,
                             show_loading_bar=False):
    """
    Processes a single job: creates a new context/page, fetches details, and handles retries.
    
    Refactored to use the Scraper ABC interface for platform-agnostic detail fetching.
    
    Args:
        scraper: Instance of a platform-specific Scraper (implementing the Scraper ABC)
        browser: Playwright browser instance
        job_summary: Dictionary containing job summary information
        company_name: Name of the company/job board being scraped
        semaphore: Asyncio semaphore for concurrency control
        show_loading_bar: Whether to display progress indicators
        
    Returns:
        Dictionary with complete job information or None if processing fails
    """
    from .base import Scraper
    
    # Validate that the scraper implements the required interface
    if not isinstance(scraper, Scraper):
        raise TypeError(
            f"Expected scraper to be an instance of Scraper ABC, "
            f"got {type(scraper).__name__}"
        )
    
    async with semaphore:
        job_url = job_summary.get("detail_url")
        if not job_url or job_url == "N/A":
            logger.info(f"Skipping job with no detail URL: {job_summary.get('title', 'N/A')}")
            return None

        context = None
        page = None
        attempts = 3
        for attempt in range(attempts):
            try:
                logger.info(f"Attempt {attempt + 1}/{attempts} for job: {job_summary.get('title', 'N/A')} - URL: {job_url}")
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    no_viewport=True,
                    java_script_enabled=True, # Keep JavaScript enabled for dynamic content
                    bypass_csp=True,
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                    }
                )
                await context.route("**/*.{png,jpg,jpeg,gif,svg,webp,css}", lambda route: route.abort())
                page = await context.new_page()

                # Use the scraper's fetch_job_details method
                detail_data = await scraper.fetch_job_details(
                    page=page,
                    job_url=job_url,
                    show_loading_bar=show_loading_bar
                )
                
                # Merge summary and detail data
                full_job_info = {**job_summary, **detail_data}
                full_job_info["company_name"] = company_name
                return full_job_info
                
            except PlaywrightTimeoutError as e:
                logger.warning(f"Timeout on attempt {attempt + 1} for {job_url}: {e}")
                if attempt == attempts - 1:
                    logger.error(f"Failed to process job {job_url} after {attempts} attempts due to timeout.")
                    return None
                await asyncio.sleep(2 * (attempt + 1)) # Exponential backoff for retries
            
            except PlaywrightError as e: # Catch Playwright specific errors like TargetClosedError
                logger.warning(f"Playwright error on attempt {attempt + 1} for {job_url}: {e}")
                # Check type name as the error might be from playwright._impl._errors
                if "Target page, context or browser has been closed" in str(e) or "TargetClosedError" in type(e).__name__:
                    logger.error(f"Target closed for {job_url}. Cannot retry this task.")
                    return None # Stop retrying for this job if target is closed
                if attempt == attempts - 1:
                    logger.error(f"Failed to process job {job_url} after {attempts} attempts due to Playwright error.")
                    return None
                await asyncio.sleep(2 * (attempt + 1)) # Exponential backoff
            
            except Exception as e:
                logger.error(f"Generic error on attempt {attempt + 1} processing job {job_url}: {e}", exc_info=True)
                if attempt == attempts - 1:
                    logger.error(f"Failed to process job {job_url} after {attempts} attempts due to generic error.")
                    return None
                await asyncio.sleep(2 * (attempt + 1)) # Exponential backoff
            
            finally:
                if page:
                    try:
                        await page.close()
                    except PlaywrightError as e_close: # Catch errors during close, e.g. if already closed
                        logger.error(f"Error closing page for {job_url} (attempt: {attempt + 1}): {e_close}", exc_info=True)
                    except Exception as e_close_generic:
                        logger.error(f"Generic error closing page for {job_url} (attempt: {attempt + 1}): {e_close_generic}", exc_info=True)
                if context:
                    try:
                        await context.close()
                    except PlaywrightError as e_close: # Catch errors during close
                        logger.error(f"Error closing context for {job_url} (attempt: {attempt + 1}): {e_close}", exc_info=True)
                    except Exception as e_close_generic:
                        logger.error(f"Generic error closing context for {job_url} (attempt: {attempt + 1}): {e_close_generic}", exc_info=True)
        
        return None # Fallback if all attempts fail

async def process_job_details_parallel(scraper,
                                       browser,
                                       company_name,
                                       job_summaries,
                                       show_loading_bar=False):
    """
    Fetches job details in parallel using a semaphore to limit concurrency.
    
    Refactored to use the Scraper ABC interface for platform-agnostic detail fetching.
    
    Args:
        scraper: Instance of a platform-specific Scraper (implementing the Scraper ABC)
        browser: Playwright browser instance
        company_name: Name of the company/job board being scraped
        job_summaries: List of job summary dictionaries
        show_loading_bar: Whether to display progress indicators
        
    Returns:
        List of complete job data dictionaries with details merged
    """
    from .base import Scraper
    
    # Validate that the scraper implements the required interface
    if not isinstance(scraper, Scraper):
        raise TypeError(
            f"Expected scraper to be an instance of Scraper ABC, "
            f"got {type(scraper).__name__}"
        )
    
    all_job_data = []
    semaphore = asyncio.Semaphore(JOB_DETAIL_CONCURRENCY)

    logger.info(f"--- Starting Parallel Job Detail Processing ({JOB_DETAIL_CONCURRENCY} workers) ---")
    
    # Filter summaries that have a valid detail_url to process
    valid_job_summaries = [
        s for s in job_summaries if s.get("detail_url") and s.get("detail_url") != "N/A"
    ]

    if not valid_job_summaries:
        logger.info(f"No jobs with valid detail URLs found out of {len(job_summaries)} total summaries.")
        return all_job_data # Return empty list if no valid jobs

    # Create tasks only for valid summaries using the updated process_single_job function
    tasks_for_processing = [process_single_job(scraper=scraper,
                                                browser=browser,
                                                job_summary=summary,
                                                company_name=company_name,
                                                semaphore=semaphore,
                                                show_loading_bar=show_loading_bar)
                            for summary in valid_job_summaries]

    if not tasks_for_processing: # Should be redundant due to valid_job_summaries check, but safe
        logger.info("No tasks to process after filtering.")
        return all_job_data

    if show_loading_bar:
        logger.info(f"Processing {len(tasks_for_processing)} jobs with progress bar...")
        for future in tqdm_asyncio.as_completed(tasks_for_processing,
                                                desc=f"{company_name} : Processing jobs",
                                                total=len(tasks_for_processing)
        ):
            try:
                result = await future # Await the future to get the actual result
                if result is not None: # process_single_job returns None on failure or skip
                    all_job_data.append(result)
            except Exception as e:
                # This catches exceptions from the task execution if not handled within process_single_job,
                # or if the future itself fails (e.g. cancelled).
                logger.error(f"Error processing a job future via tqdm: {e}", exc_info=True)
    else:
        logger.info(f"Processing {len(tasks_for_processing)} jobs via asyncio.gather...")
        results = await asyncio.gather(*tasks_for_processing, return_exceptions=True)

        for result_item in results: # Renamed result to result_item
            if isinstance(result_item, Exception):
                logger.error(f"An error occurred in a parallel task (gathered): {result_item}", exc_info=True)
            elif result_item is not None:
                all_job_data.append(result_item)

    logger.info(f"--- Parallel Job Detail Processing Finished. Collected {len(all_job_data)} jobs. ---")
    return all_job_data

async def extract_job_summaries(scraper,
                                page,
                                company_name,
                                target_url,
                                max_pages=None,
                                show_loading_bar=False):
    """
    Generic orchestrator for extracting job summaries using platform-specific scrapers.
    
    This function has been refactored to work as a platform-agnostic orchestrator that
    delegates the actual extraction logic to platform-specific Scraper implementations.
    
    Args:
        scraper: Instance of a platform-specific Scraper (implementing the Scraper ABC)
        page: Playwright page object for browser interaction
        company_name: Name of the company/job board being scraped
        target_url: Base URL of the job board
        max_pages: Maximum number of pages to scrape (None for all pages)
        show_loading_bar: Whether to display progress indicators
        
    Returns:
        List of job summary dictionaries containing standardized job information
        
    Raises:
        TypeError: If scraper doesn't implement the Scraper ABC interface
        PlaywrightTimeoutError: When page navigation or element loading times out
        Exception: For other scraping-related errors
    """
    from .base import Scraper
    
    # Validate that the scraper implements the required interface
    if not isinstance(scraper, Scraper):
        raise TypeError(
            f"Expected scraper to be an instance of Scraper ABC, "
            f"got {type(scraper).__name__}"
        )
    
    logger.info(f"Starting job summary extraction for {company_name} using {type(scraper).__name__}")
    
    try:
        # Delegate to the platform-specific scraper implementation
        job_summaries = await scraper.paginate_through_job_listings(page=page,
                                                                    company_name=company_name,
                                                                    target_url=target_url,
                                                                    max_pages=max_pages,
                                                                    show_loading_bar=show_loading_bar)
        
        logger.info(f"Successfully extracted {len(job_summaries)} job summaries for {company_name}")
        return job_summaries
        
    except Exception as e:
        logger.error(
            f"Error extracting job summaries for {company_name} using {type(scraper).__name__}: {e}",
            exc_info=True
        )
        raise


async def extract_job_summaries_legacy(page,
                                       job_item_selector,
                                       job_title_selector,
                                       job_posted_date_selector,
                                       target_url,
                                       show_loading_bar=False):
    """
    Legacy function for extracting job summaries (Workday-specific implementation).
    
    This function is kept for backward compatibility during the transition period.
    New code should use the generic extract_job_summaries function with a Scraper instance.
    
    DEPRECATED: This function will be removed in a future version.
    Use extract_job_summaries with a platform-specific Scraper instead.
    """
    logger.warning(
        "extract_job_summaries_legacy is deprecated. "
        "Use extract_job_summaries with a Scraper instance instead."
    )
    
    logger.info("Extracting job summaries (legacy Workday implementation)...")
    job_summaries = []
    job_elements = await page.query_selector_all(job_item_selector)

    for job_element in job_elements:
        summary = {}
        title_element = await job_element.query_selector(job_title_selector)
        if title_element:
            summary["title"] = (await title_element.inner_text()).strip()
            href = await title_element.get_attribute("href")
            if href:
                if href.startswith("/"):
                    base_url = target_url.split(".com")[0] + ".com"
                    summary["detail_url"] = base_url + href
                else:
                    summary["detail_url"] = href
            else:
                summary["detail_url"] = "N/A"
        else:
            summary["title"] = "N/A"
            summary["detail_url"] = "N/A"

        location_elements = await job_element.query_selector_all("dl > dd[data-automation-id='promptOption-location']")
        if not location_elements:
             location_elements = await job_element.query_selector_all("div[data-automation-id*='locations']")

        location_raw = "N/A"
        if location_elements:
            locations_list = []
            for loc_el in location_elements:
                locations_list.append((await loc_el.inner_text()).strip())
            location_raw = "; ".join(locations_list) if locations_list else "N/A"
        else:
            location_text_element = await job_element.query_selector("span[data-automation-id='subtitle']")
            if location_text_element:
                location_raw = (await location_text_element.inner_text()).strip().split(" | ")[0]

        summary["location_raw"] = location_raw
        summary["location_parsed"] = parse_location(location_raw)

        date_element = await job_element.query_selector(job_posted_date_selector)
        if not date_element:
            date_element = await job_element.query_selector("div[data-automation-id*='postedOn']")

        date_str_raw = (await date_element.inner_text()).strip() if date_element else ""
        summary["date_posted_raw"] = date_str_raw
        summary["date_posted_parsed"] = parse_relative_date(date_str_raw)

        if summary["title"] != "N/A" and summary["detail_url"] != "N/A":
            job_summaries.append(summary)

    logger.info(f"Extracted {len(job_summaries)} job summaries (legacy).")
    return job_summaries

async def filter_job_data(job_data_list,
                          show_loading_bar=False):
    """
    Filters job data to remove duplicates and jobs posted 30+ days ago.
    """
    filtered_jobs = []
    seen_urls = set()
    jobs_removed_duplicate = 0
    jobs_removed_date = 0

    for job in job_data_list:
        # Remove duplicates based on url
        if job.get("url") not in seen_urls:
            seen_urls.add(job.get("url"))
            # Remove jobs posted 30+ days ago
            if "posted 30+ days ago" not in job.get("date_posted_raw", "").lower():
                filtered_jobs.append(job)
            else:
                jobs_removed_date += 1
        else:
            jobs_removed_duplicate += 1

    logger.info(f"Removed {jobs_removed_duplicate} duplicate jobs.")
    logger.info(f"Removed {jobs_removed_date} jobs posted 30+ days ago.")
    return filtered_jobs

async def process_jobs_with_scraper(scraper,
                                    browser,
                                    page,
                                    company_name,
                                    target_url,
                                    max_pages=None,
                                    use_parallel_processing=True,
                                    show_loading_bar=False):
    """
    Complete job processing pipeline using a platform-specific scraper.
    
    This function orchestrates the entire job scraping process:
    1. Extract job summaries using the scraper's pagination logic
    2. Fetch detailed information for each job
    3. Filter and clean the results
    
    Args:
        scraper: Instance of a platform-specific Scraper (implementing the Scraper ABC)
        browser: Playwright browser instance
        page: Playwright page object for browser interaction
        company_name: Name of the company/job board being scraped
        target_url: Base URL of the job board
        max_pages: Maximum number of pages to scrape (None for all pages)
        use_parallel_processing: Whether to use parallel processing for job details
        show_loading_bar: Whether to display progress indicators
        
    Returns:
        List of filtered and complete job data dictionaries
        
    Raises:
        TypeError: If scraper doesn't implement the Scraper ABC interface
        Exception: For scraping-related errors
    """
    from .base import Scraper
    
    # Validate that the scraper implements the required interface
    if not isinstance(scraper, Scraper):
        raise TypeError(
            f"Expected scraper to be an instance of Scraper ABC, "
            f"got {type(scraper).__name__}"
        )
    
    logger.info(f"Starting complete job processing pipeline for {company_name}")
    
    try:
        # Step 1: Extract job summaries
        job_summaries = await extract_job_summaries(
            scraper=scraper,
            page=page,
            company_name=company_name,
            target_url=target_url,
            max_pages=max_pages,
            show_loading_bar=show_loading_bar
        )
        
        if not job_summaries:
            logger.warning(f"No job summaries found for {company_name}")
            return []
        
        # Step 2: Fetch job details
        if use_parallel_processing:
            all_job_data = await process_job_details_parallel(
                scraper=scraper,
                browser=browser,
                company_name=company_name,
                job_summaries=job_summaries,
                show_loading_bar=show_loading_bar
            )
        else:
            all_job_data = await process_job_details_sequential(
                scraper=scraper,
                page=page,
                company_name=company_name,
                job_summaries=job_summaries,
                show_loading_bar=show_loading_bar
            )
        
        # Step 3: Filter and clean results
        filtered_jobs = await filter_job_data(
            job_data_list=all_job_data,
            show_loading_bar=show_loading_bar
        )
        
        logger.info(
            f"Completed job processing pipeline for {company_name}. "
            f"Final count: {len(filtered_jobs)} jobs"
        )
        
        return filtered_jobs
        
    except Exception as e:
        logger.error(
            f"Error in job processing pipeline for {company_name}: {e}",
            exc_info=True
        )
        raise


# Backward compatibility functions for legacy code
async def extract_job_summaries_with_selectors(
    page,
    target_url,
    selectors: Dict[str, str],
    show_loading_bar=False
):
    """
    Backward compatibility wrapper for the legacy extract_job_summaries function.
    
    This function provides a bridge between the old selector-based approach
    and the new Scraper ABC interface. It's recommended to migrate to using
    platform-specific Scraper implementations instead.
    
    DEPRECATED: Use extract_job_summaries with a Scraper instance instead.
    """
    logger.warning(
        "extract_job_summaries_with_selectors is deprecated. "
        "Consider migrating to a platform-specific Scraper implementation."
    )
    
    
    return await extract_job_summaries_legacy(
        page=page,
        job_item_selector=selectors['job_item_selector'],
        job_title_selector=selectors['job_title_selector'],
        job_posted_date_selector=selectors['job_posted_date_selector'],
        target_url=target_url,
        show_loading_bar=show_loading_bar
    )