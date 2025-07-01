"""
Batch Processing Manager for EIP-002 Phase 4 Implementation

This module provides optimized batch processing capabilities for the IntelligentParser
integration into the scraping pipeline, ensuring minimal LLM API calls per scraper run.
"""

import asyncio
from typing import List, Dict, Any, Set, Optional
from .intelligent_parser import IntelligentParser
from .config import ENABLE_INTELLIGENT_PARSING, OPENROUTER_API_KEY, INTELLIGENT_PARSER_LLM
from .logging import setup_scraper_logger

logger = setup_scraper_logger()


class BatchLocationProcessor:
    """
    Manages batch processing of locations for optimal LLM efficiency.
    
    Collects unique locations from all jobs in a scraper run, processes them
    in a single batch LLM call, and provides a cache for individual job processing.
    """
    
    def __init__(self, intelligent_parser: Optional[IntelligentParser] = None):
        """
        Initialize the batch processor.
        
        Args:
            intelligent_parser (Optional[IntelligentParser]): Pre-configured parser instance.
                If None, creates a new instance based on configuration.
        """
        self.intelligent_parser = intelligent_parser
        self.location_cache: Dict[str, Dict[str, Any]] = {}
        self.processed_locations: Set[str] = set()
        self.enabled = ENABLE_INTELLIGENT_PARSING
        
        logger.info(f"BatchLocationProcessor initialized - Intelligent parsing enabled: {self.enabled}")
        
        # Initialize parser if enabled and not provided
        if self.enabled and not self.intelligent_parser:
            try:
                self.intelligent_parser = IntelligentParser(
                    api_key=OPENROUTER_API_KEY,
                    model=INTELLIGENT_PARSER_LLM
                )
                logger.info("IntelligentParser instance created for batch processing")
            except Exception as e:
                logger.error(f"Failed to initialize IntelligentParser: {e}")
                self.enabled = False
    
    def extract_unique_locations(self, job_summaries: List[Dict[str, Any]]) -> List[str]:
        """
        Extract unique location strings from job summaries.
        
        Args:
            job_summaries (List[Dict[str, Any]]): List of job summary dictionaries
            
        Returns:
            List[str]: List of unique location strings
        """
        unique_locations = set()
        
        for job in job_summaries:
            # Try different possible location field names
            location = (
                job.get("location_raw") or 
                job.get("location") or 
                job.get("location_parsed", "")
            )
            
            if location and isinstance(location, str) and location.strip() and location != "N/A":
                unique_locations.add(location.strip())
        
        unique_list = list(unique_locations)
        logger.info(f"Extracted {len(unique_list)} unique locations from {len(job_summaries)} job summaries")
        return unique_list
    
    async def process_unique_locations_batch(self, unique_locations: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Process unique locations in a single batch LLM call.
        
        Args:
            unique_locations (List[str]): List of unique location strings
            
        Returns:
            Dict[str, Dict[str, Any]]: Mapping from location string to parsed location data
        """
        if not self.enabled or not self.intelligent_parser:
            logger.info("Intelligent parsing disabled, skipping batch processing")
            return {}
        
        if not unique_locations:
            logger.info("No unique locations to process")
            return {}
        
        logger.info(f"Processing {len(unique_locations)} unique locations in batch")
        
        try:
            # Use the existing batch processing method from IntelligentParser
            parsed_results = await self.intelligent_parser.parse_locations_batch(unique_locations)
            
            # Create mapping from location string to parsed data
            location_mapping = {}
            for location, result in zip(unique_locations, parsed_results):
                location_mapping[location] = result
                self.processed_locations.add(location)
            
            # Update internal cache
            self.location_cache.update(location_mapping)
            
            logger.info(f"Successfully processed {len(location_mapping)} locations in batch")
            return location_mapping
            
        except Exception as e:
            logger.error(f"Batch location processing failed: {e}")
            return {}
    
    def get_cached_location(self, location_raw: str) -> Optional[Dict[str, Any]]:
        """
        Get cached location data for a given location string.
        
        Args:
            location_raw (str): Raw location string
            
        Returns:
            Optional[Dict[str, Any]]: Cached location data or None if not found
        """
        if not location_raw or not isinstance(location_raw, str):
            return None
            
        location_key = location_raw.strip()
        return self.location_cache.get(location_key)
    
    async def get_location_data(self, location_raw: str) -> Dict[str, Any]:
        """
        Get location data with fallback to individual processing if not cached.
        
        Args:
            location_raw (str): Raw location string
            
        Returns:
            Dict[str, Any]: Parsed location data
        """
        if not location_raw or not isinstance(location_raw, str):
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
        
        # Check cache first
        cached_result = self.get_cached_location(location_raw)
        if cached_result:
            logger.debug(f"Cache hit for location: '{location_raw}'")
            return cached_result
        
        # If not in cache and intelligent parsing is enabled, process individually
        if self.enabled and self.intelligent_parser:
            try:
                logger.debug(f"Processing individual location: '{location_raw}'")
                result = await self.intelligent_parser.parse_location_single(location_raw)
                # Cache for future use
                self.location_cache[location_raw.strip()] = result
                return result
            except Exception as e:
                logger.error(f"Individual location processing failed for '{location_raw}': {e}")
        
        # Fallback to basic parsing
        logger.debug(f"Using fallback parsing for: '{location_raw}'")
        try:
            from .utils import parse_location
            cleaned_location = parse_location(location_raw)
            return {
                "city": cleaned_location,
                "country": "Unknown", 
                "region": "Unknown",
                "confidence": 0.1
            }
        except Exception as e:
            logger.error(f"Fallback parsing failed for '{location_raw}': {e}")
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns:
            Dict[str, Any]: Processing statistics
        """
        return {
            "enabled": self.enabled,
            "cached_locations": len(self.location_cache),
            "processed_locations": len(self.processed_locations),
            "has_parser": self.intelligent_parser is not None
        }


class BatchJobProcessor:
    """
    Orchestrates batch processing for complete job data enhancement.
    
    Coordinates the batch location processing and applies results to individual jobs.
    """
    
    def __init__(self):
        """Initialize the batch job processor."""
        self.location_processor = BatchLocationProcessor()
        
    async def prepare_batch_cache(self, job_summaries: List[Dict[str, Any]]) -> None:
        """
        Prepare batch cache by processing all unique locations.
        
        Args:
            job_summaries (List[Dict[str, Any]]): List of job summary dictionaries
        """
        if not self.location_processor.enabled:
            logger.info("Batch processing preparation skipped - intelligent parsing disabled")
            return
        
        logger.info("Preparing batch cache for location processing")
        
        # Extract unique locations
        unique_locations = self.location_processor.extract_unique_locations(job_summaries)
        
        # Process in batch
        await self.location_processor.process_unique_locations_batch(unique_locations)
        
        stats = self.location_processor.get_stats()
        logger.info(f"Batch cache preparation complete: {stats}")
    
    async def enhance_job_with_cached_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance job data using cached location results.
        
        Args:
            job_data (Dict[str, Any]): Original job data
            
        Returns:
            Dict[str, Any]: Enhanced job data with parsed location information
        """
        try:
            # Try different possible location field names
            location_raw = (
                job_data.get("location_raw") or 
                job_data.get("location") or 
                ""
            )
            
            if not location_raw or location_raw == "N/A":
                logger.debug("No valid location found in job data")
                job_data["location_parsed_intelligent"] = {
                    "city": "Unknown", 
                    "country": "Unknown", 
                    "region": "Unknown", 
                    "confidence": 0.0
                }
                return job_data
            
            # Get location data (from cache or individual processing)
            parsed_location = await self.location_processor.get_location_data(location_raw)
            
            # Add to job data with a distinct field name to avoid conflicts
            job_data["location_parsed_intelligent"] = parsed_location
            
            logger.debug(f"Enhanced job '{job_data.get('title', 'Unknown')}' with intelligent location data")
            return job_data
            
        except Exception as e:
            logger.error(f"Failed to enhance job data: {e}")
            # Ensure we always add the field, even on error
            job_data["location_parsed_intelligent"] = {
                "city": "Unknown", 
                "country": "Unknown", 
                "region": "Unknown", 
                "confidence": 0.0
            }
            return job_data