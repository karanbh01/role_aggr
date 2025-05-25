from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .config import (
    JOB_LIST_SELECTOR,
    JOB_ITEM_SELECTOR,
    JOB_TITLE_SELECTOR,
    JOB_POSTED_DATE_SELECTOR,
    JOB_DESCRIPTION_SELECTOR,
    JOB_ID_DETAIL_SELECTOR,
    NEXT_PAGE_BUTTON_SELECTOR,
    PAGINATION_CONTAINER_SELECTOR
)
from .processing import extract_job_summaries

async def initialize_playwright_browser(p, 
                                        target_url):
    """Initializes Playwright browser, context, and navigates to the target URL."""
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        no_viewport=True, # Disable viewport to potentially save resources
        java_script_enabled=True, # Keep JavaScript enabled for dynamic content
        bypass_csp=True, # Bypass Content Security Policy
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    # Block image and stylesheet loading for faster page loads
    await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
    await context.route("**/*.css", lambda route: route.abort())
    page = await context.new_page()

    print(f"Navigating to {target_url}...")
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        print(f"Timeout navigating to {target_url}. Proceeding with potentially incomplete page.")
    except Exception as e:
        print(f"Error navigating to {target_url}: {e}")
        await browser.close()
        return None, None # Return None for page and browser on error
    return page, browser

async def check_pagination_exists(page):
    """Checks if pagination controls are present on the page."""
    try:
        await page.wait_for_selector(PAGINATION_CONTAINER_SELECTOR, timeout=5000)
        print("Pagination controls found.")
        return True
    except PlaywrightTimeoutError:
        print("No pagination controls found.")
        return False

async def navigate_to_next_page(page):
    """Navigates to the next page using the next page button."""
    try:
        next_button = await page.query_selector(NEXT_PAGE_BUTTON_SELECTOR)
        if next_button and not await next_button.is_disabled():
            print("Navigating to the next page...")
            await next_button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("Successfully navigated to the next page.")
            return True
        else:
            print("Next page button not found or is disabled.")
            return False
    except PlaywrightTimeoutError:
        print("Timeout navigating to the next page.")
        return False
    except Exception as e:
        print(f"Error navigating to the next page: {e}")
        return False

async def paginate_through_job_listings(page, 
                                        target_url, 
                                        max_pages=None):
    """
    Controls the pagination process, iterating through pages and accumulating job summaries.
    """
    all_job_summaries = []
    current_page_num = 1
    
    while True:
        print(f"\n--- Processing Page {current_page_num} ---")
        
        # First, try to extract jobs directly without scrolling
        page_job_summaries = await extract_job_summaries(page,
                                                         JOB_ITEM_SELECTOR,
                                                         JOB_TITLE_SELECTOR,
                                                         JOB_POSTED_DATE_SELECTOR,
                                                         target_url)

        if not page_job_summaries:
            print("No jobs found initially. Attempting to scroll to load all jobs.")
            # Scroll to load all jobs on the current page if no jobs were found
            await scroll_to_load_all_jobs(page, JOB_LIST_SELECTOR, JOB_ITEM_SELECTOR)
            
            # Re-extract job summaries after scrolling
            page_job_summaries = await extract_job_summaries(page,
                                                             JOB_ITEM_SELECTOR,
                                                             JOB_TITLE_SELECTOR,
                                                             JOB_POSTED_DATE_SELECTOR,
                                                             target_url)
        all_job_summaries.extend(page_job_summaries)
        print(f"Total job summaries collected so far: {len(all_job_summaries)}")

        if max_pages and current_page_num >= max_pages:
            print(f"Reached maximum pages ({max_pages}). Stopping pagination.")
            break

        if not await check_pagination_exists(page):
            print("No pagination controls found or end of pagination. Stopping.")
            break

        if not await navigate_to_next_page(page):
            print("Could not navigate to the next page. Stopping pagination.")
            break
        
        current_page_num += 1
        await page.wait_for_timeout(500) # Wait a bit before processing the next page

    return all_job_summaries

async def fetch_job_details(page, 
                            job_url):
    """Fetches and parses details from a single job posting page."""
    print(f"Navigating to job detail page: {job_url}")
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
        print(f"Timeout loading or finding elements on job detail page: {job_url}")
    except Exception as e:
        print(f"Error processing job detail page {job_url}: {e}")
    return job_details

async def scroll_to_load_all_jobs(page, 
                                  job_list_selector, 
                                  job_item_selector, 
                                  max_scroll_attempts=20):
    """Scrolls the page to load all job listings, handling infinite scroll."""
    print("Scrolling to load all jobs...")
    job_list_items_count = 0
    scroll_attempts = 0

    try:
        await page.wait_for_selector(job_list_selector, timeout=15000)
        
        while scroll_attempts < max_scroll_attempts:
            previous_job_count = job_list_items_count
            current_items = await page.query_selector_all(job_item_selector)
            job_list_items_count = len(current_items)
            print(f"Found {job_list_items_count} job items so far...")

            if job_list_items_count > previous_job_count:
                scroll_attempts = 0  # Reset counter if new jobs are found
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)  # Reduced wait time for content to load
            else:
                scroll_attempts += 1
                print(f"No new jobs loaded on scroll attempt {scroll_attempts}/{max_scroll_attempts}. Retrying...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000) # Reduced wait for subsequent attempts

            if scroll_attempts >= 5: # Increased threshold for breaking the loop
                print("No new jobs loaded after multiple scroll attempts. Assuming end of list.")
                break
        
        print(f"Finished scrolling. Total jobs found on list page: {job_list_items_count}")
        return True
    except PlaywrightTimeoutError:
        print("Timeout waiting for job list or during scrolling. Processing available jobs.")
        return False
    except Exception as e:
        print(f"Error during scrolling: {e}")
        return False