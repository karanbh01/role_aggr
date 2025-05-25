# scraper.py
import csv
from playwright.async_api import async_playwright
import os

from .processing import process_job_details_parallel
from .browser import initialize_playwright_browser, paginate_through_job_listings, fetch_job_details
from .utils import conditional_print


def save_job_data_to_csv(all_job_data,
                         output_filename,
                         show_loading_bar=False):
    """Saves the extracted job data to a CSV file."""
    conditional_print(f"\n--- All Extracted Job Data ({len(all_job_data)} jobs) ---", show_loading_bar)
    
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
        conditional_print(f"\nData saved to {output_filename}", show_loading_bar)
    else:
        conditional_print("\nNo job data to save.", show_loading_bar)

async def scraper(company_name, 
                  target_url, 
                  max_pages=None,
                  to_csv=False,
                  output_filename=None,
                  show_loading_bar=False):
    """
    Scrapes job listings from a given target URL, including pagination.
    
    Args:
        company_name (str): The name of the company being scraped.
        target_url (str): The URL of the job board to scrape.
        max_pages (int, optional): The maximum number of pages to scrape.
                                   If None, all available pages will be scraped.
    """
    async with async_playwright() as p:
        page, browser = await initialize_playwright_browser(p, 
                                                            target_url, 
                                                            show_loading_bar)
        if not page or not browser:
            return

        job_summaries = await paginate_through_job_listings(page,
                                                            company_name, 
                                                            target_url, 
                                                            max_pages, 
                                                            show_loading_bar)
        
        all_job_data = await process_job_details_parallel(browser, # Pass browser instance
                                                          company_name,
                                                          job_summaries,
                                                          fetch_job_details,
                                                          show_loading_bar)
        if to_csv:
            save_job_data_to_csv(all_job_data,
                                 output_filename,
                                 show_loading_bar)

        await browser.close()

