# config.py
TARGET_URL = "https://db.wd3.myworkdayjobs.com/en-US/DBWebsite"

# Selectors (These need to be verified and potentially adjusted by inspecting the target page)
# It's highly recommended to use data-automation-id if available and stable
JOB_LIST_SELECTOR = "ul[data-automation-id='jobResults']" # Common for the list container
JOB_ITEM_SELECTOR = "li[class='css-1q2dra3']" # Common for individual job items
JOB_TITLE_SELECTOR = "a[data-automation-id='jobTitle']" # For the job title link
JOB_LOCATION_SELECTOR = "dd[data-automation-id='locations']" # Example, often more complex

# Alternative location: Look for elements with 'location' in their class or data-automation-id
# JOB_LOCATION_SELECTOR_ALT = "[data-automation-id*='location']" # More generic
JOB_POSTED_DATE_SELECTOR = "dd[data-automation-id='postedOn']" # Common, but might be different

# For job detail page
JOB_DESCRIPTION_SELECTOR = "div[data-automation-id='jobPostingDescription']" # Common for description block
JOB_ID_DETAIL_SELECTOR = "span[data-automation-id='jobPostingJobId']" # Job ID on detail page

# Pagination selectors
PAGINATION_CONTAINER_SELECTOR = "nav[aria-label='pagination']"
NEXT_PAGE_BUTTON_SELECTOR = "button[aria-label='next']"
PAGE_NUMBER_SELECTOR = "button[data-uxi-query-id='paginationPageButton']"
# Concurrency settings
JOB_DETAIL_CONCURRENCY = 10