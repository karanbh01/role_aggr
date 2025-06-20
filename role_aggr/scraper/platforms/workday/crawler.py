"""
Workday-specific scraper implementation.

This module provides the WorkdayScraper class that implements the Scraper interface
for scraping job listings from Workday job boards. It handles Workday-specific
pagination, job summary extraction, and job detail fetching.
"""

from typing import Dict, List, Any, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from tqdm import tqdm

from role_aggr.scraper.common.base import Scraper
from role_aggr.scraper.common.logging import setup_scraper_logger
from role_aggr.scraper.common.processing import extract_job_summaries_with_selectors
from role_aggr.scraper.common.browser import (
    check_pagination_exists,
    navigate_to_next_page,
    scroll_to_load_all_jobs,
    paginate_through_job_listings
)
from .config import (
    JOB_LIST_SELECTOR,
    JOB_ITEM_SELECTOR,
    JOB_TITLE_SELECTOR,
    JOB_LOCATION_SELECTOR,
    JOB_POSTED_DATE_SELECTOR,
    NEXT_PAGE_BUTTON_SELECTOR,
    PAGINATION_CONTAINER_SELECTOR
)
from .details import fetch_job_details
from .parser import WorkdayParser

logger = setup_scraper_logger()


class WorkdayScraper(Scraper):
    """
    Workday-specific implementation of the Scraper interface.
    
    This scraper handles the specific HTML structure and pagination behavior
    of Workday job boards, including infinite scroll detection, job summary
    extraction, and detailed job information fetching.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the Workday scraper with platform-specific configuration.
        
        Args:
            config: Dictionary containing Workday-specific selectors and settings
        """
        super().__init__(config)
        self.parser = WorkdayParser()
        logger.info(f"Initialized WorkdayScraper for company: {config.get('company_name', 'Unknown')}")
    
    async def paginate_through_job_listings(
        self,
        page: Page,
        company_name: str,
        target_url: str,
        max_pages: Optional[int] = None,
        show_loading_bar: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Navigate through Workday job listing pages and extract job summaries.
        
        Workday typically uses infinite scroll or pagination. This method handles
        both scenarios by detecting the pagination type and using appropriate
        navigation strategies.
        
        Args:
            page: Playwright page object for browser interaction
            company_name: Name of the company/job board being scraped
            target_url: Base URL of the job board
            max_pages: Maximum number of pages to scrape (None for all pages)
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            List of job summary dictionaries containing basic job information
        """
        logger.info(f"Starting pagination for {company_name} at {target_url}")
        all_job_summaries = []
        page_count = 0
        
        try:
            # Wait for the job list to load
            await page.wait_for_selector(JOB_LIST_SELECTOR, timeout=30000)
            logger.info("Job list container found, starting extraction")
            
            # Check if pagination exists or if it's infinite scroll
            has_pagination = await check_pagination_exists(page, PAGINATION_CONTAINER_SELECTOR)
            
            if has_pagination:
                logger.info("Detected pagination-based job board")
                # Use pagination-based extraction
                while True:
                    page_count += 1
                    if max_pages and page_count > max_pages:
                        logger.info(f"Reached maximum page limit: {max_pages}")
                        break
                    
                    logger.info(f"Processing page {page_count}")
                    
                    # Extract job summaries from current page
                    page_summaries = await self._extract_job_summaries(
                        page, target_url, show_loading_bar
                    )
                    
                    if page_summaries:
                        all_job_summaries.extend(page_summaries)
                        logger.info(f"Extracted {len(page_summaries)} jobs from page {page_count}")
                    else:
                        logger.warning(f"No jobs found on page {page_count}")
                    
                    # Try to navigate to next page
                    if not await navigate_to_next_page(page, NEXT_PAGE_BUTTON_SELECTOR):
                        logger.info("No more pages available")
                        break
                    
                    # Wait for new content to load
                    await page.wait_for_timeout(2000)
            
            else:
                logger.info("Detected infinite scroll job board")
                # Use infinite scroll extraction
                await scroll_to_load_all_jobs(page, JOB_ITEM_SELECTOR, show_loading_bar)
                
                # Extract all job summaries after scrolling
                all_job_summaries = await self._extract_job_summaries(
                    page, target_url, show_loading_bar
                )
                
                logger.info(f"Extracted {len(all_job_summaries)} jobs via infinite scroll")
        
        except PlaywrightTimeoutError:
            logger.error(f"Timeout waiting for job listings to load on {target_url}")
        except Exception as e:
            logger.error(f"Error during pagination: {e}", exc_info=True)
        
        logger.info(f"Pagination complete. Total jobs extracted: {len(all_job_summaries)}")
        return all_job_summaries
    
    async def fetch_job_details(
        self,
        page: Page,
        job_url: str,
        show_loading_bar: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch detailed information from a specific Workday job posting page.
        
        This method navigates to individual job detail pages and extracts
        comprehensive job information using Workday-specific selectors.
        
        Args:
            page: Playwright page object for browser interaction
            job_url: URL of the specific job detail page
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            Dictionary containing detailed job information
        """
        logger.debug(f"Fetching job details from: {job_url}")
        
        try:
            # Use the existing fetch_job_details function from details.py
            job_details = await fetch_job_details(page, job_url, show_loading_bar)
            
            # Parse the job ID using the parser
            if job_details.get('job_id'):
                job_details['job_id'] = self.parser.parse_job_id(job_details['job_id'])
            
            return job_details
            
        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {e}", exc_info=True)
            return {
                "url": job_url,
                "description": "N/A",
                "job_id": "N/A",
                "detail_page_title": "N/A"
            }
    
    async def _extract_job_summaries(
        self,
        page: Page,
        target_url: str,
        show_loading_bar: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extract job summary information from the current Workday page.
        
        This method extracts basic job information (title, URL, location, date)
        from job listing elements on the current page using Workday-specific selectors.
        
        Args:
            page: Playwright page object for browser interaction
            target_url: Base URL for constructing absolute URLs
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            List of job summary dictionaries
        """
        logger.debug("Extracting job summaries from current page")
        
        try:
            # Use the common extraction function with Workday-specific selectors
            selectors = {
                'job_list_selector': JOB_LIST_SELECTOR,
                'job_item_selector': JOB_ITEM_SELECTOR,
                'job_title_selector': JOB_TITLE_SELECTOR,
                'job_location_selector': JOB_LOCATION_SELECTOR,
                'job_posted_date_selector': JOB_POSTED_DATE_SELECTOR
            }
            
            job_summaries = await extract_job_summaries_with_selectors(
                page, target_url, selectors, show_loading_bar
            )
            
            # Parse dates and locations using the Workday parser
            for summary in job_summaries:
                if summary.get('date_posted_raw'):
                    summary['date_posted_parsed'] = self.parser.parse_date(
                        summary['date_posted_raw']
                    )
                
                if summary.get('location_raw'):
                    summary['location_parsed'] = self.parser.parse_location(
                        summary['location_raw']
                    )
            
            logger.debug(f"Successfully extracted {len(job_summaries)} job summaries")
            return job_summaries
            
        except Exception as e:
            logger.error(f"Error extracting job summaries: {e}", exc_info=True)
            return []