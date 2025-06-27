"""
Example: Using the Refactored High-Level Processing Module

This example demonstrates how to use the refactored extract_job_summaries function
and other processing functions with the new Scraper ABC interface.

This is part of EIP-001 Task 7 implementation.
"""

import asyncio
from playwright.async_api import async_playwright
from role_aggr.scraper.common.base import Scraper
from role_aggr.scraper.common.processing import (
    extract_job_summaries,
    process_jobs_with_scraper,
    extract_job_summaries_with_selectors  # Legacy function
)


class ExampleWorkdayScraper(Scraper):
    """
    Example implementation of a Workday scraper using the Scraper ABC.
    
    This demonstrates how to implement the abstract methods for a specific platform.
    """
    
    def __init__(self, config):
        super().__init__(config)
        # Platform-specific selectors from config
        self.job_item_selector = config.get("job_item_selector")
        self.job_title_selector = config.get("job_title_selector")
        self.job_posted_date_selector = config.get("job_posted_date_selector")
    
    async def paginate_through_job_listings(self, page, company_name, target_url, max_pages=None, show_loading_bar=False):
        """
        Example implementation of pagination logic for Workday.
        
        In a real implementation, this would handle:
        - Infinite scroll or pagination buttons
        - Loading more jobs dynamically
        - Extracting job summaries from each page
        """
        # This is a simplified example - real implementation would be more complex
        job_summaries = await self._extract_job_summaries(page, target_url, show_loading_bar)
        return job_summaries
    
    async def fetch_job_details(self, page, job_url, show_loading_bar=False):
        """
        Example implementation of job detail fetching for Workday.
        
        In a real implementation, this would:
        - Navigate to the job detail page
        - Extract comprehensive job information
        - Parse and clean the data
        """
        # Navigate to job detail page
        await page.goto(job_url)
        
        # Extract job details (simplified example)
        detail_data = {
            "url": job_url,
            "description": "Example job description",
            "job_id": "12345",
            "detail_page_title": "Example Job Title"
        }
        
        return detail_data
    
    async def _extract_job_summaries(self, page, target_url, show_loading_bar=False):
        """
        Example implementation of job summary extraction for Workday.
        
        This would extract basic job information from the current page.
        """
        # This is a simplified example using the legacy logic
        # In a real implementation, you'd use platform-specific selectors
        from role_aggr.scraper.common.processing import extract_job_summaries_legacy
        
        return await extract_job_summaries_legacy(
            page=page,
            job_item_selector=self.job_item_selector,
            job_title_selector=self.job_title_selector,
            job_posted_date_selector=self.job_posted_date_selector,
            target_url=target_url,
            show_loading_bar=show_loading_bar
        )


async def example_new_approach():
    """
    Example of using the new Scraper ABC interface.
    """
    print("=== New Approach: Using Scraper ABC ===")
    
    # Configuration for the scraper
    config = {
        "job_item_selector": "li[data-automation-id='listItem']",
        "job_title_selector": "a[data-automation-id='jobTitle']",
        "job_posted_date_selector": "dd[data-automation-id='postedOn']"
    }
    
    # Create a scraper instance
    scraper = ExampleWorkdayScraper(config)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            # Method 1: Use the refactored extract_job_summaries function
            job_summaries = await extract_job_summaries(
                scraper=scraper,
                page=page,
                company_name="Example Company",
                target_url="https://example.workday.com/jobs",
                max_pages=2,
                show_loading_bar=True
            )
            
            print(f"Extracted {len(job_summaries)} job summaries using new approach")
            
            # Method 2: Use the complete pipeline orchestrator
            all_jobs = await process_jobs_with_scraper(
                scraper=scraper,
                browser=browser,
                page=page,
                company_name="Example Company",
                target_url="https://example.workday.com/jobs",
                max_pages=2,
                use_parallel_processing=True,
                show_loading_bar=True
            )
            
            print(f"Processed {len(all_jobs)} complete jobs using pipeline orchestrator")
            
        finally:
            await browser.close()


async def example_legacy_approach():
    """
    Example of using the legacy approach for backward compatibility.
    """
    print("=== Legacy Approach: Using Selectors Directly ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            # Legacy approach using selectors directly
            job_summaries = await extract_job_summaries_with_selectors(
                page=page,
                job_item_selector="li[data-automation-id='listItem']",
                job_title_selector="a[data-automation-id='jobTitle']",
                job_posted_date_selector="dd[data-automation-id='postedOn']",
                target_url="https://example.workday.com/jobs",
                show_loading_bar=True
            )
            
            print(f"Extracted {len(job_summaries)} job summaries using legacy approach")
            
        finally:
            await browser.close()


async def main():
    """
    Main function demonstrating both approaches.
    """
    print("Job Scraper Refactoring Example")
    print("=" * 50)
    
    # Note: These examples won't actually work without a real Workday site
    # They're just to demonstrate the API changes
    
    print("\nThis example demonstrates the API changes in EIP-001 Task 7:")
    print("1. New approach uses Scraper ABC interface")
    print("2. Legacy approach preserved for backward compatibility")
    print("3. Complete pipeline orchestrator available")
    
    # Uncomment to run actual examples (requires real URLs)
    # await example_new_approach()
    # await example_legacy_approach()


if __name__ == "__main__":
    asyncio.run(main())