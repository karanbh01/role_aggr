# scraper.py - Formatted with date parsing

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urlparse, urljoin
import random
import os
import concurrent.futures
import traceback # For detailed error logging if needed
from datetime import datetime, timedelta # Import datetime components

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException # Specific Selenium exceptions
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Import database components
try:
    from .database.functions import SessionLocal, get_db, Company, JobBoard, Listing
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from role_aggr.database.functions import SessionLocal, get_db, Company, JobBoard, Listing
    except ImportError as e:
        print(f"Error importing database modules: {e}")
        sys.exit(1)


def get_user_agent():
    """Return a random user agent."""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
    ]
    return random.choice(user_agents)

# --- Date Parsing Logic (Moved from app.py) ---
def parse_date(date_str):
    """
    Parse date string to datetime object.
    Handles relative dates ('X days ago'), 'today', 'yesterday', and common absolute formats.
    Returns a datetime object; datetime.min if parsing fails or input is invalid.
    """
    if not date_str or date_str == 'N/A':
        return datetime.min # Treat missing dates as very old

    date_str = str(date_str).strip().lower()

    if 'ago' in date_str:
        match = re.search(r'(\d+)\s+(day|week|month|hour|minute)s?', date_str)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            now = datetime.now()
            if 'minute' in unit: return now - timedelta(minutes=num)
            if 'hour' in unit: return now - timedelta(hours=num)
            if 'day' in unit: return now - timedelta(days=num)
            if 'week' in unit: return now - timedelta(weeks=num)
            if 'month' in unit: return now - timedelta(days=num * 30)

    if 'today' in date_str or 'just posted' in date_str:
        return datetime.now()
    if 'yesterday' in date_str:
        return datetime.now() - timedelta(days=1)

    date_formats = [
        '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d %b %Y',
        '%d %B %Y', '%b %d, %Y', '%B %d, %Y',
    ]
    for fmt in date_formats:
        try:
            date_part = date_str.split('t')[0].strip()
            return datetime.strptime(date_part, fmt)
        except ValueError:
            continue

    # If parsing fails, return datetime.min (very old)
    # print(f"Warning: Could not parse date string: '{date_str}'") # Reduce noise
    return datetime.min

# --- Main Scraping Logic ---

def scrape_job_board(db: Session, job_board: JobBoard):
    """Scrape a single job board, routing to specific extraction logic."""
    company_name = job_board.company.name if job_board.company else job_board.name
    print(f"Scraping {company_name} ({job_board.link})...")
    try:
        time.sleep(random.uniform(1.0, 3.5))
        domain = urlparse(job_board.link).netloc

        if 'myworkdayjobs.com' in domain: extract_workday_jobs(db, job_board)
        elif 'oraclecloud.com' in domain: extract_oracle_cloud_jobs(db, job_board)
        elif 'eightfold.ai' in domain: extract_eightfold_jobs(db, job_board)
        else:
            headers = {'User-Agent': get_user_agent()}
            try:
                response = requests.get(job_board.link, headers=headers, timeout=25)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                print(f"Timeout: {company_name}")
                return
            except requests.exceptions.RequestException as e:
                print(f"Request error: {company_name} - {e}")
                return
            soup = BeautifulSoup(response.text, 'html.parser')
            extract_jobs_by_domain(db, soup, domain, job_board)
    except Exception as e: print(f"Unexpected Error scraping {company_name}: {type(e).__name__} - {str(e)}")

# --- Threading and Session Management ---

def scrape_job_board_task(job_board_id: int):
    """Task function run in a thread, managing its own DB session."""
    db = SessionLocal()
    try:
        from sqlalchemy.orm import joinedload
        job_board = db.query(JobBoard).options(joinedload(JobBoard.company)).get(job_board_id)
        if not job_board:
            print(f"Job board ID {job_board_id} not found.")
            return
        scrape_job_board(db, job_board)
        db.commit()
    except Exception as e:
        job_board_name = f"ID {job_board_id}"
        try:
            if 'job_board' in locals() and job_board: job_board_name = job_board.name
        except: pass
        print(f"Error in thread for {job_board_name}: {e}")
        db.rollback()
    finally: db.close()

def scrape_job_listings(job_board_ids: list[int]):
    """Scrapes job boards in parallel threads."""
    print(f"Starting parallel scraping for {len(job_board_ids)} job boards...")
    failed_tasks = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(scrape_job_board_task, board_id) for board_id in job_board_ids]
        results = concurrent.futures.wait(futures)
        for future in results.done:
            try:
                future.result()
            except Exception:
                failed_tasks += 1
    if failed_tasks > 0: print(f"Warning: {failed_tasks} scraping tasks failed.")
    print("Parallel scraping finished.")

# --- BeautifulSoup Extraction Routing ---

def extract_jobs_by_domain(db: Session, soup: BeautifulSoup, domain: str, job_board: JobBoard):
    """Routes BeautifulSoup extraction based on domain."""
    company_name = job_board.company.name if job_board.company else job_board.name
    if 'efinancialcareers.co.uk' in domain: extract_efinancialcareers_jobs(db, soup, job_board)
    elif 'jobs.janushenderson.com' in domain: extract_janus_henderson_jobs(db, soup, job_board)
    elif 'referrals.selectminds.com' in domain: extract_selectminds_jobs(db, soup, job_board)
    elif 'insightinvestment.com' in domain: extract_insight_investment_jobs(db, soup, job_board)
    else:
        print(f"Using generic BS4 extraction for {company_name} ({domain})")
        extract_generic_jobs(db, soup, job_board)

# --- Database Helper ---

def _add_listing_to_db(db: Session, listing_data: dict):
    """Helper to create/add Listing, handling duplicates and validation."""
    if 'date_posted' in listing_data and not isinstance(listing_data['date_posted'], datetime):
        print(f"Warning: date_posted not datetime for {listing_data.get('link')}. Type: {type(listing_data['date_posted'])}")
        listing_data['date_posted'] = parse_date(str(listing_data.get('date_posted')))
    if not all(listing_data.get(k) for k in ['title', 'link', 'company_id']):
        return False
    max_title_len = 255
    if len(listing_data['title']) > max_title_len:
        listing_data['title'] = listing_data['title'][:max_title_len]
    existing = db.query(Listing.id).filter_by(link=listing_data['link']).first()
    if existing:
        return False
    listing = Listing(**listing_data)
    db.add(listing)
    return True

# --- Selenium Extraction Functions ---

def extract_workday_jobs(db: Session, job_board: JobBoard):
    """Extract jobs from Workday using Selenium."""
    company = job_board.company
    company_name = company.name if company else job_board.name
    print(f"Using Selenium for Workday: {company_name}")
    if not company and job_board.type == 'Company':
        print(f"Warning: Skipping Workday company board '{job_board.name}' - no company link.")
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={get_user_agent()}")
    listings_added_count = 0
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.implicitly_wait(5)
        driver.get(job_board.link)
        job_list_locator = (By.CSS_SELECTOR, "ul[role='list'], section[data-automation-id='jobResults']")
        job_title_locator = (By.CSS_SELECTOR, "a[data-automation-id='jobTitle']")
        job_elements = []
        try:
            WebDriverWait(driver, 25).until(EC.presence_of_element_located(job_list_locator))
            job_elements = driver.find_elements(*job_title_locator)
            print(f"Found {len(job_elements)} potential Workday job elements for {company_name}")
        except (TimeoutException, NoSuchElementException) as e_wait:
            print(f"Error waiting/finding list on Workday for {company_name}: {e_wait}")
        else:
            for job_element in job_elements:
                listing_company_id = company.id if company else None
                if not listing_company_id:
                    continue
                try:
                    job_title = job_element.text.strip()
                    job_url = job_element.get_attribute('href')
                    if not job_title or not job_url:
                        continue
                    location = "N/A"
                    date_posted_str = "N/A"
                    parent_context = None
                    try:
                        parent_context = job_element.find_element(By.XPATH, "./ancestor::li[contains(@class, 'css-')] | ./ancestor::div[contains(@class, 'css-')][.//a[@data-automation-id='jobTitle']] | ./ancestor::div[@role='listitem']")
                    except NoSuchElementException:
                        pass
                    if parent_context:
                        try:
                            loc_element = parent_context.find_element(By.CSS_SELECTOR, "[data-automation-id*='location'], [class*='location']")
                            location = loc_element.text.strip()
                        except NoSuchElementException:
                            pass
                        try:
                            date_element = parent_context.find_element(By.CSS_SELECTOR, "[data-automation-id*='posted'], [class*='posted'], time")
                            date_text = date_element.get_attribute('datetime') or date_element.text.strip()
                            date_posted_str = date_text if date_text else "N/A"
                        except NoSuchElementException:
                            pass

                    parsed_dt = parse_date(date_posted_str) # Parse date

                    listing_data = {'title': job_title, 'company_id': listing_company_id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
                    if _add_listing_to_db(db, listing_data):
                        listings_added_count += 1
                except Exception as e_extract:
                    print(f"Error extracting Workday job detail: {str(e_extract)}")
    except Exception as e_general:
        print(f"General Selenium Workday error: {str(e_general)}")
    finally:
        if driver:
            driver.quit()
        print(f"Processed {company_name} (Workday). Added {listings_added_count} new listings.")

def extract_oracle_cloud_jobs(db: Session, job_board: JobBoard):
    """Placeholder: Extract jobs from Oracle Cloud HCM sites."""
    company_name = job_board.company.name if job_board.company else job_board.name
    print(f"Selenium Oracle Cloud: {company_name} (Placeholder - Not Implemented)")
    # TODO: Implement Selenium logic, parse date string with parse_date()
    print(f"Added 0 new listings from {company_name} (Oracle Cloud - Placeholder).")

def extract_eightfold_jobs(db: Session, job_board: JobBoard):
    """Placeholder: Extract jobs from Eightfold.ai sites."""
    company_name = job_board.company.name if job_board.company else job_board.name
    print(f"Selenium Eightfold.ai: {company_name} (Placeholder - Not Implemented)")
    # TODO: Implement Selenium logic, parse date string with parse_date()
    print(f"Added 0 new listings from {company_name} (Eightfold - Placeholder).")

# --- BeautifulSoup Extraction Functions ---

def extract_efinancialcareers_jobs(db: Session, soup: BeautifulSoup, job_board: JobBoard):
    """Extract jobs from eFinancialCareers using BeautifulSoup."""
    listings_added_count = 0
    base_url = 'https://www.efinancialcareers.co.uk'
    job_elements = soup.select('div.job-card')
    print(f"Found {len(job_elements)} potential eFin job elements.")
    for job_element in job_elements:
        try:
            title_element = job_element.select_one('h3.job-card__title a')
            job_title = title_element.text.strip() if title_element else None
            job_url_relative = title_element.get('href', '') if title_element else None
            if not job_title or not job_url_relative:
                continue
            job_url = urljoin(base_url, job_url_relative)
            company_name_element = job_element.select_one('div.job-card__company-name')
            company_name_scraped = company_name_element.text.strip() if company_name_element else None
            if not company_name_scraped:
                continue
            company = db.query(Company).filter(Company.name.ilike(company_name_scraped)).first()
            if not company:
                print(f"Warning: Company '{company_name_scraped}' (eFin) not found. Skipping.")
                continue
            date_element = job_element.select_one('span.job-card__date')
            date_posted_str = date_element.text.strip() if date_element else 'N/A'
            location_element = job_element.select_one('span.job-card__location')
            location = location_element.text.strip() if location_element else 'N/A'
            parsed_dt = parse_date(date_posted_str) # Parse date
            listing_data = {'title': job_title, 'company_id': company.id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
            if _add_listing_to_db(db, listing_data):
                listings_added_count += 1
        except Exception as e_extract:
            print(f"Error extracting eFin job: {str(e_extract)}")
    print(f"Processed {job_board.name} (eFin). Added {listings_added_count} new listings.")

def extract_janus_henderson_jobs(db: Session, soup: BeautifulSoup, job_board: JobBoard):
    """Extract jobs from jobs.janushenderson.com using BeautifulSoup."""
    listings_added_count = 0
    company = job_board.company
    if not company:
        return
    job_elements = soup.select('section.jobs-list article.job-item')
    print(f"Found {len(job_elements)} potential Janus Henderson elements.")
    for job_element in job_elements:
        try:
            title_element = job_element.select_one('h2 a')
            job_title = title_element.text.strip() if title_element else None
            job_url_relative = title_element.get('href', '') if title_element else None
            if not job_title or not job_url_relative:
                continue
            job_url = urljoin(job_board.link, job_url_relative)
            location_element = job_element.select_one('div.job-location')
            location = location_element.text.strip() if location_element else 'N/A'
            date_element = job_element.select_one('div.job-date')
            date_posted_str = date_element.text.strip() if date_element else 'N/A'
            parsed_dt = parse_date(date_posted_str) # Parse date
            listing_data = {'title': job_title, 'company_id': company.id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
            if _add_listing_to_db(db, listing_data):
                listings_added_count += 1
        except Exception as e:
            print(f"Error extracting Janus Henderson job: {e}")
    print(f"Processed {company.name} (Janus Henderson). Added {listings_added_count} new listings.")

def extract_selectminds_jobs(db: Session, soup: BeautifulSoup, job_board: JobBoard):
    """Extract jobs from *.referrals.selectminds.com using BeautifulSoup."""
    listings_added_count = 0
    company = job_board.company
    if not company:
        return
    job_elements = soup.select('div.job_list_row, li.job')
    print(f"Found {len(job_elements)} potential SelectMinds elements for {company.name}.")
    for job_element in job_elements:
        try:
            title_element = job_element.select_one('a.job_link, a[href*="job"]')
            job_title = title_element.text.strip() if title_element else None
            job_url_relative = title_element.get('href', '') if title_element else None
            if not job_title or not job_url_relative:
                continue
            job_url = urljoin(job_board.link, job_url_relative)
            location_element = job_element.select_one('.job_location, span[class*="location"]')
            location = location_element.text.strip() if location_element else 'N/A'
            date_element = job_element.select_one('.job_post_date, span[class*="date"]')
            date_posted_str = date_element.text.strip() if date_element else 'N/A'
            parsed_dt = parse_date(date_posted_str) # Parse date
            listing_data = {'title': job_title, 'company_id': company.id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
            if _add_listing_to_db(db, listing_data):
                listings_added_count += 1
        except Exception as e:
            print(f"Error extracting SelectMinds job for {company.name}: {e}")
    print(f"Processed {company.name} (SelectMinds). Added {listings_added_count} new listings.")

def extract_insight_investment_jobs(db: Session, soup: BeautifulSoup, job_board: JobBoard):
    """Extract jobs from insightinvestment.com using BeautifulSoup."""
    listings_added_count = 0
    company = job_board.company
    if not company:
        return
    job_elements = soup.select('table#VacanciesTable tbody tr')
    print(f"Found {len(job_elements)} potential Insight Investment elements.")
    for job_element in job_elements:
        try:
            cells = job_element.find_all('td')
            if len(cells) < 3:
                continue
            title_element = cells[0].find('a')
            job_title = title_element.text.strip() if title_element else cells[0].text.strip()
            job_url_relative = title_element.get('href', '') if title_element else None
            if not job_title or not job_url_relative:
                continue
            job_url = urljoin(job_board.link, job_url_relative)
            location = cells[1].text.strip()
            date_posted_str = 'N/A' # Date not available
            parsed_dt = parse_date(date_posted_str) # Parse date (will be datetime.min)
            listing_data = {'title': job_title, 'company_id': company.id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
            if _add_listing_to_db(db, listing_data):
                listings_added_count += 1
        except Exception as e:
            print(f"Error extracting Insight Investment job: {e}")
    print(f"Processed {company.name} (Insight Investment). Added {listings_added_count} new listings.")

def extract_generic_jobs(db: Session, soup: BeautifulSoup, job_board: JobBoard):
    """Generic BS4 job extraction logic."""
    listings_added_count = 0
    company = job_board.company
    company_name = company.name if company else job_board.name
    is_company_board = (job_board.type == 'Company')
    if not company and is_company_board:
        print(f"Skipping generic: company board '{job_board.name}' no link.")
        return
    selectors = ['div.job', 'div.job-listing', 'div.vacancy', 'li.job-item', 'article.job', 'div.job-card', 'div[class*="job"]', 'li[class*="job"]', 'div[class*="vacancy"]', 'article[class*="job"]', 'tr[class*="job"]', 'tr.job-row']
    job_elements = []
    try:
        for selector in selectors:
            found = soup.select(selector)
            job_elements.extend(found)
        job_elements = list({id(el): el for el in job_elements}.values())
    except Exception as e_select:
        print(f"Error generic selector search {company_name}: {e_select}")
        return
    print(f"Found {len(job_elements)} potential generic elements for {company_name}")
    if not job_elements and soup.body:
         links = soup.body.find_all('a', href=True)
         potential_job_links = []
         for link in links:
             link_text = link.text.strip()
             if len(link_text) > 5 and (' ' in link_text or re.match(r'^[A-Z][a-zA-Z/]+', link_text)):
                 parent = link.parent
                 if parent and parent.name in ['li', 'div', 'td', 'article', 'section']:
                     potential_job_links.append(link)
         if potential_job_links:
             print(f"Trying {len(potential_job_links)} potential links.")
             job_elements = potential_job_links
         else:
             print(f"Warning: No generic elements/heuristics found for {company_name}.")
    for job_element in job_elements:
        try:
            job_title, title_element = None, None
            if job_element.name == 'a':
                job_title = job_element.text.strip()
                title_element = job_element
            else:
                title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '.job-title', '[class*="title"]', 'a']
                for ts in title_selectors:
                    el = job_element.select_one(ts)
                    if el and el.text and el.text.strip() and len(el.text.strip()) > 2:
                        job_title = el.text.strip()
                        title_element = el
                        break
            if not job_title or len(job_title) > 255:
                continue
            job_url, url_element = None, None
            if job_element.name == 'a' and job_element.has_attr('href'):
                url_element = job_element
            elif title_element and title_element.name == 'a' and title_element.has_attr('href'):
                url_element = title_element
            else:
                 url_selectors = ['a[href]', '.job-link[href]', '[class*="link"][href]']
                 for us in url_selectors:
                     el = job_element.select_one(us)
                     if el and el.has_attr('href'):
                         url_element = el
                         break
            if not url_element:
                continue
            job_url_relative = url_element.get('href', '')
            if not job_url_relative or job_url_relative.startswith('javascript:'):
                continue
            job_url = urljoin(job_board.link, job_url_relative)
            listing_company_id = None
            if is_company_board and company:
                listing_company_id = company.id
            else:
                company_selectors = ['.company', '.company-name', '[class*="company"]']
                company_name_scraped = None
                for cs in company_selectors:
                    el = job_element.select_one(cs)
                    if el and el.text.strip():
                        company_name_scraped = el.text.strip()
                        break
                if company_name_scraped:
                    found_company = db.query(Company).filter(Company.name.ilike(company_name_scraped)).first()
                    if found_company:
                        listing_company_id = found_company.id
                    else:
                        print(f"Warning: Company '{company_name_scraped}' (generic) not found. Skipping.")
                        continue
                else:
                    print(f"Warning: No company name for job '{job_title}' (generic). Skipping.")
                    continue
            location_selectors = ['.location', '.job-location', '[class*="location"]', '.loc', 'span[itemprop="jobLocation"]']
            location = "N/A"
            for ls in location_selectors:
                el = job_element.select_one(ls)
                if el and el.text.strip():
                    location = el.text.strip()
                    break
            date_selectors = ['.date', '.posted', '[class*="date"]', '[class*="posted"]', 'time', 'span[itemprop="datePosted"]']
            date_posted_str = "N/A"
            for ds in date_selectors:
                el = job_element.select_one(ds)
                if el:
                    date_text = el.get('datetime', '') or el.text.strip()
                    if date_text:
                        date_posted_str = date_text.strip()
                        break
            parsed_dt = parse_date(date_posted_str) # Parse date
            listing_data = {'title': job_title, 'company_id': listing_company_id, 'job_board_id': job_board.id, 'location': location, 'link': job_url, 'date_posted': parsed_dt, 'description': None}
            if _add_listing_to_db(db, listing_data):
                listings_added_count += 1
        except Exception as e_extract:
            print(f"Error extracting generic job from {company_name}: {str(e_extract)}")
    print(f"Processed {company_name} (Generic). Added {listings_added_count} new listings.")

# --- Main Execution ---

def update_job_listings_from_boards():
    """Fetches job boards from DB and triggers parallel scraping."""
    print("Starting job listing update process...")
    db = SessionLocal()
    job_board_ids_to_scrape = []
    job_board_names = []
    try:
        job_boards = db.query(JobBoard.id, JobBoard.name).filter(JobBoard.name != 'LinkedIn', JobBoard.name != 'Indeed').order_by(JobBoard.name).all()
        job_board_ids_to_scrape = [jb.id for jb in job_boards]
        job_board_names = [jb.name for jb in job_boards]
        print(f"Found {len(job_board_ids_to_scrape)} job boards to scrape: {job_board_names}")
    except Exception as e:
        print(f"Error fetching job boards: {e}")
    finally:
        db.close()
    if not job_board_ids_to_scrape:
        print("No job boards found to scrape.")
        return
    scrape_job_listings(job_board_ids_to_scrape)
    print("Job listing update process finished.")

if __name__ == "__main__":
    print("Running scraper update...")
    start_time = time.time()
    update_job_listings_from_boards()
    end_time = time.time()
    print(f"\nScraper update finished in {end_time - start_time:.2f} seconds.")
    print("\nChecking database for results...")
    db = SessionLocal()
    try:
        listing_count = db.query(Listing).count()
        print(f"Total listings in database: {listing_count}")
        if listing_count > 0:
            print("\nSample 5 listings (latest added):")
            from sqlalchemy.orm import joinedload
            listings = db.query(Listing).options(joinedload(Listing.company)).order_by(Listing.date_posted.desc().nullslast()).limit(5).all()
            for listing in listings:
                 company_name = listing.company.name if listing.company else "N/A"
                 date_str = listing.date_posted.strftime('%Y-%m-%d') if listing.date_posted and listing.date_posted != datetime.min else "N/A"
                 print(f"  Title: {listing.title}\n  Company: {company_name}\n  Location: {listing.location}\n  URL: {listing.link}\n  Date: {date_str}\n" + "-" * 20)
    except Exception as e:
        print(f"Error querying database: {e}")
    finally:
        db.close()