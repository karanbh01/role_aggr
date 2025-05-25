# utils.py
from datetime import datetime, timedelta
import re
from dateutil.parser import parse as parse_date # For robust date parsing

def parse_relative_date(date_str_raw: str) -> str | None:
    """
    Parses relative date strings like "Posted Today", "Posted Yesterday", "Posted X days ago"
    and attempts to convert more specific dates.
    Returns an ISO format date string or None.
    """
    if not date_str_raw:
        return None
    
    date_str = date_str_raw.lower().strip().replace("posted on", "")

    try:
        if "posted today" in date_str or "just posted" in date_str:
            return datetime.now().date().isoformat()
        if "posted yesterday" in date_str:
            return (datetime.now() - timedelta(days=1)).date().isoformat()
        
        days_ago_match = re.search(r'posted\s+(\d+)\s+days?\s+ago', date_str)
        if days_ago_match:
            days = int(days_ago_match.group(1))
            return (datetime.now() - timedelta(days=days)).date().isoformat()

        plus_days_ago_match = re.search(r'posted\s*(\d+)\+\s*days?\s*ago', date_str)
        if plus_days_ago_match:
            days = int(plus_days_ago_match.group(1))
            return (datetime.now() - timedelta(days=days)).date().isoformat()
        
        # Try parsing with dateutil for formats like "Posted Jan 10, 2024" or "Posted 01/10/2024"
        # Remove "Posted " prefix for better parsing
        cleaned_date_str = date_str.replace("posted ", "")
        return parse_date(cleaned_date_str).date().isoformat()
    except Exception:
        # print(f"Could not parse date: {date_str_raw}")
        return date_str_raw # Return original if parsing fails, or None

def parse_location(location_str_raw: str) -> str:
    """
    Parses a raw location string by removing the "locations" prefix (case-insensitive)
    and stripping leading/trailing whitespace.
    """
    if not location_str_raw:
        return ""
    
    # Use regex to remove "locations" prefix case-insensitively, with optional whitespace
    cleaned_location = re.sub(r'^locations\s*', '', location_str_raw, flags=re.IGNORECASE)
    return cleaned_location.strip()

def conditional_print(message: str, show_loading_bar: bool = False) -> None:
    """
    Prints the message only if show_loading_bar is False.
    Useful for providing detailed output when progress bars are disabled.
    """
    if not show_loading_bar:
        print(message)