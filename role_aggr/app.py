from flask import Flask, render_template, request
import os
import json
import time
import re
from datetime import datetime, timedelta
from scraper import get_all_jobs

app = Flask(__name__)

# Cache for job listings
CACHE_FILE = 'job_cache.json'
CACHE_EXPIRY = 3600  # Cache expiry in seconds (1 hour)

def parse_date(date_str):
    """
    Parse date string to datetime object for sorting
    """
    if not date_str or date_str == 'N/A':
        # If no date, assume it's old (30 days ago)
        return datetime.now() - timedelta(days=30)
    
    # Try to parse common date formats
    date_str = date_str.lower()
    
    # Handle relative dates like "2 days ago", "1 week ago", etc.
    if 'ago' in date_str:
        # Extract number and unit
        match = re.search(r'(\d+)\s+(day|days|week|weeks|month|months|hour|hours|minute|minutes)', date_str)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            if 'minute' in unit:
                return datetime.now() - timedelta(minutes=num)
            elif 'hour' in unit:
                return datetime.now() - timedelta(hours=num)
            elif 'day' in unit:
                return datetime.now() - timedelta(days=num)
            elif 'week' in unit:
                return datetime.now() - timedelta(weeks=num)
            elif 'month' in unit:
                return datetime.now() - timedelta(days=num*30)
    
    # Handle "today", "yesterday"
    if 'today' in date_str:
        return datetime.now()
    elif 'yesterday' in date_str:
        return datetime.now() - timedelta(days=1)
    
    # Try common date formats
    date_formats = [
        '%Y-%m-%d',           # 2023-04-21
        '%d/%m/%Y',           # 21/04/2023
        '%m/%d/%Y',           # 04/21/2023
        '%d %b %Y',           # 21 Apr 2023
        '%d %B %Y',           # 21 April 2023
        '%B %d, %Y',          # April 21, 2023
        '%b %d, %Y'           # Apr 21, 2023
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # If all parsing attempts fail, assume it's recent (today)
    return datetime.now()

def sort_jobs_by_date(jobs):
    """
    Sort jobs by date, most recent first
    """
    return sorted(jobs, key=lambda job: parse_date(job.get('date_posted', 'N/A')), reverse=True)

def get_jobs_with_cache():
    """
    Get job listings with caching to avoid scraping on every request
    """
    # Check if cache file exists and is not expired
    if os.path.exists(CACHE_FILE):
        file_modified_time = os.path.getmtime(CACHE_FILE)
        if time.time() - file_modified_time < CACHE_EXPIRY:
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading cache: {str(e)}")
    
    # Cache doesn't exist or is expired, scrape new data
    jobs = get_all_jobs()
    
    # Save to cache
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing cache: {str(e)}")
    
    return jobs

@app.route('/')
def index():
    """
    Main route to display job listings
    """
    # Get filter parameters
    company_filter = request.args.get('company', '')
    
    # Get jobs from cache
    jobs = get_jobs_with_cache()
    
    # Apply company filter if provided
    if company_filter:
        jobs = [job for job in jobs if company_filter.lower() in job['company'].lower()]
    
    # Sort jobs by date
    sorted_jobs = sort_jobs_by_date(jobs)
    
    # Get unique companies for filter dropdown
    companies = sorted(set(job['company'] for job in jobs))
    
    return render_template('index.html', jobs=sorted_jobs, companies=companies, selected_company=company_filter)

@app.route('/refresh')
def refresh():
    """
    Route to force refresh the job listings cache
    """
    # Delete cache file if it exists
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    
    # Get fresh job listings
    jobs = get_jobs_with_cache()
    
    # Get unique companies for filter dropdown
    companies = sorted(set(job['company'] for job in jobs))
    
    # Sort jobs by date
    sorted_jobs = sort_jobs_by_date(jobs)
    
    return render_template('index.html', jobs=sorted_jobs, companies=companies, selected_company='')

if __name__ == '__main__':
    app.run(debug=True)