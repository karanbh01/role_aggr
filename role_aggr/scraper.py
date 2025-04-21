import csv
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urlparse
import random
import os
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def read_job_boards(csv_file):
    """
    Read job boards from CSV file and filter out LinkedIn and Indeed
    """
    job_boards = []
    
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['Name'] not in ['LinkedIn', 'Indeed']:
                job_boards.append(row)
    
    return job_boards

def get_user_agent():
    """
    Return a random user agent to avoid being blocked
    """
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
    ]
    return random.choice(user_agents)

def scrape_job_board(board):
    """
    Scrape a single job board
    """
    try:
        print(f"Scraping {board['Name']}...")
        
        # Add a small delay to avoid being blocked
        time.sleep(1)
        
        # Check if this is a Workday job board
        domain = urlparse(board['Link']).netloc
        if 'myworkdayjobs.com' in domain:
            # Use Selenium for Workday job boards
            jobs = extract_workday_jobs(None, board)
        else:
            # Use requests for other job boards
            headers = {'User-Agent': get_user_agent()}
            response = requests.get(board['Link'], headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract job listings based on the domain
            jobs = extract_jobs_by_domain(soup, domain, board)
        
        print(f"Found {len(jobs)} jobs from {board['Name']}")
        return jobs
        
    except Exception as e:
        print(f"Error scraping {board['Name']}: {str(e)}")
        return []

def scrape_job_listings(job_boards):
    """
    Scrape job listings from each job board using parallel processing
    """
    all_jobs = []
    
    # Use ThreadPoolExecutor for parallel scraping
    # We use threads instead of processes because most of the time is spent waiting for network I/O
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit scraping tasks for each job board
        future_to_board = {executor.submit(scrape_job_board, board): board for board in job_boards}
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_board):
            board = future_to_board[future]
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"Error processing results from {board['Name']}: {str(e)}")
    
    return all_jobs

def extract_jobs_by_domain(soup, domain, board):
    """
    Extract job listings based on the domain
    Different job boards have different HTML structures
    """
    jobs = []
    
    # Default extraction logic (basic)
    if 'myworkdayjobs' in domain:
        # Workday job boards
        return extract_workday_jobs(soup, board)
    elif 'efinancialcareers' in domain:
        # eFinancialCareers
        return extract_efinancialcareers_jobs(soup, board)
    else:
        # Generic extraction (may not work for all sites)
        return extract_generic_jobs(soup, board)

def extract_workday_jobs(soup, board):
    """
    Extract jobs from Workday-based job boards using Selenium
    """
    print(f"Using Selenium to scrape Workday job board: {board['Name']}")
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={get_user_agent()}")
    
    # Initialize Chrome driver
    driver = webdriver.Chrome(options=chrome_options)
    jobs = []
    
    try:
        # Navigate to the job board URL
        driver.get(board['Link'])
        
        # Wait for the page to load (reduced from 5 to 3 seconds)
        time.sleep(3)
        
        # Wait for job listings to appear
        try:
            # Wait for job title links to appear
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-automation-id='jobTitle']"))
            )
            
            # Find all job listings
            job_elements = driver.find_elements(By.CSS_SELECTOR, "a[data-automation-id='jobTitle']")
            
            print(f"Found {len(job_elements)} job listings for {board['Name']}")
            
            for job_element in job_elements:
                try:
                    # Extract job title
                    job_title = job_element.text.strip()
                    job_url = job_element.get_attribute('href')
                    
                    # Extract company name
                    company = board['Name']
                    
                    # Try to extract location (if available)
                    try:
                        # Find the parent element that contains both the job title and location
                        parent_element = driver.execute_script("return arguments[0].closest('li')", job_element)
                        location_element = parent_element.find_element(By.CSS_SELECTOR, "[data-automation-id='locationLabel']")
                        location = location_element.text.strip()
                    except:
                        location = "N/A"
                    
                    # Try to extract date posted information
                    date_posted = "N/A"
                    
                    # First try to get the date from the postedOn element
                    try:
                        # Find the parent element that contains the date
                        posted_element = driver.find_element(By.CSS_SELECTOR, "[data-automation-id='postedOn']")
                        if posted_element:
                            date_text = posted_element.text
                            # Extract the date part (e.g., "Posted 12 Days Ago")
                            if "Posted" in date_text:
                                date_posted = date_text.split("posted on")[-1].strip()
                    except:
                        pass
                    
                    # If we couldn't get the date from the UI, try to get it from JSON-LD
                    if date_posted == "N/A":
                        try:
                            # Look for JSON-LD script tags
                            script_elements = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
                            for script in script_elements:
                                script_content = script.get_attribute('textContent')
                                if '"datePosted"' in script_content:
                                    # Extract the date using regex
                                    import re
                                    date_match = re.search(r'"datePosted"\s*:\s*"([^"]+)"', script_content)
                                    if date_match:
                                        date_posted = date_match.group(1)
                                        break
                        except:
                            pass
                    
                    jobs.append({
                        'title': job_title,
                        'company': company,
                        'date_posted': date_posted,
                        'location': location,
                        'url': job_url,
                        'source': board['Name']
                    })
                except Exception as e:
                    print(f"Error extracting job from {board['Name']}: {str(e)}")
            
        except Exception as e:
            print(f"Error waiting for job listings: {str(e)}")
    
    finally:
        # Close the browser
        driver.quit()
    
    return jobs

def extract_efinancialcareers_jobs(soup, board):
    """
    Extract jobs from eFinancialCareers
    """
    jobs = []
    
    # Look for job listings
    job_elements = soup.select('.job-card')
    
    for job_element in job_elements:
        try:
            # Extract job title
            title_element = job_element.select_one('.job-card__title')
            if not title_element:
                continue
                
            job_title = title_element.text.strip()
            
            # Extract job URL
            url_element = job_element.select_one('a.job-card__link')
            job_url = url_element.get('href', '') if url_element else ''
            if job_url and not job_url.startswith('http'):
                job_url = 'https://www.efinancialcareers.co.uk' + job_url
            
            # Extract company name
            company_element = job_element.select_one('.job-card__company-name')
            company = company_element.text.strip() if company_element else board['Name']
            
            # Extract date posted
            date_element = job_element.select_one('.job-card__date')
            date_posted = date_element.text.strip() if date_element else 'N/A'
            
            jobs.append({
                'title': job_title,
                'company': company,
                'date_posted': date_posted,
                'url': job_url,
                'source': board['Name']
            })
        except Exception as e:
            print(f"Error extracting job from {board['Name']}: {str(e)}")
    
    return jobs

def extract_generic_jobs(soup, board):
    """
    Generic job extraction logic
    """
    jobs = []
    
    # Look for common job listing patterns
    # This is a basic approach and may need to be customized for specific sites
    
    # Try to find job listings by looking for common patterns
    job_elements = soup.select('div.job, div.job-listing, div.vacancy, li.job-item, div.job-card')
    
    if not job_elements:
        # Try alternative selectors
        job_elements = soup.select('div[class*="job"], li[class*="job"], div[class*="vacancy"]')
    
    for job_element in job_elements:
        try:
            # Try to extract job title
            title_element = job_element.select_one('h2, h3, h4, .title, .job-title, [class*="title"]')
            if not title_element:
                continue
                
            job_title = title_element.text.strip()
            
            # Try to extract job URL
            url_element = job_element.select_one('a')
            job_url = url_element.get('href', '') if url_element else ''
            
            # Make sure URL is absolute
            if job_url and not job_url.startswith('http'):
                base_url = f"https://{urlparse(board['Link']).netloc}"
                job_url = base_url + ('' if job_url.startswith('/') else '/') + job_url
            
            # Extract company name
            company_element = job_element.select_one('.company, .company-name, [class*="company"]')
            company = company_element.text.strip() if company_element else board['Name']
            
            # Extract date posted
            date_element = job_element.select_one('.date, .posted, [class*="date"], [class*="posted"]')
            date_posted = date_element.text.strip() if date_element else 'N/A'
            
            jobs.append({
                'title': job_title,
                'company': company,
                'date_posted': date_posted,
                'url': job_url,
                'source': board['Name']
            })
        except Exception as e:
            print(f"Error extracting job from {board['Name']}: {str(e)}")
    
    return jobs

def get_all_jobs(csv_file='job_boards.csv'):
    """
    Main function to get all jobs
    """
    job_boards = read_job_boards(csv_file)
    return scrape_job_listings(job_boards)

if __name__ == "__main__":
    # Test the scraper
    jobs = get_all_jobs()
    print(f"Total jobs found: {len(jobs)}")
    for job in jobs[:5]:  # Print first 5 jobs
        print(f"Title: {job['title']}")
        print(f"Company: {job['company']}")
        print(f"Date Posted: {job['date_posted']}")
        print(f"URL: {job['url']}")
        print(f"Source: {job['source']}")
        print("-" * 50)