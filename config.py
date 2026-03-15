"""
All configuration in one place. No hierarchical merging, no platform overrides.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# -- Paths ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_FILE = DATABASE_DIR / "jobs.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_FILE}"
CSV_FILE_PATH = BASE_DIR / "role_aggr" / "job_boards.csv"
LOG_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# -- Server -----------------------------------------------------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# -- Scraping ---------------------------------------------------------------
MAX_CONCURRENT_DETAILS = int(os.getenv("MAX_CONCURRENT_DETAILS", "10"))
BROWSER_TIMEOUT_MS = 60_000
ELEMENT_TIMEOUT_MS = 10_000
PAGE_DELAY_MS = 2_000

# -- Intelligent location parsing (optional) --------------------------------
ENABLE_INTELLIGENT_PARSING = os.getenv("ENABLE_INTELLIGENT_PARSING", "").lower() in ("true", "1", "yes")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
INTELLIGENT_PARSER_MODEL = os.getenv("INTELLIGENT_PARSER_MODEL", "google/gemini-2.5-flash")

# -- Workday selectors ------------------------------------------------------
WORKDAY_SELECTORS = {
    "job_list":       "[data-automation-id='jobResults']",
    "job_item":       "li[class='css-1q2dra3']",
    "job_title":      "a[data-automation-id='jobTitle']",
    "job_location":   "[data-automation-id='locations']",
    "job_date":       "[data-automation-id='postedOn']",
    "description":    "div[data-automation-id='jobPostingDescription']",
    "job_id":         "span[data-automation-id='jobPostingJobId']",
    "job_id_fallback":"span:has-text('Job Id:') + span",
    "title_header":   "h1[data-automation-id='jobPostingHeader']",
    "pagination":     "nav[aria-label='pagination']",
    "next_page":      "button[aria-label='next']",
}

# -- Platform registry ------------------------------------------------------
SUPPORTED_PLATFORMS = {"workday", "linkedin"}

# -- Logging ----------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
