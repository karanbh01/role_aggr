import os
import csv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from role_aggr.database.model import SessionLocal, Listing, Company, JobBoard, Base, engine
from role_aggr.environment import DATABASE_DIR, DATABASE_FILE, CSV_FILE_PATH
from datetime import datetime as dt
import pandas as pd
#from role_aggr.scraper.utils import parse_date

## main functions: ##

def get_db():
    """Dependency to get a database session."""
    
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Creates the database tables."""
    
    print(f"Initializing database at: {DATABASE_FILE}")
    
    # Create the database directory if it doesn't exist
    os.makedirs(DATABASE_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    
    print("Database tables created.")

def update_job_boards(csv_file=CSV_FILE_PATH):
    """
    Updates job boards from CSV file.
    If a job board exists, updates its properties.
    If it doesn't exist, creates a new job board.
    """
    
    print(f"Updating job boards from CSV: {csv_file}")
    db_session = SessionLocal()
    try:
        _process_job_board(csv_file, db_session)
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file}")
    except Exception as e:
        db_session.rollback()
        print(f"An error occurred during job board update: {e}")
    finally:
        db_session.close()

def get_job_boards(dataframe=False) -> list | pd.DataFrame:
    """Fetches all job boards from the database."""
    
    db_session = SessionLocal()
    
    try:
        query = db_session.query(JobBoard).options(joinedload(JobBoard.company))
    
        if dataframe:
            job_boards = pd.read_sql(query.statement, query.session.bind)
        else:
            job_boards = query.all()
            
        return job_boards
    
    except Exception as e:
        print(f"Error fetching job boards: {e}")
        return []
    finally:
        db_session.close()


## helper functions: ##

def _get_or_create_company(db_session, 
                           company_name: str, 
                           sector: str) -> Company:
    """Gets an existing company or creates a new one."""
    company = db_session.query(Company).filter_by(name=company_name).first()
    if company:
        return company

    # Create new company
    company = Company(name=company_name, sector=sector)
    db_session.add(company)
    try:
        db_session.flush()  # Assign ID to company before using it
        print(f"Added Company: {company_name}")
        return company
    except IntegrityError:
        db_session.rollback()
        print(f"Company '{company_name}' already exists (concurrent add?). Fetching existing.")
        # Re-fetch the company that was concurrently added
        return db_session.query(Company).filter_by(name=company_name).first()
    except Exception as e:
        db_session.rollback()
        print(f"Error adding company {company_name}: {e}")
        # Depending on desired behavior, you might re-raise or return None
        return None

def _get_or_create_job_board(db_session,
                             name: str,
                             type: str,
                             link: str,
                             platform: str,
                             company_id: int = None) -> JobBoard:
    """Gets an existing job board by link or creates a new one."""
    job_board = db_session.query(JobBoard).filter_by(link=link).first()
    if job_board:
        return job_board

    # Create new job board
    if company_id:
        job_board = JobBoard(
            type=type,
            link=link,
            platform=platform,
            company_id=company_id
        )
    else:
        job_board = JobBoard(
            type=type,
            link=link,
            platform=platform,
        )
    db_session.add(job_board)
    try:
        db_session.flush()
        print(f"Added Job Board: {name} ({link})")
        return job_board
    except IntegrityError:
        db_session.rollback()
        print(f"Job Board with link '{link}' already exists (concurrent add?). Skipping.")
        # Re-fetch the job board that was concurrently added
        return db_session.query(JobBoard).filter_by(link=link).first()
    except Exception as e:
        db_session.rollback()
        print(f"Error adding job board {name} ({link}): {e}")
        # Depending on desired behavior, you might re-raise or return None
        return None

def _process_job_board(csv_file, 
                       db_session):
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                _process_job_board_row(db_session, row)
            except Exception as e:
                print(f"Error processing row {row}: {e}")

    # Commit all successful changes
    db_session.commit()
    print("Finished updating job boards from CSV.")

def _process_job_board_row(db_session, 
                           row: dict):
    """Processes a single row from the job board CSV for updating."""
    name = row.get('Name')
    job_board_type = row.get('Type')
    sector = row.get('Sector')
    link = row.get('Link')
    platform = row.get('Platform')

    if not all([sector, job_board_type, link, platform]):
        print(f"Skipping row due to missing data: {row}")
        return

    job_board = db_session.query(JobBoard).filter_by(link=link).first()

    if job_board:
        _update_existing_job_board(db_session, job_board, row)
    else:
        _create_new_job_board_from_row(db_session, row)

def _update_existing_job_board(db_session, 
                               job_board: JobBoard, 
                               row: dict):
    """Updates an existing job board and its associated company if necessary."""
    company_name = row.get('Name')
    job_board_type = row.get('Type')
    sector = row.get('Sector')
    link = row.get('Link')
    platform = row.get('Platform')

    print(f"Updating Job Board: {company_name if company_name else platform} ({link})")
    job_board.type = job_board_type
    job_board.platform = platform

    if job_board_type != 'Company':
        return # Only process company updates for 'Company' type job boards

    # Handle company updates for 'Company' type job boards
    if job_board.company and job_board.company.name != company_name:
        new_company = _get_or_create_company(db_session, company_name, sector)
        if new_company:
            job_board.company_id = new_company.id
        return # Company name changed and handled

    if job_board.company and job_board.company.sector != sector:
        job_board.company.sector = sector
        print(f"Updated Company sector: {company_name}")
        return # Company sector updated

    if not job_board.company and company_name:
        # No company linked, create one and link it
        company = _get_or_create_company(db_session, company_name, sector)
        if company:
            job_board.company_id = company.id

def _create_new_job_board_from_row(db_session, 
                                   row: dict):
    """Creates a new job board and its associated company if necessary."""
    company_name = row.get('Name')
    job_board_type = row.get('Type')
    sector = row.get('Sector')
    link = row.get('Link')
    platform = row.get('Platform')

    company = None
    if job_board_type == 'Company':
        company = _get_or_create_company(db_session, company_name, sector)
        if not company:
            print(f"Could not get or create company for new job board: {row}")
            return # Skip job board creation if company creation failed

    _get_or_create_job_board(db_session, company_name, job_board_type, link, platform, company.id if company else None)


def save_job_listing_data_to_db():
    ...
    
