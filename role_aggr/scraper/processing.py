import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .config import JOB_DETAIL_CONCURRENCY
from .utils import parse_relative_date, parse_location

async def process_job_details_sequential(page,
                                       company_name,
                                       job_summaries,
                                       fetch_job_details_func):
    """Sequentially navigates to job detail pages, fetches details, and merges with summaries."""
    all_job_data = []
    # Process all job summaries
    for i, summary in enumerate(job_summaries):
        if summary["detail_url"] != "N/A":
            print(f"\nProcessing job {i+1}/{len(job_summaries)} (sequential): {summary['title']}")
            detail_data = await fetch_job_details_func(page, summary["detail_url"])
            full_job_info = {**summary, **detail_data}
            full_job_info["company_name"] = company_name
            all_job_data.append(full_job_info)
            await page.wait_for_timeout(300) # Small delay between sequential requests
        else:
            print(f"Skipping job with no detail URL: {summary['title']}")
    return all_job_data

async def process_single_job(browser, 
                             job_summary, 
                             company_name, 
                             semaphore, 
                             fetch_job_details_func):
    """
    Processes a single job: creates a new context/page, fetches details, and handles retries.
    """
    async with semaphore:
        job_url = job_summary.get("detail_url")
        if not job_url or job_url == "N/A":
            print(f"Skipping job with no detail URL: {job_summary.get('title', 'N/A')}")
            return None

        context = None
        page = None
        attempts = 3
        for attempt in range(attempts):
            try:
                print(f"Attempt {attempt + 1}/{attempts} for job: {job_summary.get('title', 'N/A')} - URL: {job_url}")
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

                detail_data = await fetch_job_details_func(page, job_url)
                full_job_info = {**job_summary, **detail_data}
                full_job_info["company_name"] = company_name
                return full_job_info
            except PlaywrightTimeoutError as e:
                print(f"Timeout on attempt {attempt + 1} for {job_url}: {e}")
                if attempt == attempts - 1:
                    print(f"Failed to process job {job_url} after {attempts} attempts due to timeout.")
                    return None
                await asyncio.sleep(1) # Wait 1 second before retrying
            except Exception as e:
                print(f"Error on attempt {attempt + 1} processing job {job_url}: {e}")
                if attempt == attempts - 1:
                    print(f"Failed to process job {job_url} after {attempts} attempts.")
                    return None
                await asyncio.sleep(1) # Wait 1 second before retrying
            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()
        return None # Should not be reached if logic is correct, but as a fallback

async def process_job_details_parallel(browser,
                                     company_name,
                                     job_summaries,
                                     fetch_job_details_func):
    """
    Fetches job details in parallel using a semaphore to limit concurrency.
    """
    all_job_data = []
    semaphore = asyncio.Semaphore(JOB_DETAIL_CONCURRENCY)
    tasks = []

    print(f"\n--- Starting Parallel Job Detail Processing ({JOB_DETAIL_CONCURRENCY} workers) ---")
    for i, summary in enumerate(job_summaries):
        print(f"Queueing job {i+1}/{len(job_summaries)} for parallel processing: {summary.get('title', 'N/A')}")
        tasks.append(process_single_job(browser, summary, company_name, semaphore, fetch_job_details_func))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print(f"An error occurred in a parallel task: {result}")
        elif result is not None:
            all_job_data.append(result)

    print(f"--- Parallel Job Detail Processing Finished. Collected {len(all_job_data)} jobs. ---")
    return all_job_data

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