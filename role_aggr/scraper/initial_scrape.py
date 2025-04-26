# role_aggr/initial_scrape.py - Updated to clear listings

import time
import os
import sys

# Ensure the main project directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__))) # Add role_aggr dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # Add workspace root

try:
    # Import Listing model as well
    from role_aggr.database.functions import init_db, load_job_boards_from_csv, SessionLocal, DATABASE_FILE, Listing
    from role_aggr.scraper import update_job_listings_from_boards
except ImportError as e:
    print(f"Error importing necessary modules: {e}")
    print("Please ensure database.py and scraper.py are present and correctly structured.")
    sys.exit(1)

if __name__ == "__main__":
    print("--- Starting Initial Database Setup and Scrape ---")

    # 1. Initialize Database (Create tables if they don't exist)
    print("\nStep 1: Initializing database schema...")
    try:
        init_db()
    except Exception as e:
        print(f"Error during database initialization: {e}")
        sys.exit(1)

    # 2. Load Job Boards from CSV (if needed, handles duplicates)
    print("\nStep 2: Loading Companies and Job Boards from CSV...")
    db = SessionLocal()
    try:
        load_job_boards_from_csv(db)
    except Exception as e:
        print(f"Error loading data from CSV: {e}")
        # Continue anyway
    finally:
        db.close()

    # 2.5 Clear Existing Listings
    print("\nStep 2.5: Clearing existing job listings...")
    db = SessionLocal()
    try:
        num_deleted = db.query(Listing).delete()
        db.commit()
        print(f"Deleted {num_deleted} existing listings.")
    except Exception as e:
        print(f"Error clearing existing listings: {e}")
        db.rollback()
        # Decide if we should exit or continue
        # sys.exit(1) # Optional: exit if clearing fails
    finally:
        db.close()


    # 3. Run the Scraper to Populate Listings
    print("\nStep 3: Starting scraper to populate job listings...")
    start_time = time.time()
    try:
        update_job_listings_from_boards()
    except Exception as e:
        print(f"An error occurred during the scraping process: {e}")
    finally:
        end_time = time.time()
        print(f"Scraping finished in {end_time - start_time:.2f} seconds.")

    print("\n--- Initial Database Setup and Scrape Complete ---")
    print(f"Database located at: {DATABASE_FILE}")