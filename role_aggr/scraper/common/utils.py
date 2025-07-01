from datetime import datetime, timedelta
import re
from dateutil.parser import parse as parse_date


def parse_relative_date(date_str_raw: str) -> str | None:
    """
    Wrapper for IntelligentParser's parse_relative_date method for backward compatibility.
    
    Args:
        date_str_raw (str): Raw date string to parse
        
    Returns:
        str | None: ISO format date string or None if parsing fails
    """
    from .intelligent_parser import IntelligentParser
    parser = IntelligentParser()
    return parser.parse_relative_date(date_str_raw)


def parse_location(location_str_raw: str) -> str:
    """
    Parses a raw location string by removing the "locations" prefix (case-insensitive)
    and stripping leading/trailing whitespace.
    
    Args:
        location_str_raw (str): Raw location string to parse
        
    Returns:
        str: Cleaned location string
    """
    if not location_str_raw:
        return ""

    # Use regex to remove "locations" prefix case-insensitively, with optional whitespace
    cleaned_location = re.sub(r'^locations\s*', '', location_str_raw, flags=re.IGNORECASE)
    return cleaned_location.strip()
