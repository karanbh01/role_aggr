# role_aggr/database/clear_listings.py
import os
import sys

# Add the project root to sys.path to enable importing modules like 'environment'
# when this script is run directly as a module.
# Alternative method using a known file within the package.
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
_project_root_alt = os.path.abspath(os.path.join(_current_file_dir, '..', '..'))
if _project_root_alt not in sys.path:
    sys.path.insert(0, _project_root_alt)

# Standard library imports first, then application imports.

from functions import SessionLocal
from model import Listing


def clear_job_listings():
    print("Attempting to clear all job listings from the database...")
    db = SessionLocal()
    try:
        num_deleted = db.query(Listing).delete()
        db.commit()
        print(f"Successfully deleted {num_deleted} job listings.")
    except Exception as e:
        print(f"Error clearing job listings: {e}")
        db.rollback()
    finally:
        db.close()
        print("Database session closed.")

if __name__ == "__main__":
    print("--- Starting: Clear Job Listings Script ---")
    clear_job_listings()
    print("--- Finished: Clear Job Listings Script ---")