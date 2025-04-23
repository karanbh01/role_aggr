# role_aggr/app.py - Final Version with DB DateTime

from flask import Flask, render_template, request, redirect, url_for, flash
import os
import re # Keep re if needed elsewhere, otherwise remove
from datetime import datetime, timedelta # Keep datetime for formatting
from sqlalchemy.orm import joinedload, Session
from sqlalchemy import desc # Import desc for ordering
import threading

# Database imports
try:
    from database.database import SessionLocal, Listing, Company, JobBoard
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from role_aggr.database.database import SessionLocal, Listing, Company, JobBoard
    except ImportError as e:
        print(f"Error importing database modules in app.py: {e}")
        sys.exit(1)

# Scraper update function import
try:
    from scraper import update_job_listings_from_boards
except ImportError as e:
     print(f"Error importing scraper update function: {e}")
     def update_job_listings_from_boards():
         print("Error: Scraper function 'update_job_listings_from_boards' not available.")
         import time
         time.sleep(5)


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
            if listing.date_posted and listing.date_posted != datetime.min:
                try:
                    # Example format: "Oct 27, 2023" - adjust as desired
                    date_display = listing.date_posted.strftime('%b %d, %Y')
                except ValueError:
                    # Handle potential invalid dates stored (shouldn't happen with default)
                    date_display = "Invalid Date"

            # Determine if the job is new (posted within the last 24 hours)
            is_new = False
            if listing.date_posted and listing.date_posted != datetime.min:
                time_difference = datetime.now() - listing.date_posted
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
    app.run(debug=True, use_reloader=False)