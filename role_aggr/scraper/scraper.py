# scraper.py
import asyncio
import csv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os, sys

from config import (
    TARGET_URL,
    JOB_LIST_SELECTOR,
    JOB_ITEM_SELECTOR,
    JOB_TITLE_SELECTOR,
    JOB_POSTED_DATE_SELECTOR,
    JOB_DESCRIPTION_SELECTOR,
    JOB_ID_DETAIL_SELECTOR,
)

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from utils import parse_relative_date, parse_location
from role_aggr.database.functions import get_job_boards

async def fetch_job_details(page, 
                            job_url):
    """Fetches and parses details from a single job posting page."""
    print(f"Navigating to job detail page: {job_url}")
    job_details = {"url": job_url, "description": "N/A", "job_id": "N/A", "detail_page_title": "N/A"}
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=60000) # Increased timeout
        await page.wait_for_selector(JOB_DESCRIPTION_SELECTOR, timeout=30000) # Wait for description to be present

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

async def initialize_playwright_browser(p, 
                                        target_url):
    """Initializes Playwright browser, context, and navigates to the target URL."""
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    page = await context.new_page()

    print(f"Navigating to {target_url}...")
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=60000)
    except PlaywrightTimeoutError:
        print(f"Timeout navigating to {target_url}. Proceeding with potentially incomplete page.")
    except Exception as e:
        print(f"Error navigating to {target_url}: {e}")
        await browser.close()
        return None, None # Return None for page and browser on error
    return page, browser

async def scroll_to_load_all_jobs(page, 
                                  job_list_selector, 
                                  job_item_selector, 
                                  max_scroll_attempts=60):
    """Scrolls the page to load all job listings, handling infinite scroll."""
    print("Scrolling to load all jobs...")
    job_list_items_count = 0
    scroll_attempts = 0

    try:
        await page.wait_for_selector(job_list_selector, timeout=60000)
        
        while scroll_attempts < max_scroll_attempts:
            previous_job_count = job_list_items_count
            current_items = await page.query_selector_all(job_item_selector)
            job_list_items_count = len(current_items)
            print(f"Found {job_list_items_count} job items so far...")

            if job_list_items_count > previous_job_count:
                scroll_attempts = 0  # Reset counter if new jobs are found
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(10000)  # Increased wait time for content to load
            else:
                scroll_attempts += 1
                print(f"No new jobs loaded on scroll attempt {scroll_attempts}/{max_scroll_attempts}. Retrying...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(5000) # Shorter wait for subsequent attempts

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

async def extract_job_summaries(page, 
                                job_item_selector, 
                                job_title_selector, 
                                job_posted_date_selector, 
                                target_url):
    """Extracts job summaries (title, URL, location, date) from the main listing page."""
    print("Extracting job summaries...")
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

    print(f"Extracted {len(job_summaries)} job summaries.")
    return job_summaries

async def process_job_details(page,
                              company_name,
                              job_summaries,
                              fetch_job_details_func):
    """Navigates to job detail pages, fetches details, and merges with summaries."""
    all_job_data = []
    # Process all job summaries
    for i, summary in enumerate(job_summaries):
        if summary["detail_url"] != "N/A":
            print(f"\nProcessing job {i+1}/{len(job_summaries)}: {summary['title']}")
            detail_data = await fetch_job_details_func(page, summary["detail_url"])
            full_job_info = {**summary, **detail_data}
            full_job_info["company_name"] = company_name
            all_job_data.append(full_job_info)
            await page.wait_for_timeout(1000)
        else:
            print(f"Skipping job with no detail URL: {summary['title']}")
    return all_job_data

def save_job_data_to_csv(all_job_data, 
                         output_filename="role_aggr/scraper_new/workday_jobs_playwright.csv"):
    """Saves the extracted job data to a CSV file."""
    print(f"\n--- All Extracted Job Data ({len(all_job_data)} jobs) ---")
    
    if all_job_data:
        keys = all_job_data[0].keys()
        file_exists = os.path.exists(output_filename)
        file_is_empty = not file_exists or os.path.getsize(output_filename) == 0

        mode = "w" if file_is_empty else "a"
        write_header = file_is_empty

        with open(output_filename, mode, newline="", encoding="utf-8") as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            if write_header:
                dict_writer.writeheader()
            dict_writer.writerows(all_job_data)
        print(f"\nData saved to {output_filename}")
    else:
        print("\nNo job data to save.")

async def scraper(company_name, target_url):
    async with async_playwright() as p:
        page, browser = await initialize_playwright_browser(p, target_url)
        if not page or not browser:
            return

        await scroll_to_load_all_jobs(page, 
                                      JOB_LIST_SELECTOR, 
                                      JOB_ITEM_SELECTOR)
        job_summaries = await extract_job_summaries(page, 
                                                    JOB_ITEM_SELECTOR, 
                                                    JOB_TITLE_SELECTOR, 
                                                    JOB_POSTED_DATE_SELECTOR, 
                                                    target_url)
        all_job_data = await process_job_details(page, 
                                                 company_name,
                                                 job_summaries, 
                                                 fetch_job_details)
        save_job_data_to_csv(all_job_data)

        await browser.close()

def main():
    job_boards = get_job_boards()
    platform_job_boards = {platform: [{'company_name': board.company.name if board.company else None,
                                       'job_board_url': board.link} 
                                      for board in job_boards if board.platform == platform]
                           for platform in {board.platform for board in job_boards}}

    for platform, boards in platform_job_boards.items():
        if platform == "Workday":
            for board_dict in boards:
                company_name = board_dict['company_name']
                target_url = board_dict['job_board_url']        
                print(f"Scraping {board_dict['company_name'] if board_dict['company_name'] else platform} at {target_url}")
                asyncio.run(scraper(company_name, target_url))

if __name__ == "__main__":
    main()