import os
import sys

# Add the project root to sys.path to enable importing modules
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
_project_root_alt = os.path.abspath(os.path.join(_current_file_dir, '..', '..'))
if _project_root_alt not in sys.path:
    sys.path.insert(0, _project_root_alt)

from role_aggr.database.model import SessionLocal, Listing

def clear_job_listings():
    """Clears all job listings from the database."""
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
