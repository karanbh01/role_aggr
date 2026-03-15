from .workday import scrape_workday
from .linkedin import scrape_linkedin

# Plain dict mapping platform names to scraper functions.
# This is the entire "factory pattern" replacement.
SCRAPERS = {
    "workday": scrape_workday,
    "linkedin": scrape_linkedin,
}
