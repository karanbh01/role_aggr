"""
Workday-specific parser implementation.

This module provides the WorkdayParser class that implements the Parser interface
for parsing job data from Workday job boards. It handles Workday-specific date formats,
location strings, job IDs, and Playwright-based HTML element extraction.
"""

from datetime import datetime, timedelta
import re
from typing import Optional, Dict, Any
from dateutil.parser import parse as parse_date
from playwright.async_api import Page

from role_aggr.scraper.common.base import Parser, JobData
from role_aggr.scraper.common.logging import setup_scraper_logger
from .config import (
    JOB_TITLE_SELECTOR,
    JOB_LOCATION_SELECTOR,
    JOB_POSTED_DATE_SELECTOR,
    JOB_DESCRIPTION_SELECTOR,
    JOB_ID_DETAIL_SELECTOR
)

logger = setup_scraper_logger()


class WorkdayParser(Parser):
    """
    Workday-specific implementation of the Parser interface.
    
    This parser handles the specific HTML structure and data formats used by
    Workday job boards, including relative date parsing, location cleaning,
    and job ID extraction using Playwright for HTML element access.
    """
    
    def parse_date(self, date_str_raw: str) -> Optional[str]:
        """
        Parse Workday-specific date strings into standardized ISO format.
        
        Handles various Workday date formats including:
        - Relative dates: "Posted today", "Posted yesterday", "Posted X days ago"
        - Absolute dates: "Posted Jan 10, 2024", "Posted 01/10/2024"
        - Plus notation: "Posted 30+ days ago"
        
        Args:
            date_str_raw: Raw date string from Workday job listing
            
        Returns:
            ISO format date string (YYYY-MM-DD) or None if parsing fails
        """
        if not date_str_raw:
            return None
        
        date_str = date_str_raw.lower().strip().replace("posted on", "")
        
        try:
            if "posted today" in date_str or "just posted" in date_str:
                return datetime.now().date().isoformat()
            if "posted yesterday" in date_str:
                return (datetime.now() - timedelta(days=1)).date().isoformat()
            
            # Handle "X days ago" format
            days_ago_match = re.search(r'posted\s+(\d+)\s+days?\s+ago', date_str)
            if days_ago_match:
                days = int(days_ago_match.group(1))
                return (datetime.now() - timedelta(days=days)).date().isoformat()
            
            # Handle "X+ days ago" format
            plus_days_ago_match = re.search(r'posted\s*(\d+)\+\s*days?\s*ago', date_str)
            if plus_days_ago_match:
                days = int(plus_days_ago_match.group(1))
                return (datetime.now() - timedelta(days=days)).date().isoformat()
            
            # Try parsing absolute dates with dateutil
            cleaned_date_str = date_str.replace("posted ", "")
            return parse_date(cleaned_date_str).date().isoformat()
            
        except Exception as e:
            logger.warning(f"Could not parse date '{date_str_raw}': {e}")
            return None
    
    def parse_location(self, location_str_raw: str) -> str:
        """
        Parse and clean Workday location strings.
        
        Removes Workday-specific prefixes like "Locations:" and cleans
        whitespace to extract the core location information.
        
        Args:
            location_str_raw: Raw location string from Workday job listing
            
        Returns:
            Cleaned location string
        """
        if not location_str_raw:
            return ""
        
        # Remove "locations" prefix case-insensitively with optional whitespace and colon
        cleaned_location = re.sub(r'^\s*locations\s*:?\s*', '', location_str_raw, flags=re.IGNORECASE)
        return cleaned_location.strip()
    
    def parse_job_id(self, job_id_raw: str) -> str:
        """
        Parse and extract job ID from Workday-specific formats.
        
        Workday job IDs may have prefixes or be embedded in longer strings.
        This method extracts the core job identifier.
        
        Args:
            job_id_raw: Raw job ID string from Workday job detail page
            
        Returns:
            Cleaned job ID string
        """
        if not job_id_raw:
            return ""
        
        # Remove common Workday job ID prefixes
        job_id = job_id_raw.strip()
        
        # Remove "Job ID:" prefix if present
        job_id = re.sub(r'^job\s*id\s*:?\s*', '', job_id, flags=re.IGNORECASE)
        
        # Remove "REQ-" prefix if present (common Workday format)
        job_id = re.sub(r'^req-?', '', job_id, flags=re.IGNORECASE)
        
        return job_id.strip()
    
    async def parse_job_summary(self, page: Page, base_url: str = "") -> Optional[JobData]:
        """
        Parse job summary data from Workday page using Playwright.
        
        Extracts comprehensive job information from Workday job listing or detail
        page using Playwright's element selection and text extraction methods.
        
        Args:
            page: Playwright page object containing the job listing/detail
            base_url: Base URL for constructing absolute URLs
            
        Returns:
            JobData object with parsed information or None if parsing fails
        """
        if not page:
            logger.warning("No page provided for job summary parsing")
            return None
        
        try:
            # Extract job title
            title_element = await page.query_selector(JOB_TITLE_SELECTOR)
            title = await title_element.inner_text() if title_element else ""
            
            # Extract detail URL from title link
            detail_url = ""
            if title_element:
                href = await title_element.get_attribute('href')
                if href:
                    if href.startswith('http'):
                        detail_url = href
                    elif href.startswith('/'):
                        detail_url = base_url.rstrip('/') + href
                    else:
                        detail_url = f"{base_url.rstrip('/')}/{href}"
            
            # Extract and parse location
            location_element = await page.query_selector(JOB_LOCATION_SELECTOR)
            location_raw = await location_element.inner_text() if location_element else ""
            location = self.parse_location(location_raw)
            
            # Extract and parse date posted
            date_element = await page.query_selector(JOB_POSTED_DATE_SELECTOR)
            date_raw = await date_element.inner_text() if date_element else ""
            date_posted = self.parse_date(date_raw)
            
            # Extract job description (if available on detail page)
            description_element = await page.query_selector(JOB_DESCRIPTION_SELECTOR)
            description = await description_element.inner_text() if description_element else ""
            
            # Extract job ID (if available on detail page)
            job_id_element = await page.query_selector(JOB_ID_DETAIL_SELECTOR)
            job_id_raw = await job_id_element.inner_text() if job_id_element else ""
            job_id = self.parse_job_id(job_id_raw)
            
            # Validate required fields
            if not title:
                logger.warning("No job title found on page")
                return None
            
            # Create JobData object
            job_data = JobData(
                title=title.strip(),
                company_name="",  # Company name typically extracted from context
                location=location,
                date_posted=date_posted,
                job_id=job_id,
                description=description.strip() if description else "",
                detail_url=detail_url,
                # Store raw data for debugging
                location_raw=location_raw,
                date_posted_raw=date_raw,
                job_id_raw=job_id_raw
            )
            
            logger.debug(f"Successfully parsed job summary: {job_data.title}")
            return job_data
            
        except Exception as e:
            logger.error(f"Error parsing job summary from page: {e}")
            return None


# Legacy function wrappers for backward compatibility
def parse_relative_date(date_str_raw: str) -> Optional[str]:
    """
    Legacy wrapper for backward compatibility.
    
    Args:
        date_str_raw: Raw date string
        
    Returns:
        Parsed date string or None
    """
    parser = WorkdayParser()
    return parser.parse_date(date_str_raw)


def parse_location(location_str_raw: str) -> str:
    """
    Legacy wrapper for backward compatibility.
    
    Args:
        location_str_raw: Raw location string
        
    Returns:
        Cleaned location string
    """
    parser = WorkdayParser()
    return parser.parse_location(location_str_raw)