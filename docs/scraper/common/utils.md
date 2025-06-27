# Common Utils Module Documentation

This document provides an overview of the utility functions found in the [`role_aggr/scraper/common/utils.py`](../../role_aggr/scraper/common/utils.py) file, detailing their purpose and parsing capabilities for job board data.

## Overview

The utils module provides utility functions for parsing and cleaning job board data. These functions handle common data transformation tasks such as date parsing and location cleaning that are needed across different platform implementations.

## Date Parsing Functions

### [`parse_relative_date()`](../../role_aggr/scraper/common/utils.py:5)

**Purpose:** Parses relative date strings commonly found on job boards and converts them to ISO format dates.

**Parameters:**
- `date_str_raw` (str): Raw date string from job listing

**Returns:** ISO format date string (YYYY-MM-DD) or None if parsing fails

**Supported Date Formats:**

#### Relative Dates
- **"Posted Today"** or **"Just Posted"** → Current date
- **"Posted Yesterday"** → Yesterday's date  
- **"Posted X days ago"** → Date X days before current date
- **"Posted X+ days ago"** → Date X days before current date (handles plus notation)

#### Absolute Dates
- **"Posted Jan 10, 2024"** → 2024-01-10
- **"Posted 01/10/2024"** → 2024-01-10
- **Other dateutil-parseable formats** → Corresponding ISO date

**Flow:**
1. **Input Validation:** Returns None for empty/null input
2. **Preprocessing:** Converts to lowercase, strips whitespace, removes "posted on" prefix
3. **Pattern Matching:** Uses regex patterns to identify date format
4. **Relative Date Processing:**
   - "today"/"just posted" → `datetime.now().date().isoformat()`
   - "yesterday" → `(datetime.now() - timedelta(days=1)).date().isoformat()`
   - "X days ago" → `(datetime.now() - timedelta(days=X)).date().isoformat()`
   - "X+ days ago" → `(datetime.now() - timedelta(days=X)).date().isoformat()`
5. **Absolute Date Processing:** Uses `dateutil.parser.parse()` for flexible date parsing
6. **Error Handling:** Returns original string if all parsing attempts fail

**Regex Patterns Used:**
```python
# Standard "X days ago" format
r'posted\s+(\d+)\s+days?\s+ago'

# Plus notation "X+ days ago" format  
r'posted\s*(\d+)\+\s*days?\s*ago'
```

**Example Transformations:**
```python
parse_relative_date("Posted today") → "2024-01-15"
parse_relative_date("Posted 3 days ago") → "2024-01-12"  
parse_relative_date("Posted 30+ days ago") → "2023-12-16"
parse_relative_date("Posted Jan 10, 2024") → "2024-01-10"
parse_relative_date("Invalid date") → "Invalid date"
```

## Location Parsing Functions

### [`parse_location()`](../../role_aggr/scraper/common/utils.py:40)

**Purpose:** Cleans and standardizes location strings by removing common prefixes and normalizing whitespace.

**Parameters:**
- `location_str_raw` (str): Raw location string from job listing

**Returns:** Cleaned location string

**Cleaning Operations:**
1. **Input Validation:** Returns empty string for empty/null input
2. **Prefix Removal:** Removes "locations" prefix (case-insensitive) using regex
3. **Whitespace Normalization:** Strips leading and trailing whitespace

**Regex Pattern:**
```python
r'^locations\s*'  # Matches "locations" at start with optional whitespace
```

**Example Transformations:**
```python
parse_location("Locations: New York, NY") → "New York, NY"
parse_location("LOCATIONS   London, UK") → "London, UK"  
parse_location("locations:San Francisco, CA") → "San Francisco, CA"
parse_location("Remote - United States") → "Remote - United States"
parse_location("") → ""
```

## Implementation Details

### Date Parsing Robustness

**Multi-Stage Approach:**
1. **Quick Pattern Matching:** Fast regex-based detection for common patterns
2. **Fallback Parsing:** Uses `dateutil.parser` for complex date formats
3. **Error Recovery:** Returns original string instead of crashing on parse failures

**Date Calculation Accuracy:**
- Uses `datetime.now()` for current date baseline
- Applies `timedelta` for accurate date arithmetic
- Converts to ISO format for database compatibility

**Timezone Considerations:**
- Uses local system time for "today" calculations
- No timezone conversion (assumes same timezone as job board)
- ISO date format is timezone-neutral (date only)

### Location Parsing Strategy

**Case-Insensitive Matching:**
- Uses `re.IGNORECASE` flag for prefix removal
- Handles various capitalization patterns from different job boards

**Whitespace Handling:**
- Regex accounts for optional whitespace after "locations" prefix
- Final `.strip()` removes any remaining leading/trailing whitespace

## Error Handling

### Date Parsing Errors

**Exception Types Handled:**
- **dateutil.parser.ParserError:** Invalid date format
- **ValueError:** Invalid date values
- **TypeError:** Non-string input to dateutil
- **AttributeError:** Missing date components

**Error Recovery Strategy:**
```python
try:
    return parse_date(cleaned_date_str).date().isoformat()
except Exception:
    return date_str_raw  # Return original if parsing fails
```

### Location Parsing Errors

**Robust Input Handling:**
- Handles None/empty input gracefully
- Regex operations are safe for all string inputs
- No exceptions expected for string operations

## Dependencies

### External Libraries

**datetime:** Core Python datetime functionality
- `datetime`: For current date/time operations
- `timedelta`: For date arithmetic

**re:** Regular expression operations
- Pattern matching for date formats
- Case-insensitive location prefix removal

**dateutil.parser:** Advanced date parsing
- `parse`: Flexible date string parsing
- Handles many international date formats

### Internal Dependencies

**None:** This utility module is designed to be self-contained with no internal dependencies to avoid circular imports.

## Usage Examples

### Date Parsing Usage

```python
from role_aggr.scraper.common.utils import parse_relative_date

# Relative dates
today_iso = parse_relative_date("Posted today")
yesterday_iso = parse_relative_date("Posted yesterday") 
week_ago_iso = parse_relative_date("Posted 7 days ago")
month_plus_iso = parse_relative_date("Posted 30+ days ago")

# Absolute dates
formatted_date = parse_relative_date("Posted on January 15, 2024")
slash_date = parse_relative_date("Posted 01/15/2024")

# Invalid dates
original_text = parse_relative_date("Some invalid date text")
```

### Location Parsing Usage

```python
from role_aggr.scraper.common.utils import parse_location

# Common prefix removal
clean_location = parse_location("Locations: San Francisco, CA")
# Result: "San Francisco, CA"

# Case variations
clean_location2 = parse_location("LOCATIONS New York, NY")  
# Result: "New York, NY"

# No prefix
clean_location3 = parse_location("Remote - Worldwide")
# Result: "Remote - Worldwide"
```

### Integration with Parser Classes

```python
from role_aggr.scraper.common.utils import parse_relative_date, parse_location

class MyJobParser:
    def parse_job_data(self, raw_data):
        return {
            'title': raw_data['title'],
            'location': parse_location(raw_data['location_raw']),
            'date_posted': parse_relative_date(raw_data['date_raw']),
            'description': raw_data['description']
        }
```

## Performance Considerations

### Date Parsing Performance

**Optimization Strategy:**
- Regex matching before expensive dateutil parsing
- Early returns for common patterns ("today", "yesterday")
- Single-pass string preprocessing

**Performance Order:**
1. **Fastest:** Direct string matching for "today"/"yesterday"
2. **Fast:** Regex pattern matching for "X days ago"
3. **Slower:** dateutil parsing for complex formats

### Location Parsing Performance

**Efficient Operations:**
- Single regex operation for prefix removal
- Minimal string operations
- No expensive parsing or calculations

## Extension Possibilities

### Additional Date Formats

**Potential Extensions:**
```python
# Week-based relative dates
"Posted last week" → 7 days ago
"Posted 2 weeks ago" → 14 days ago

# Month-based relative dates  
"Posted last month" → 30 days ago
"Posted 2 months ago" → 60 days ago
```

### Advanced Location Parsing

**Potential Enhancements:**
```python
# State/country extraction
"New York, NY, USA" → {"city": "New York", "state": "NY", "country": "USA"}

# Remote work detection
"Remote - USA" → {"type": "remote", "region": "USA"}

# Multiple location handling
"New York, NY; San Francisco, CA" → ["New York, NY", "San Francisco, CA"]
```

## Testing Recommendations

### Date Parsing Test Cases

```python
# Relative dates
assert parse_relative_date("Posted today") == datetime.now().date().isoformat()
assert parse_relative_date("Posted 5 days ago") == (datetime.now() - timedelta(days=5)).date().isoformat()

# Absolute dates
assert parse_relative_date("Posted Jan 15, 2024") == "2024-01-15"

# Edge cases
assert parse_relative_date("") is None
assert parse_relative_date("Invalid") == "Invalid"
```

### Location Parsing Test Cases

```python
# Prefix removal
assert parse_location("Locations: NYC") == "NYC"
assert parse_location("LOCATIONS   Boston") == "Boston"

# No change needed
assert parse_location("Remote Work") == "Remote Work"

# Edge cases  
assert parse_location("") == ""
assert parse_location("   ") == ""