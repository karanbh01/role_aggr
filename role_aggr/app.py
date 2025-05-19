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
from flask import Flask, render_template, request, redirect, url_for, flash
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
try:
    from database.model import SessionLocal, Listing, Company
    from database.functions import init_db, load_job_boards_from_csv, update_job_boards, DATABASE_FILE
except ImportError:
    import sys
    # If run directly, __file__ is app.py. os.path.dirname gives role_aggr.
    # os.path.dirname(os.path.dirname()) gives project root.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Attempt imports again after path modification
    from database.model import SessionLocal, Listing, Company
    from database.functions import init_db, load_job_boards_from_csv, update_job_boards, DATABASE_FILE


# Scraper update function import
try:
    from role_aggr.scraper import update_job_listings_from_boards
except ImportError as e:
     logging.error(f"Error importing scraper update function from role_aggr.scraper: {e}", exc_info=True)
     def update_job_listings_from_boards():
         logging.error("Fallback: Scraper function 'update_job_listings_from_boards' not available due to import error.")
         # Avoid print here, use logging
         # import time # time is already imported via datetime
         # time.sleep(5) # Not useful in a real scenario

app = Flask(__name__)
app.secret_key = os.urandom(24)


# --- Date Parsing and Sorting Removed ---
# parse_date and sort_jobs_by_date are no longer needed here

# --- Flask Routes ---

@app.route('/')
def index():
    """Main route to display job listings from the database."""
    company_filter = request.args.get('company', '')
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

        # Apply company filter
        if company_filter:
            query = query.join(Company).filter(Company.name.ilike(f"%{company_filter}%"))

        # Fetch listings, ordered by date_posted descending (latest first)
        # Use nullslast() to put jobs with unknown dates at the end
        listings = query.order_by(desc(Listing.date_posted).nullslast(), Listing.id.desc()).all()

        # Convert Listing objects to dictionaries and format date
        for listing in listings:
            # Format the date for display
            date_display = "N/A"
            if listing.date_posted and listing.date_posted != datetime.min.replace(tzinfo=pytz.utc):
                try:
                    # Example format: "Oct 27, 2023" - adjust as desired
                    date_display = listing.date_posted.strftime('%b %d, %Y')
                except ValueError:
                    # Handle potential invalid dates stored (shouldn't happen with default)
                    date_display = "Invalid Date"

            # Determine if the job is new (posted within the last 24 hours)
            is_new = False
            if listing.date_posted and listing.date_posted != datetime.min.replace(tzinfo=pytz.utc):
                now_utc = datetime.now(pytz.utc)
                time_difference = now_utc - listing.date_posted.replace(tzinfo=pytz.utc)
                if time_difference < timedelta(hours=24):
                    is_new = True

            jobs_data.append({
                'title': listing.title,
                'company': listing.company.name if listing.company else 'N/A',
                'location': listing.location or 'N/A',
                'date_posted': date_display, # Use formatted date string
                'url': listing.link,
                'source': listing.job_board.name if listing.job_board else 'N/A',
                'is_new': is_new # Add the is_new flag
            })
            # No need to sort jobs_data here, already ordered by query

        # Get unique company names for the filter dropdown
        companies = sorted([c.name for c in db.query(Company.name).distinct().order_by(Company.name)])

    except Exception as e:
        print(f"Error fetching data from database: {e}")
        error_message = "Error loading job listings from the database."
        # jobs_data remains []
        companies = []
    finally:
        db.close()

    if error_message:
        flash(error_message, 'error')

    # Pass jobs_data directly (already sorted by DB query)
    return render_template('index.html',
                           jobs=jobs_data,
                           companies=companies,
                           selected_company=company_filter)

# --- Background Task Handling ---
update_thread = None
is_updating = False

def run_update_task():
    """Wrapper function to run the update and manage state."""
    global is_updating
    is_updating = True
    print("Background update task started.")
    try:
        update_job_listings_from_boards()
    except Exception as e:
        print(f"Exception in background update task: {e}")
    finally:
        is_updating = False
        print("Background update task finished.")

@app.route('/update-jobs')
def update_jobs():
    """Route to trigger the background job scraping process."""
    print("--- DEBUG: /update-jobs route hit ---") # Added debug print
    global update_thread, is_updating

    if is_updating:
        flash("An update is already in progress.", 'info')
    else:
        flash("Job listing update started in the background. Refresh the page in a few minutes.", 'success')
        update_thread = threading.Thread(target=run_update_task)
        update_thread.start()

    return redirect(url_for('index'))

@app.route('/update-status')
def update_status():
    """API endpoint to check if an update is running (optional)."""
    global is_updating
    return {"is_updating": is_updating}


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
        db = SessionLocal()
        load_job_boards_from_csv(db)
        db.close()
        logging.info("Database created and initialized.")
    else:
        logging.info("Database exists. Updating job boards...")
        update_job_boards()
        logging.info("Job boards updated.")
    
    app.run(debug=True, use_reloader=False)