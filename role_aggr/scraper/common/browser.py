import logging
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tqdm import tqdm
# from .utils import conditional_print # Removed conditional_print import
from .processing import extract_job_summaries_with_selectors as extract_job_summaries
from .logging import setup_scraper_logger

logger = setup_scraper_logger()

async def initialize_playwright_browser(p,
                                        target_url,
                                        show_loading_bar=False):
    """Initializes Playwright browser, context, and navigates to the target URL."""
    
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                        no_viewport=True, # Disable viewport to potentially save resources
                                        java_script_enabled=True, # Keep JavaScript enabled for dynamic content
                                        bypass_csp=True, # Bypass Content Security Policy
                                        extra_http_headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                                                            "Accept-Language": "en-US,en;q=0.5",
                                                            "Connection": "keep-alive",
                                                            "Upgrade-Insecure-Requests": "1"})
    
    # Block image and stylesheet loading for faster page loads
    await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
    await context.route("**/*.css", lambda route: route.abort())
    
    page = await context.new_page()

    if show_loading_bar:
        # Use print for immediate feedback if loading bar is shown
        print(f"Navigating to {target_url}...")
    else:
        logger.info(f"Navigating to {target_url}...")
    
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=20000)
    
    except PlaywrightTimeoutError:
        logger.warning(f"Timeout navigating to {target_url}. Proceeding with potentially incomplete page.") # Critical
    
    except Exception as e:
        logger.error(f"Error navigating to {target_url}: {e}") # Critical
        await browser.close()
        return None, None # Return None for page and browser on error
    
    return page, browser

async def check_pagination_exists(page,
                                  pagination_container_selector, # Added as parameter
                                  show_loading_bar=False):
    """Checks if pagination controls are present on the page."""
    try:
        await page.wait_for_selector(pagination_container_selector, timeout=5000)
        if show_loading_bar:
            print("Pagination controls found.")
        else:
            logger.info("Pagination controls found.")
        return True
    except PlaywrightTimeoutError:
        if show_loading_bar:
            print("No pagination controls found.")
        else:
            logger.info("No pagination controls found.")
        return False

async def navigate_to_next_page(page,
                                next_page_button_selector, # Added as parameter
                                show_loading_bar=False):
    """Navigates to the next page using the next page button."""
    try:
        next_button = await page.query_selector(next_page_button_selector)
        if next_button and not await next_button.is_disabled():
            if show_loading_bar:
                print("Navigating to the next page...")
            else:
                logger.info("Navigating to the next page...")
            await next_button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            if show_loading_bar:
                print("Successfully navigated to the next page.")
            else:
                logger.info("Successfully navigated to the next page.")
            return True
        else:
            if show_loading_bar:
                print("Next page button not found or is disabled.")
            else:
                logger.info("Next page button not found or is disabled.")
            return False
    except PlaywrightTimeoutError:
        logger.warning("Timeout navigating to the next page.") # Critical
        return False
    except Exception as e:
        logger.error(f"Error navigating to the next page: {e}") # Critical
        return False

async def paginate_through_job_listings(page,
                                        company_name,
                                        target_url,
                                        job_list_selector, # Added as parameter
                                        job_item_selector, # Added as parameter
                                        job_title_selector, # Added as parameter
                                        job_posted_date_selector, # Added as parameter
                                        next_page_button_selector, # Added as parameter
                                        pagination_container_selector, # Added as parameter
                                        max_pages=None,
                                        show_loading_bar=False):
    """
    Controls the pagination process, iterating through pages and accumulating job summaries.
    """
    # NOTE: extract_job_summaries is now imported from common.processing
    # from role_aggr.scraper.common.processing import extract_job_summaries # This import will be handled by the user of this module
    all_job_summaries = []
    current_page_num = 1

    progress_bar = None
    if show_loading_bar:
        progress_bar = tqdm(desc=f"{company_name} : Scraping pages & collecting jobs",
                            unit="page",
                            bar_format="{desc}: {n_fmt} pages [{postfix}]")
        progress_bar.set_postfix(jobs=0)  # Initial job count

    while True:
        if show_loading_bar:
            print(f"\n--- Processing Page {current_page_num} ---")
        else:
            logger.info(f"--- Processing Page {current_page_num} ---")

        # First, try to extract jobs directly without scrolling
        # NOTE: extract_job_summaries needs to be imported by the caller of this function
        # For now, we assume it's available in the scope.
        # If this function is called from a module that imports from common.processing, it will work.
        # If not, the caller needs to ensure the import.
        page_job_summaries = await extract_job_summaries(page,
                                                         job_item_selector,
                                                         job_title_selector,
                                                         job_posted_date_selector,
                                                         target_url,
                                                         show_loading_bar) # Pass show_loading_bar

        if not page_job_summaries:
            if show_loading_bar:
                print("No jobs found initially. Attempting to scroll to load all jobs.")
            else:
                logger.info("No jobs found initially. Attempting to scroll to load all jobs.")
            await scroll_to_load_all_jobs(page, 
                                          job_list_selector, 
                                          job_item_selector, 
                                          show_loading_bar=show_loading_bar) # Pass show_loading_bar

            page_job_summaries = await extract_job_summaries(page,
                                                             job_item_selector,
                                                             job_title_selector,
                                                             job_posted_date_selector,
                                                             target_url,
                                                             show_loading_bar) # Pass show_loading_bar
        all_job_summaries.extend(page_job_summaries)

        if progress_bar is not None:
            progress_bar.update(1) # Increment page count
            progress_bar.set_postfix(jobs=len(all_job_summaries)) # Update job count

        if show_loading_bar:
            print(f"Total job summaries collected so far: {len(all_job_summaries)}")
        else:
            logger.info(f"Total job summaries collected so far: {len(all_job_summaries)}")

        if max_pages and current_page_num >= max_pages:
            if show_loading_bar:
                print(f"Reached maximum pages ({max_pages}). Stopping pagination.")
            else:
                logger.info(f"Reached maximum pages ({max_pages}). Stopping pagination.")
            break

        if not await check_pagination_exists(page, pagination_container_selector, show_loading_bar): # check_pagination_exists already uses conditional_print
            if show_loading_bar:
                print("End of pagination or no controls found. Stopping.")
            else:
                logger.info("End of pagination or no controls found. Stopping.")
            break

        if not await navigate_to_next_page(page, next_page_button_selector, show_loading_bar): # navigate_to_next_page uses conditional_print and print for errors
            if show_loading_bar:
                print("Could not navigate to the next page. Stopping pagination.")
            else:
                logger.info("Could not navigate to the next page. Stopping pagination.")
            break

        current_page_num += 1
        await page.wait_for_timeout(500)

    if progress_bar is not None:
        progress_bar.close()
    return all_job_summaries

async def scroll_to_load_all_jobs(page,
                                  job_list_selector, # Added as parameter
                                  job_item_selector, # Added as parameter
                                  max_scroll_attempts=20,
                                  show_loading_bar=False):
    """Scrolls the page to load all job listings, handling infinite scroll."""
    if show_loading_bar:
        print("Scrolling to load all jobs...")
    else:
        logger.info("Scrolling to load all jobs...")
    job_list_items_count = 0
    scroll_attempts = 0

    try:
        await page.wait_for_selector(job_list_selector, timeout=15000)

        while scroll_attempts < max_scroll_attempts:
            previous_job_count = job_list_items_count
            current_items = await page.query_selector_all(job_item_selector)
            job_list_items_count = len(current_items)
            if show_loading_bar:
                print(f"Found {job_list_items_count} job items so far...")
            else:
                logger.info(f"Found {job_list_items_count} job items so far...")

            if job_list_items_count > previous_job_count:
                scroll_attempts = 0  # Reset counter if new jobs are found
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)  # Reduced wait time for content to load
            else:
                scroll_attempts += 1
                if show_loading_bar:
                    print(f"No new jobs loaded on scroll attempt {scroll_attempts}/{max_scroll_attempts}. Retrying...")
                else:
                    logger.info(f"No new jobs loaded on scroll attempt {scroll_attempts}/{max_scroll_attempts}. Retrying...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000) # Reduced wait for subsequent attempts

            if scroll_attempts >= 5: # Increased threshold for breaking the loop
                if show_loading_bar:
                    print("No new jobs loaded after multiple scroll attempts. Assuming end of list.")
                else:
                    logger.info("No new jobs loaded after multiple scroll attempts. Assuming end of list.")
                break

        if show_loading_bar:
            print(f"Finished scrolling. Total jobs found on list page: {job_list_items_count}")
        else:
            logger.info(f"Finished scrolling. Total jobs found on list page: {job_list_items_count}")
        return True
    
    except PlaywrightTimeoutError:
        logger.warning("Timeout waiting for job list or during scrolling. Processing available jobs.") # Critical
    
    except Exception as e:
        logger.error(f"Error during scrolling: {e}") # Critical
        return False

# Note: fetch_job_details is not being moved as per the instructions.
# It remains in the original browser.py file for now.
# If it needs to be moved, it would likely go to common/browser.py as well.