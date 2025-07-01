from __future__ import annotations
import os
import asyncio
import logging
import time
import json
import re
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from typing import List, Dict, Any
import openai
from .logging import setup_scraper_logger


class IntelligentParser:
    """
    IntelligentParser core class for EIP-002 enhancement.

    Provides location parsing capabilities and job data enhancements using the OpenRouter API.
    Also handles date parsing functionality migrated from utils.py.
    """

    SYSTEM_PROMPT = (
        "You are a location parsing expert. Parse location strings into structured data with city, country, and region fields. Always respond with valid JSON.\n\n"
        "Rules:\n"
        "- Extract city, country, and region\n"
        "- Use \"Remote\" for region if location indicates remote work\n"
        "- Use full country names (e.g., \"United States\", not \"US\")\n"
        "- If uncertain, use \"Unknown\" for that field\n"
        "- For region, the values should be Americas (for countries in north and south america), Europe, Asia, Oceanea, etc. extrapolate the region based on the country\n"
        "- Confidence score: 0.1-1.0 based on clarity of input\n\n"
        "For single location:\n"
        "{\"city\": \"string\", \"country\": \"string\", \"region\": \"string\", \"confidence\": float}\n\n"
        "For multiple locations, return an array:\n"
        "[{\"city\": \"string\", \"country\": \"string\", \"region\": \"string\", \"confidence\": float}, ...]"
    )

    def __init__(self, api_key: str = None, model: str = "google/gemini-2.5-flash") -> None:
        """
        Initialize the IntelligentParser.

        Args:
            api_key (str, optional): API key for OpenRouter API. Defaults to value from OPENROUTER_API_KEY environment variable.
            model (str, optional): Model identifier. Defaults to "google/gemini-2.5-pro".
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
        self.timeout = 30  # seconds per request
        self.max_retries = 3
        self.cache = {}
        self.logger = setup_scraper_logger()

    def parse_relative_date(self, date_str_raw: str) -> str | None:
        """
        Parses relative date strings like "Posted Today", "Posted Yesterday", "Posted X days ago"
        and attempts to convert more specific dates.
        
        This method migrates the original logic from utils.py with enhanced error handling
        and logging capabilities.
        
        Args:
            date_str_raw (str): Raw date string to parse
            
        Returns:
            str | None: ISO format date string or None if parsing fails
        """
        if not date_str_raw:
            self.logger.debug("Empty date string provided")
            return None

        date_str = date_str_raw.lower().strip().replace("posted on", "")
        self.logger.debug(f"Parsing date string: '{date_str_raw}' -> '{date_str}'")

        try:
            # Handle "today" variations
            if "posted today" in date_str or "just posted" in date_str:
                result = datetime.now().date().isoformat()
                self.logger.debug(f"Parsed as today: {result}")
                return result
            
            # Handle "yesterday" variations
            if "posted yesterday" in date_str:
                result = (datetime.now() - timedelta(days=1)).date().isoformat()
                self.logger.debug(f"Parsed as yesterday: {result}")
                return result

            # Handle "X days ago" patterns
            days_ago_match = re.search(r'posted\s+(\d+)\s+days?\s+ago', date_str)
            if days_ago_match:
                days_ago = int(days_ago_match.group(1))
                result = (datetime.now() - timedelta(days=days_ago)).date().isoformat()
                self.logger.debug(f"Parsed as {days_ago} days ago: {result}")
                return result

            # Handle "X+ days ago" patterns
            plus_days_ago_match = re.search(r'posted\s*(\d+)\+\s*days?\s*ago', date_str)
            if plus_days_ago_match:
                days = int(plus_days_ago_match.group(1))
                result = (datetime.now() - timedelta(days=days)).date().isoformat()
                self.logger.debug(f"Parsed as {days}+ days ago: {result}")
                return result

            # Try parsing with dateutil for formats like "Posted Jan 10, 2024" or "Posted 01/10/2024"
            # Remove "Posted " prefix for better parsing
            cleaned_date_str = date_str.replace("posted ", "").strip()
            if cleaned_date_str:
                result = parse_date(cleaned_date_str).date().isoformat()
                self.logger.debug(f"Parsed with dateutil: {result}")
                return result
                
        except Exception as e:
            self.logger.error(f"Error parsing relative date '{date_str_raw}': {e}")
            
        self.logger.warning(f"Could not parse date: '{date_str_raw}'")
        return None

    def _clean_json_response(self, response_text: str) -> str:
        """
        Clean the LLM response to extract JSON from markdown code blocks.
        
        Args:
            response_text (str): Raw response from LLM
            
        Returns:
            str: Cleaned JSON string
        """
        # Remove markdown code block formatting
        if "```json" in response_text:
            # Extract content between ```json and ```
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                return response_text[start:end].strip()
        elif "```" in response_text:
            # Extract content between ``` and ```
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                return response_text[start:end].strip()
        
        # If no code blocks, return as is
        return response_text.strip()

    async def _make_llm_request(self, prompt: str, max_retries: int = 3) -> dict:
        """
        Make an asynchronous request to the LLM with retry logic and exponential backoff.
    
        Args:
            prompt (str): Prompt to send to the language model.
            max_retries (int, optional): Maximum number of retries. Defaults to 3.
    
        Returns:
            dict: Parsed JSON response from the language model.
        """
        if not self.api_key:
            self.logger.warning("No API key provided, using fallback parsing")
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
            
        attempt = 0
        backoff = 1
        while attempt < max_retries:
            try:
                # Use modern OpenAI API client
                client = openai.AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout
                )
                
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ]
                )
                print(response.choices[0].message.content)

                response_text = response.choices[0].message.content.strip()
                self.logger.debug(f"Raw LLM response: '{response_text}'")
                
                if not response_text:
                    self.logger.error("Empty response from LLM")
                    raise ValueError("Empty response from LLM")
                
                # Clean the response text to handle markdown code blocks
                cleaned_response = self._clean_json_response(response_text)
                self.logger.debug(f"Cleaned response: '{cleaned_response}'")
                
                parsed_response = json.loads(cleaned_response)
                
                # Handle both single location and batch responses
                if isinstance(parsed_response, list):
                    # Batch response - validate each item
                    if all(isinstance(item, dict) and all(key in item for key in ["city", "country", "region", "confidence"]) for item in parsed_response):
                        self.logger.debug(f"LLM batch request successful: {len(parsed_response)} locations")
                        return parsed_response
                    else:
                        self.logger.error(f"Invalid batch response format: {parsed_response}")
                elif isinstance(parsed_response, dict):
                    # Single response
                    if all(key in parsed_response for key in ["city", "country", "region", "confidence"]):
                        self.logger.debug(f"LLM request successful: {parsed_response}")
                        return parsed_response
                    else:
                        self.logger.error(f"Invalid response format: {parsed_response}")
                else:
                    self.logger.error(f"Unexpected response type: {type(parsed_response)}")
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response: {e}")
            except Exception as e:
                self.logger.error(f"LLM request failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    await asyncio.sleep(backoff)
                    backoff *= 2
                attempt += 1
                
        self.logger.error("Max retries exceeded for LLM request.")
        return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}

    async def _parse_location_llm(self, location_raw: str) -> dict:
        """
        Parse location using LLM with proper prompt formatting.
        
        Args:
            location_raw (str): Raw location string to parse
            
        Returns:
            dict: Standardized location dict with city, country, region, confidence
        """
        try:
            user_prompt = f"Parse this location: {location_raw}"
            self.logger.debug(f"Sending location to LLM: '{location_raw}'")
            
            response = await self._make_llm_request(user_prompt)
            
            # Validate response has required keys
            if all(key in response for key in ["city", "country", "region", "confidence"]):
                self.logger.debug(f"LLM parsed location successfully: {response}")
                return response
            else:
                self.logger.error(f"LLM response missing required keys: {response}")
                return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
                
        except Exception as e:
            self.logger.error(f"Error in LLM location parsing: {e}")
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}

    async def _parse_locations_llm_batch(self, locations: List[str]) -> List[dict]:
        """
        Parse multiple locations using LLM in a single API call.
        
        Args:
            locations (List[str]): List of location strings to parse
            
        Returns:
            List[dict]: List of standardized location dicts
        """
        if not locations:
            return []
            
        try:
            # Create batch prompt
            numbered_locations = [f"{i+1}. {loc}" for i, loc in enumerate(locations)]
            locations_text = "\n".join(numbered_locations)
            user_prompt = f"Parse these locations:\n{locations_text}"
            
            self.logger.debug(f"Sending {len(locations)} locations to LLM in batch")
            
            response = await self._make_llm_request(user_prompt)
            
            # Handle the response - it should be a list or we need to extract a list
            if isinstance(response, list):
                results = response
            elif isinstance(response, dict) and 'locations' in response:
                results = response['locations']
            else:
                # If single response returned, wrap in list
                results = [response] if 'city' in response else []
            
            # Validate and pad results to match input length
            validated_results = []
            for i, location in enumerate(locations):
                if i < len(results) and isinstance(results[i], dict):
                    result = results[i]
                    if all(key in result for key in ["city", "country", "region", "confidence"]):
                        validated_results.append(result)
                    else:
                        self.logger.warning(f"Invalid LLM result for '{location}': {result}")
                        validated_results.append({"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0})
                else:
                    self.logger.warning(f"Missing LLM result for '{location}'")
                    validated_results.append({"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0})
            
            self.logger.debug(f"LLM batch parsing completed: {len(validated_results)} results")
            return validated_results
                
        except Exception as e:
            self.logger.error(f"Error in batch LLM location parsing: {e}")
            # Return fallback results for all locations
            return [{"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0} for _ in locations]

    def _get_cache_key(self, location: str) -> str:
        """
        Generate a cache key based on a location string.

        Args:
            location (str): The location string.

        Returns:
            str: Cache key.
        """
        return f"loc::{location.lower().strip()}"

    def _parse_location_fallback(self, location_raw: str) -> dict:
        """
        Fallback using existing parse_location from utils.
        
        Args:
            location_raw (str): Raw location string to parse
            
        Returns:
            dict: Standardized location dict using fallback method
        """
        try:
            from .utils import parse_location
            cleaned_location = parse_location(location_raw)
            self.logger.debug(f"Fallback parsed location: '{location_raw}' -> '{cleaned_location}'")
            return {
                "city": cleaned_location,
                "country": "Unknown",
                "region": "Unknown",
                "confidence": 0.1
            }
        except Exception as e:
            self.logger.error(f"Error in fallback location parsing: {e}")
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}

    async def parse_location_single(self, location: str) -> dict:
        """
        Parse single location with cache, LLM, and fallback.
        
        Args:
            location (str): The location string to parse.
            
        Returns:
            dict: Parsed location data with standardized format
        """
        if not location:
            self.logger.debug("Empty location string provided")
            return {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
        
        # 1. Cache lookup using self._get_cache_key(location)
        cache_key = self._get_cache_key(location)
        if cache_key in self.cache:
            self.logger.debug(f"Cache hit for location: '{location}'")
            return self.cache[cache_key]
        
        try:
            # 2. LLM attempt with confidence threshold (0.5)
            llm_result = await self._parse_location_llm(location)
            
            if llm_result.get("confidence", 0.0) >= 0.5:
                self.logger.debug(f"LLM result meets confidence threshold: {llm_result}")
                result = llm_result
            else:
                # 3. Fallback attempt if LLM insufficient
                self.logger.info(f"LLM confidence too low ({llm_result.get('confidence', 0.0)}), using fallback")
                result = self._parse_location_fallback(location)
                
        except Exception as e:
            self.logger.error(f"Error in LLM parsing for '{location}': {e}")
            result = self._parse_location_fallback(location)
        
        # 4. Cache successful results
        self.cache[cache_key] = result
        self.logger.debug(f"Cached result for '{location}': {result}")
        
        return result

    async def parse_locations_batch(self, locations: List[str]) -> List[dict]:
        """
        Process multiple locations efficiently using batch LLM processing with fallback.
        
        Args:
            locations (List[str]): List of location strings to parse.
            
        Returns:
            List[dict]: List of parsed location data with error handling.
        """
        if not locations:
            self.logger.debug("Empty locations list provided")
            return []
            
        self.logger.info(f"Processing batch of {len(locations)} locations")
        
        # Check cache first for all locations
        cache_results = {}
        uncached_locations = []
        uncached_indices = []
        
        for i, location in enumerate(locations):
            cache_key = self._get_cache_key(location)
            if cache_key in self.cache:
                cache_results[i] = self.cache[cache_key]
                self.logger.debug(f"Cache hit for location '{location}'")
            else:
                uncached_locations.append(location)
                uncached_indices.append(i)
        
        # Process uncached locations with batch LLM if any
        llm_results = []
        if uncached_locations:
            self.logger.info(f"Processing {len(uncached_locations)} uncached locations with batch LLM")
            try:
                # Try batch LLM processing first
                llm_results = await self._parse_locations_llm_batch(uncached_locations)
                
                # Filter results by confidence threshold
                for i, (location, result) in enumerate(zip(uncached_locations, llm_results)):
                    if result.get("confidence", 0.0) < 0.5:
                        self.logger.info(f"LLM confidence too low for '{location}', using fallback")
                        llm_results[i] = self._parse_location_fallback(location)
                    
                    # Cache the result
                    cache_key = self._get_cache_key(location)
                    self.cache[cache_key] = llm_results[i]
                    
            except Exception as e:
                self.logger.error(f"Batch LLM processing failed: {e}, using fallback for all")
                llm_results = [self._parse_location_fallback(loc) for loc in uncached_locations]
                
                # Cache fallback results
                for location, result in zip(uncached_locations, llm_results):
                    cache_key = self._get_cache_key(location)
                    self.cache[cache_key] = result
        
        # Combine cached and new results in original order
        final_results = []
        llm_index = 0
        
        for i in range(len(locations)):
            if i in cache_results:
                final_results.append(cache_results[i])
            else:
                final_results.append(llm_results[llm_index])
                llm_index += 1
        
        self.logger.info(f"Completed batch processing: {len(final_results)} results ({len(cache_results)} cached, {len(llm_results)} processed)")
        return final_results

    async def enhance_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance job data with intelligent location parsing.
        
        Args:
            job_data (Dict[str, Any]): Original job data.
            
        Returns:
            Dict[str, Any]: Job data enhanced with parsed location information.
        """
        try:
            location_raw = job_data.get("location", "")
            if not location_raw:
                self.logger.warning("No location found in job data.")
                return job_data
            
            # Replace _make_llm_request call with parse_location_single
            # Ensure full parsing pipeline is used
            parsed_location = await self.parse_location_single(location_raw)
            job_data["parsed_location"] = parsed_location
            
            self.logger.debug(f"Enhanced job data with location: {parsed_location}")
            return job_data
            
        except Exception as e:
            self.logger.error(f"Failed to enhance job data: {e}")
            # Return original job data with error indication
            job_data["parsed_location"] = {"city": "Unknown", "country": "Unknown", "region": "Unknown", "confidence": 0.0}
            return job_data