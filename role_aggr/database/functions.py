import os
import csv
import logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from role_aggr.database.model import SessionLocal, Listing, Company, JobBoard, Base, engine
from role_aggr.environment import DATABASE_DIR, DATABASE_FILE, CSV_FILE_PATH
from datetime import datetime as dt
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    
    logger.info(f"Initializing database at: {DATABASE_FILE}")
    
    # Create the database directory if it doesn't exist
    os.makedirs(DATABASE_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    
    logger.info("Database tables created.")

def update_job_boards(csv_file=CSV_FILE_PATH):
    """
    Updates job boards from CSV file.
    If a job board exists, updates its properties.
    If it doesn't exist, creates a new job board.
    """
    
    logger.info(f"Updating job boards from CSV: {csv_file}")
    db_session = SessionLocal()
    try:
        _process_job_board(csv_file, db_session)
    except FileNotFoundError:
        logger.error(f"Error: CSV file not found at {csv_file}")
    except Exception as e:
        db_session.rollback()
        logger.error(f"An error occurred during job board update: {e}")
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
        logger.error(f"Error fetching job boards: {e}")
        return []
    finally:
        db_session.close()

def update_job_listings(all_job_data: list) -> tuple[bool, str]:
    """
    Saves job listing data to the database.

    Args:
        all_job_data (list): A list of job listing dictionaries.

    Returns:
        tuple[bool, str]: A tuple containing a boolean indicating success/failure
                          and a message with statistics or error details.
    """
    db_session = SessionLocal()
    success_count = 0
    failure_messages = []

    try:
        for job_data in all_job_data:
            # Data Validation
            if not isinstance(job_data, dict):
                failure_messages.append(f"Invalid data format: {job_data}. Expected a dictionary.")
                continue

            # Extract data, handling potential missing keys
            job_title = job_data.get('title')
            company_name = job_data.get('company_name')

            job_board_url = job_data.get('job_board_url') # Main URL of the board

            job_link = job_data.get('url') # Specific URL for the job
            location = job_data.get('location_parsed')
            date_posted_str = job_data.get('date_posted_parsed')
            description = job_data.get('description') # Added job description
            
            # EIP-002: Extract intelligent parser location data (city, country, region)
            city = None
            country = None
            region = None
            
            # Check for intelligent parser enhanced location data
            intelligent_location = job_data.get('location_parsed_intelligent')
            if intelligent_location and isinstance(intelligent_location, dict):
                city = intelligent_location.get('city')
                country = intelligent_location.get('country')
                region = intelligent_location.get('region')
                
                # Clean up "Unknown" values - store as None for database consistency
                if city == "Unknown":
                    city = None
                if country == "Unknown":
                    country = None
                if region == "Unknown":
                    region = None
                    
                logger.debug(f"Extracted intelligent location data for {job_title}: city={city}, country={country}, region={region}")

            if not all([job_title, company_name, job_link, job_board_url]):
                failure_messages.append(f"Missing required data for job: {job_title or 'Unknown'}. Data: {job_data}")
                continue

            #Date is expected to be in ISO format from scraper, or None
            date_posted = None
            if date_posted_str:
                try:
                    date_posted = dt.fromisoformat(date_posted_str)
                except ValueError:
                    failure_messages.append(f"Could not convert posted date to datetime object for {job_title}: {date_posted_str}")
                    logger.warning(f"Could not convert posted date to datetime object for {job_title}: {date_posted_str}")
                    continue

            try:
                # Get or create company
                company = _get_or_create_company(db_session, 
                                                 company_name)
                if not company:
                    failure_messages.append(f"Failed to get or create company '{company_name}' for job: {job_title}")
                    logger.error(f"Failed to get or create company '{company_name}' for job: {job_title}")
                    continue

                # Query existing job board
                job_board = db_session.query(JobBoard).filter_by(link=job_board_url).first()

                if not job_board:
                    failure_messages.append(f"Job board with canonical URL '{job_board_url}' not found for {job_title}. Ensure job boards are pre-populated.")
                    logger.error(f"Job board with canonical URL '{job_board_url}' not found for {job_title}.")
                    continue

                # Create Listing object with intelligent parser location data
                listing = Listing(title=job_title,
                                  link=job_link,
                                  location=location,
                                  city=city,
                                  country=country,
                                  region=region,
                                  date_posted=date_posted,
                                  description=description, # Added job description
                                  company_id=company.id,
                                  job_board_id=job_board.id)
                db_session.add(listing)
                db_session.flush() # Flush to get the ID before commit
                success_count += 1
                logger.debug(f"Successfully added job: {job_title}")

            except IntegrityError as e:
                db_session.rollback()
                failure_messages.append(f"Duplicate entry for job {job_title}: {e}")
                logger.warning(f"Duplicate entry for job {job_title}: {e}")
            except Exception as e:
                db_session.rollback()
                failure_messages.append(f"Error saving job {job_title}: {e}")
                logger.error(f"Error saving job {job_title}: {e}")

        db_session.commit()
        return True, f"Successfully saved {success_count} job listings. Failures: {len(failure_messages)}. Messages: {failure_messages}"

    except Exception as e:
        db_session.rollback()
        return False, f"An unexpected error occurred: {e}"
    finally:
        db_session.close()

## helper functions: ##

def _get_or_create_company(db_session,
                           company_name: str,
                           sector: str = None) -> Company:
    """Gets an existing company or creates a new one."""
    company = db_session.query(Company).filter_by(name=company_name).first()
    if company:
        return company

    # Create new company
    company = Company(name=company_name, sector=sector)
    db_session.add(company)
    try:
        db_session.flush()  # Assign ID to company before using it
        logger.info(f"Added Company: {company_name}")
        return company
    except IntegrityError:
        db_session.rollback()
        logger.warning(f"Company '{company_name}' already exists (concurrent add?). Fetching existing.")
        # Re-fetch the company that was concurrently added
        return db_session.query(Company).filter_by(name=company_name).first()
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error adding company {company_name}: {e}")
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
        logger.info(f"Added Job Board: {name} ({link})")
        return job_board
    except IntegrityError:
        db_session.rollback()
        logger.warning(f"Job Board with link '{link}' already exists (concurrent add?). Skipping.")
        # Re-fetch the job board that was concurrently added
        return db_session.query(JobBoard).filter_by(link=link).first()
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error adding job board {name} ({link}): {e}")
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
                logger.error(f"Error processing row {row}: {e}")

    # Commit all successful changes
    db_session.commit()
    logger.info("Finished updating job boards from CSV.")

def _process_job_board_row(db_session,
                           row: dict):
    """Processes a single row from the job board CSV for updating."""
    name = row.get('Name')
    job_board_type = row.get('Type')
    sector = row.get('Sector')
    link = row.get('Link')
    platform = row.get('Platform')

    if not all([sector, job_board_type, link, platform]):
        logger.warning(f"Skipping row due to missing data: {row}")
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

    logger.info(f"Updating Job Board: {company_name if company_name else platform} ({link})")
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
        logger.info(f"Updated Company sector: {company_name}")
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
            logger.error(f"Could not get or create company for new job board: {row}")
            return # Skip job board creation if company creation failed

    _get_or_create_job_board(db_session, company_name, job_board_type, link, platform, company.id if company else None)


