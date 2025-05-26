# scraper.py
import csv
import os
import logging
import asyncio # Added for to_thread
from playwright.async_api import async_playwright
from role_aggr.database.functions import update_job_listings
from .processing import filter_job_data

from .processing import process_job_details_parallel
from .browser import initialize_playwright_browser, paginate_through_job_listings, fetch_job_details
from .utils import conditional_print

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def save_job_listings_data_to_csv(all_job_data,
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


def save_job_listing_data_to_db(all_job_data):
    if all_job_data:
        # Database integration - run synchronous DB code in a separate thread
        logger.info(f"Attempting to save {len(all_job_data)} job listings to the database...")
        try:
            # Use asyncio.to_thread to run the synchronous DB function
            #success, message = await asyncio.to_thread(save_job_listing_data_to_db, all_job_data)
            success, message = update_job_listings(all_job_data)
            
            if success:
                logger.info(f"Database save successful: {message}")
            else:
                logger.error(f"Database save failed: {message}")
        except Exception as e:
            logger.error(f"An exception occurred during database save operation: {e}", exc_info=True)
    else:
        logger.info("No job data to save to the database.")

async def scraper(company_name, 
                  target_url,
                  max_pages=None,
                  to_csv=False,
                  output_filename=None,
                  show_loading_bar=False):
    """
    Scrapes job listings from a given target URL, including pagination.

    Args:
        company_name (str): The name of the company being scraped (can be the job board name if not a specific company).
        target_url (str): The canonical URL of the job board to scrape.
        max_pages (int, optional): The maximum number of pages to scrape.
                                   If None, all available pages will be scraped.
        to_csv (bool): If True, save to CSV. Otherwise, save to database.
        output_filename (str, optional): Filename for CSV output.
        show_loading_bar (bool): Whether to show a loading bar.
        job_board_type (str): Type of job board (e.g., "Company", "Aggregator", "Niche").
        job_board_platform (str, optional): Platform hosting the job board (e.g., "Greenhouse", "Lever", "Workable", or the company_name itself).
                                            Defaults to company_name if None.
        company_sector (str): Sector of the company (if job_board_type is 'Company').
    """
    async with async_playwright() as p:
        page, browser = await initialize_playwright_browser(p,
                                                           target_url,
                                                           show_loading_bar)
        if not page or not browser:
            logger.error(f"Failed to initialize browser for {target_url}")
            return [] # Return empty list on failure

        job_summaries = await paginate_through_job_listings(page,
                                                           company_name,
                                                           target_url,
                                                           max_pages,
                                                           show_loading_bar)

        job_summaries_full = []

        for summary_base in job_summaries: # summary_base usually contains job_link and initial title
            summary_enriched = {**summary_base} # Copy base summary to enrich it
            summary_enriched['job_board_url'] = target_url
            job_summaries_full.append(summary_enriched)

        all_job_data = await process_job_details_parallel(browser, # Pass browser instance
                                                          company_name, # Still used for logging/context within processing
                                                          job_summaries_full, # Use enriched summaries
                                                          fetch_job_details,
                                                          show_loading_bar)
        
        logger.info(f"Jobs before filtering: {len(all_job_data)}")
        all_job_data = await filter_job_data(all_job_data,
                                             show_loading_bar)
        logger.info(f"Jobs after filtering: {len(all_job_data)}")

        if to_csv:
            save_job_listings_data_to_csv(all_job_data,
                                          output_filename,
                                          show_loading_bar)

        else:
            await asyncio.to_thread(save_job_listing_data_to_db, all_job_data)

        await browser.close()

