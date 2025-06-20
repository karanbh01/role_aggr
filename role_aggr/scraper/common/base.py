"""
Abstract base classes for the scraper system.

This module defines the core interfaces that all platform-specific scrapers and parsers
must implement to ensure consistency and maintainability across different job board platforms.

The abstract base classes provide a contract for:
- Scraper: Main scraping orchestration and pagination logic
- Parser: Platform-specific data parsing and extraction logic
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from playwright.async_api import Page, Browser


class Scraper(ABC):
    """
    Abstract base class for platform-specific scrapers.
    
    This class defines the interface that all platform scrapers must implement
    to handle job listing pagination, data extraction, and detail fetching.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the scraper with platform-specific configuration.
        
        Args:
            config: Dictionary containing platform-specific selectors and settings
        """
        self.config = config
    
    @abstractmethod
    async def paginate_through_job_listings(
        self,
        page: Page,
        company_name: str,
        target_url: str,
        max_pages: Optional[int] = None,
        show_loading_bar: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Navigate through job listing pages and extract job summaries.
        
        This method handles the pagination logic for the specific platform,
        scrolling through infinite scroll or clicking through paginated results
        to collect all available job summaries.
        
        Args:
            page: Playwright page object for browser interaction
            company_name: Name of the company/job board being scraped
            target_url: Base URL of the job board
            max_pages: Maximum number of pages to scrape (None for all pages)
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            List of job summary dictionaries containing basic job information
            
        Raises:
            PlaywrightTimeoutError: When page navigation or element loading times out
            Exception: For other scraping-related errors
        """
        pass
    
    @abstractmethod
    async def fetch_job_details(
        self,
        page: Page,
        job_url: str,
        show_loading_bar: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch detailed information from a specific job posting page.
        
        This method navigates to individual job detail pages and extracts
        comprehensive job information including description, requirements,
        and other platform-specific details.
        
        Args:
            page: Playwright page object for browser interaction
            job_url: URL of the specific job detail page
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            Dictionary containing detailed job information including:
            - url: The job detail page URL
            - description: Full job description text
            - job_id: Platform-specific job identifier
            - detail_page_title: Job title from the detail page
            - Additional platform-specific fields
            
        Raises:
            PlaywrightTimeoutError: When page navigation or element loading times out
            Exception: For other detail extraction errors
        """
        pass
    
    @abstractmethod
    async def _extract_job_summaries(
        self,
        page: Page,
        target_url: str,
        show_loading_bar: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extract job summary information from the current page.
        
        This is a helper method that extracts basic job information
        (title, URL, location, date) from job listing elements on the current page.
        
        Args:
            page: Playwright page object for browser interaction
            target_url: Base URL for constructing absolute URLs
            show_loading_bar: Whether to display progress indicators
            
        Returns:
            List of job summary dictionaries containing:
            - title: Job title
            - detail_url: URL to the job detail page
            - location_raw: Raw location text from the listing
            - location_parsed: Cleaned/parsed location
            - date_posted_raw: Raw date text from the listing
            - date_posted_parsed: Parsed date in ISO format
            
        Raises:
            Exception: For element extraction or parsing errors
        """
        pass


class Parser(ABC):
    """
    Abstract base class for platform-specific data parsers.
    
    This class defines the interface for parsing and cleaning data extracted
    from job listings, ensuring consistent data formats across platforms.
    """
    
    @abstractmethod
    def parse_date(self, date_str_raw: str) -> Optional[str]:
        """
        Parse platform-specific date strings into standardized ISO format.
        
        Different platforms use various date formats including relative dates
        ("Posted today", "2 days ago") and absolute dates. This method should
        handle all platform-specific variations and return a consistent format.
        
        Args:
            date_str_raw: Raw date string from the job listing
            
        Returns:
            ISO format date string (YYYY-MM-DD) or None if parsing fails
            
        Examples:
            - "Posted today" -> "2024-01-15"
            - "Posted 3 days ago" -> "2024-01-12"
            - "Posted Jan 10, 2024" -> "2024-01-10"
            - Invalid date -> None
        """
        pass
    
    @abstractmethod
    def parse_location(self, location_str_raw: str) -> str:
        """
        Parse and clean location strings from job listings.
        
        Location data often includes prefixes, suffixes, or formatting
        that needs to be cleaned for consistency. This method should
        extract the core location information.
        
        Args:
            location_str_raw: Raw location string from the job listing
            
        Returns:
            Cleaned location string
            
        Examples:
            - "Locations: New York, NY" -> "New York, NY"
            - "Remote - United States" -> "Remote - United States"
            - "" -> ""
        """
        pass
    
    @abstractmethod
    def parse_job_id(self, job_id_raw: str) -> str:
        """
        Parse and extract job ID from platform-specific formats.
        
        Job IDs may be embedded in longer strings or have platform-specific
        prefixes/suffixes that need to be cleaned for storage and comparison.
        
        Args:
            job_id_raw: Raw job ID string from the job detail page
            
        Returns:
            Cleaned job ID string
            
        Examples:
            - "Job ID: 12345" -> "12345"
            - "REQ-2024-001" -> "REQ-2024-001"
            - "" -> ""
        """
        pass


class ScraperFactory(ABC):
    """
    Abstract factory for creating platform-specific scrapers and parsers.
    
    This factory pattern allows for dynamic instantiation of platform-specific
    implementations based on configuration or runtime parameters.
    """
    
    @abstractmethod
    def create_scraper(self, platform: str, config: Dict[str, Any]) -> Scraper:
        """
        Create a platform-specific scraper instance.
        
        Args:
            platform: Platform identifier (e.g., "workday", "greenhouse")
            config: Platform-specific configuration dictionary
            
        Returns:
            Configured scraper instance for the specified platform
            
        Raises:
            ValueError: If the platform is not supported
            ImportError: If the platform module cannot be imported
        """
        pass
    
    @abstractmethod
    def create_parser(self, platform: str) -> Parser:
        """
        Create a platform-specific parser instance.
        
        Args:
            platform: Platform identifier (e.g., "workday", "greenhouse")
            
        Returns:
            Parser instance for the specified platform
            
        Raises:
            ValueError: If the platform is not supported
            ImportError: If the platform module cannot be imported
        """
        pass


class JobData:
    """
    Data class representing standardized job information.
    
    This class provides a consistent structure for job data across all platforms,
    ensuring that regardless of the source platform, job information is stored
    and accessed in a uniform manner.
    """
    
    def __init__(
        self,
        title: str,
        company_name: str,
        location: str,
        date_posted: Optional[str] = None,
        job_id: Optional[str] = None,
        description: Optional[str] = None,
        detail_url: Optional[str] = None,
        job_board_url: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize job data with standardized fields.
        
        Args:
            title: Job title
            company_name: Name of the hiring company
            location: Job location (parsed/cleaned)
            date_posted: Date posted in ISO format (YYYY-MM-DD)
            job_id: Platform-specific job identifier
            description: Full job description
            detail_url: URL to the job detail page
            job_board_url: URL of the job board/listing page
            **kwargs: Additional platform-specific fields
        """
        self.title = title
        self.company_name = company_name
        self.location = location
        self.date_posted = date_posted
        self.job_id = job_id
        self.description = description
        self.detail_url = detail_url
        self.job_board_url = job_board_url
        
        # Store additional platform-specific fields
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert job data to dictionary format.
        
        Returns:
            Dictionary representation of the job data
        """
        return {
            key: value for key, value in self.__dict__.items()
            if not key.startswith('_')
        }
    
    def __repr__(self) -> str:
        """String representation of the job data."""
        return f"JobData(title='{self.title}', company='{self.company_name}', location='{self.location}')"


# Type aliases for better code documentation
JobSummary = Dict[str, Any]  # Basic job information from listing pages
JobDetails = Dict[str, Any]  # Detailed job information from detail pages
PlatformConfig = Dict[str, Any]  # Platform-specific configuration