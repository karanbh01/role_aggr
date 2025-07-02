print("--- DEBUG: Starting app.py ---") # Added debug print at the very beginning

# role_aggr/app.py

# --- Early Logging Configuration ---
# Configure logging as early as possible, before other project imports that might use logging.
import logging
# from logging.handlers import RotatingFileHandler # Removed RotatingFileHandler import
import os # For app.secret_key

# Basic configuration for the root logger.
# Modules using logging.getLogger(__name__) will inherit this.
# Configuring only console output for now to isolate issues.
console_handler = logging.StreamHandler() # Handler to output to console
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))


logging.basicConfig(level=logging.DEBUG,
                    handlers=[
                        console_handler # Only console handler for now
                    ])

logging.info("Root logger configured at top of app.py. Logging to console only.")

# --- Standard Flask and App Imports ---
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sys, os
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import joinedload, Session
from sqlalchemy import desc
import threading

# Add the project root to sys.path to enable importing modules like 'environment'
# when this script is run directly as a module.
# Alternative method using a known file within the package.
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
_project_root_alt = os.path.abspath(os.path.join(_current_file_dir, '..'))
if _project_root_alt not in sys.path:
    sys.path.insert(0, _project_root_alt)


# Database imports
from role_aggr.database.model import SessionLocal, Listing, Company
from role_aggr.database.functions import init_db, update_job_boards, DATABASE_FILE, get_all_listings, get_unique_cities, get_unique_countries, get_unique_companies, get_unique_locations
import math



# Scraper update function import
from role_aggr.scripts.scraper import main

app = Flask(__name__)
print("--- DEBUG: Flask app created ---") # Added debug print after Flask app creation
app.secret_key = os.urandom(24)


# --- Date Parsing and Sorting Removed ---
# parse_date and sort_jobs_by_date are no longer needed here

# --- Flask Routes ---

@app.route('/')
def index():
    """Main route to display job listings with search, filtering, and pagination."""
    search = request.args.get('search', '').strip()
    city = request.args.get('city', '').strip()
    country = request.args.get('country', '').strip()
    company = request.args.getlist('company')  # Get multiple values
    location = request.args.getlist('location')  # Get multiple values
    date_filter = request.args.get('date_filter', '').strip()
    items_per_page = request.args.get('items_per_page', '20').strip()
    page = int(request.args.get('page', 1))
    
    # Convert items_per_page to int with default
    try:
        per_page = int(items_per_page) if items_per_page else 20
    except ValueError:
        per_page = 20

    try:
        # Get unique data for dropdown filters
        available_cities = get_unique_cities()
        available_countries = get_unique_countries()
        available_companies = get_unique_companies()
        available_locations = get_unique_locations()
        
        listings, total_count = get_all_listings(search=search, city=city, country=country, company=company, location=location, date_filter=date_filter, page=page, per_page=per_page)
        total_pages = math.ceil(total_count / per_page)

        # Calculate pagination variables
        prev_page = page - 1 if page > 1 else None
        next_page = page + 1 if page < total_pages else None

        # Generate a list of page numbers to display in the pagination control
        # This example shows a simple range, you might want a more sophisticated one
        # like showing current page, +/- 2 pages, and first/last pages.
        pages_to_display = []
        if total_pages <= 7: # If total pages are few, display all
            pages_to_display = list(range(1, total_pages + 1))
        else:
            # Always show first page
            pages_to_display.append(1)
            # Show pages around the current page
            start_range = max(2, page - 2)
            end_range = min(total_pages - 1, page + 2)

            if start_range > 2:
                pages_to_display.append('...') # Ellipsis for skipped pages

            for i in range(start_range, end_range + 1):
                pages_to_display.append(i)

            if end_range < total_pages - 1:
                pages_to_display.append('...') # Ellipsis for skipped pages
            
            # Always show last page if not already included
            if total_pages not in pages_to_display:
                pages_to_display.append(total_pages)

        pagination = {
            'prev_page': prev_page,
            'next_page': next_page,
            'pages': pages_to_display,
            'current_page': page,
            'total_pages': total_pages
        }

        jobs_data = []
        now = datetime.now()
        for item in listings:
            if isinstance(item, tuple):
                listing_obj = item[0]
                relevance_score = item[1]
            else:
                listing_obj = item
                relevance_score = 0  # Set to 0 when no search is active

            # Determine if job is new (posted within last 24 hours)
            is_new = False
            if listing_obj.date_posted:
                time_diff = now - listing_obj.date_posted
                is_new = time_diff.total_seconds() < 24 * 60 * 60  # 24 hours

            # Format date to show only date part, not time
            formatted_date = listing_obj.date_posted.strftime('%Y-%m-%d') if listing_obj.date_posted else 'N/A'

            jobs_data.append({
                'title': listing_obj.title,
                'company': listing_obj.company.name if listing_obj.company else 'N/A',
                'location': listing_obj.location,
                'city': listing_obj.city,
                'country': listing_obj.country,
                'date_posted': formatted_date,
                'url': listing_obj.link,
                'description': listing_obj.description,
                'relevance_score': relevance_score,
                'is_new': is_new
            })

        return render_template(
            'index.html',
            jobs=jobs_data,
            search=search,
            search_query=search,  # Add search_query for template logic
            city=city,
            country=country,
            company=company,
            location=location,
            date_filter=date_filter,
            items_per_page=items_per_page,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            pagination=pagination, # Pass the pagination object
            available_cities=available_cities,
            available_countries=available_countries,
            available_companies=available_companies,
            available_locations=available_locations
        )
    except Exception as e:
        logging.error(f"Error fetching listings: {e}")
        flash("Error loading job listings.", "error")
        # Ensure pagination is passed even on error to prevent template errors
        pagination = {
            'prev_page': None,
            'next_page': None,
            'pages': [1],
            'current_page': 1,
            'total_pages': 0
        }
        # Get empty lists for dropdown filters even on error
        available_cities = []
        available_countries = []
        available_companies = []
        available_locations = []
        return render_template('index.html', jobs=[], search=search, search_query=search, city=city, country=country, company=company, location=location, date_filter=date_filter, items_per_page=items_per_page, page=page, per_page=per_page, total_pages=0, pagination=pagination, available_cities=available_cities, available_countries=available_countries, available_companies=available_companies, available_locations=available_locations)

if __name__ == '__main__':
    # Logging is now configured at the top of the file.
    # The app.logger will also use this configuration if Flask doesn't override it.
    # However, for Flask apps, it's common for Flask's own logging setup (especially with debug=True)
    # to take precedence for app.logger. The root logger setup we did should still catch other modules.

    app.logger.info("Flask app starting...") # This will use Flask's logger, which might be different from root.

    # Check if database exists
    if not os.path.exists(DATABASE_FILE):
        logging.info("Database does not exist. Creating and initializing...")
        init_db()
        logging.info("Database created and initialized.")
        
    logging.info("Updating job boards...")
    update_job_boards()
    logging.info("Job boards updated.")
    
    app.run(debug=True, use_reloader=False)