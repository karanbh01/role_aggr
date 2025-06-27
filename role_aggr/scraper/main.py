# scraper.py
import csv
import os
import asyncio
from playwright.async_api import async_playwright
from role_aggr.database.functions import update_job_listings
from .common.processing import filter_job_data, process_job_details_parallel, extract_job_summaries
from .common.browser import initialize_playwright_browser
from .factory import ConcreteScraperFactory # Import the concrete factory
from .common.logging import setup_scraper_logger # Import the logger setup function
from .common.base import ScraperFactory, Scraper # Import ScraperFactory and Scraper ABC for type hinting

# Configure logging using the centralized setup
logger = setup_scraper_logger()

# Instantiate the factory
scraper_factory: ScraperFactory = ConcreteScraperFactory()


def save_job_listings_data_to_csv(all_job_data,
                                  output_filename,
                                  show_loading_bar=False):
    """Saves the extracted job data to a CSV file."""
    logger.info(f"--- All Extracted Job Data ({len(all_job_data)} jobs) ---")

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
        logger.info(f"Data saved to {output_filename}")
    else:
        logger.info("No job data to save.")


def save_job_listing_data_to_db(all_job_data):
    if all_job_data:
        # Database integration - run synchronous DB code in a separate thread
        logger.info(f"Attempting to save {len(all_job_data)} job listings to the database...")
        try:
            # Use asyncio.to_thread to run the synchronous DB function
            success, message = update_job_listings(all_job_data)

            if success:
                logger.info(f"Database save successful: {message}")
            else:
                logger.error(f"Database save failed: {message}")
        except Exception as e:
            logger.error(f"An exception occurred during database save operation: {e}", exc_info=True)
    else:
        logger.info("No job data to save to the database.")

async def scraper(company_name: str,
                  target_url: str,
                  platform: str,
                  max_pages: int | None = None,
                  to_csv: bool = False,
                  output_filename: str | None = None,
                  show_loading_bar: bool = False):
    """
    Scrapes job listings from a given target URL, including pagination,
    using platform-specific logic via the factory and ABCs.

    Args:
        company_name (str): The name of the company being scraped (can be the job board name if not a specific company).
        target_url (str): The canonical URL of the job board to scrape.
        platform (str): The platform hosting the job board (e.g., "workday").
        max_pages (int, optional): The maximum number of pages to scrape.
                                   If None, all available pages will be scraped.
        to_csv (bool): If True, save to CSV. Otherwise, save to database.
        output_filename (str, optional): Filename for CSV output.
        show_loading_bar (bool): Whether to show a loading bar.
    """
    logger.info(f"Starting scraper for {company_name} on platform {platform}...")

    try:
        # Use the factory to create a platform-specific scraper instance
        config = {'company_name': company_name}
        scraper_instance: Scraper = scraper_factory.create_scraper(platform.lower(), config)
        # Note: Parser instance is not directly needed in main, as Scraper implementation uses it internally

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return [] # Return empty list if platform is not supported or invalid
    except ImportError as e:
        logger.error(f"Import error for platform '{platform}': {e}")
        return [] # Return empty list if platform modules are missing
    except Exception as e:
        logger.error(f"An unexpected error occurred while creating scraper instance: {e}", exc_info=True)
        return [] # Return empty list on other errors

    async with async_playwright() as p:
        page, browser = await initialize_playwright_browser(p,
                                                           target_url,
                                                           show_loading_bar)
        if not page or not browser:
            logger.error(f"Failed to initialize browser for {target_url}")
            return [] # Return empty list on failure

        try:
            # Use the scraper instance to paginate and extract job summaries
            job_summaries = await extract_job_summaries(scraper=scraper_instance,
                                                        page=page,
                                                        company_name=company_name,
                                                        target_url=target_url,
                                                        max_pages=max_pages,
                                                        show_loading_bar=show_loading_bar)

            job_summaries_full = []

            for summary_base in job_summaries:
                summary_enriched = {**summary_base}
                summary_enriched['job_board_url'] = target_url
                job_summaries_full.append(summary_enriched)

            # Use the scraper instance to fetch job details in parallel
            all_job_data = await process_job_details_parallel( # Use the refactored processing function
                scraper=scraper_instance, # Pass the scraper instance
                browser=browser,
                company_name=company_name,
                job_summaries=job_summaries_full,
                show_loading_bar=show_loading_bar
            )

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

        except Exception as e:
            logger.error(f"An error occurred during the scraping process: {e}", exc_info=True)
            all_job_data = [] # Ensure all_job_data is defined even if an error occurs

        finally:
            if browser:
                await browser.close()

    return all_job_data # Return the processed job data
