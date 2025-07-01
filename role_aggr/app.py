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
from role_aggr.database.functions import init_db, update_job_boards, DATABASE_FILE



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
    print("--- DEBUG: Entering index() function ---") # Added debug print
    """Main route to display job listings from the database."""
    # Get multiple values for filters using getlist()
    company_filters = request.args.getlist('company')
    location_filters = request.args.getlist('location')
    
    # DEBUG: Log what we received
    logging.debug(f"Raw request.args: {dict(request.args)}")
    logging.debug(f"Company filters received: {company_filters}")
    logging.debug(f"Location filters received: {location_filters}")
    
    # Remove empty strings from filters
    company_filters = [c for c in company_filters if c.strip()]
    location_filters = [l for l in location_filters if l.strip()]
    
    # DEBUG: Log after filtering
    logging.debug(f"Company filters after filtering: {company_filters}")
    logging.debug(f"Location filters after filtering: {location_filters}")
    
    db: Session = SessionLocal()
    jobs_data = []
    companies = []
    error_message = None

    try:
        # Base query, eager load relationships
        query = db.query(Listing).options(
            joinedload(Listing.company),
            joinedload(Listing.job_board)
        )

        # Apply company filter - use IN clause for multiple selections
        if company_filters:
            query = query.join(Company).filter(Company.name.in_(company_filters))
        
        # Apply location filter - use IN clause for multiple selections
        if location_filters:
            query = query.filter(Listing.location.in_(location_filters))

        # Fetch listings, ordered by date_posted descending (latest first)
        # Use nullslast() to put jobs with unknown dates at the end
        listings = query.order_by(desc(Listing.date_posted).nullslast(), Listing.id.desc()).all()

        # Convert Listing objects to dictionaries and format date
        for listing in listings:
            # Format the date for display
            try:
                date_display = listing.date_posted.strftime('%b %d, %Y')
            except ValueError:
                # Handle potential invalid dates stored (shouldn't happen with default)
                date_display = "Invalid Date"

            # Determine if the job is new (posted within the last 24 hours)
            is_new = False
            now_utc = datetime.now()
            time_difference = now_utc - listing.date_posted
            if time_difference < timedelta(hours=24):
                is_new = True

            jobs_data.append({
                'title': listing.title,
                'company': listing.company.name if listing.company else 'N/A',
                'location': listing.location or 'N/A',
                'city': listing.city or 'N/A',
                'country': listing.country or 'N/A',
                'region': listing.region or 'N/A',
                'date_posted': date_display, # Use formatted date string
                'url': listing.link,
                'is_new': is_new # Add the is_new flag
            })
            # No need to sort jobs_data here, already ordered by query

        # Get unique company names for the filter dropdown
        companies = sorted([c.name for c in db.query(Company.name).distinct().order_by(Company.name)])

        # Get unique locations for the filter dropdown
        try:
            location_query = db.query(Listing.location).distinct().filter(
                Listing.location.isnot(None),
                Listing.location != '',
                Listing.location != 'N/A'
            ).order_by(Listing.location)
            locations = sorted([l[0] for l in location_query.all() if l[0] and l[0].strip()])
            logging.debug(f"Fetched {len(locations)} unique locations: {locations[:10]}{'...' if len(locations) > 10 else ''}")
        except Exception as e:
            logging.error(f"Error fetching locations: {e}")
            locations = []

    except Exception as e:
        logging.error(f"Error fetching data from database: {e}") # Changed print to logging.error
        error_message = "Error loading job listings from the database."
        # jobs_data remains []
        companies = []
        locations = [] # Initialize locations list on error
    finally:
        db.close()

    if error_message:
        flash(error_message, 'error')

    logging.debug(f"Rendering index.html with {len(jobs_data)} jobs, {len(companies)} companies, and {len(locations)} locations.") # Added debug log before rendering
    # Pass jobs_data directly (already sorted by DB query)
    return render_template('index.html',
                           jobs=jobs_data,
                           companies=companies,
                           selected_companies=company_filters,  # Pass list of selected companies
                           locations=locations, # Pass locations to the template
                           selected_locations=location_filters) # Pass list of selected locations

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