from sqlalchemy import or_, func, case, desc
from datetime import datetime, timedelta
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

def get_all_listings(search=None, city=None, country=None, company=None, location=None, date_filter=None, page=1, per_page=20):
    """
    Fetches all job listings with search, filtering, relevance scoring, and pagination.

    Args:
        search (str): Search term for title and description.
        city (str): Filter by city.
        country (str): Filter by country.
        company (list): Filter by company names.
        location (list): Filter by location strings.
        date_filter (str): Filter by date ('24h', '7d', 'new').
        page (int): Page number for pagination (minimum 1).
        per_page (int): Number of items per page (minimum 1, maximum 100).

    Returns:
        tuple: (list of listings, total_items count)
    """
    db_session = SessionLocal()
    try:
        # Validate input parameters
        if not isinstance(page, int) or page < 1:
            logger.warning(f"Invalid page parameter {page} provided. Defaulting to 1.")
            page = 1
        if not isinstance(per_page, int) or per_page < 1:
            logger.warning(f"Invalid per_page parameter {per_page} provided. Defaulting to 20.")
            per_page = 20
        elif per_page > 100:
            logger.warning(f"per_page parameter {per_page} exceeds maximum of 100. Setting to 100.")
            per_page = 100
        
        # Clean and validate search term
        if search is not None:
            search = search.strip()
            if not search:
                search = None
        
        # Clean and validate location filters
        if city is not None:
            city = city.strip()
            if not city:
                city = None
        if country is not None:
            country = country.strip()
            if not country:
                country = None
        
        # Clean and validate company filter
        if company is not None:
            if isinstance(company, str):
                company = [company.strip()] if company.strip() else None
            elif isinstance(company, list):
                company = [c.strip() for c in company if c.strip()]
                if not company:
                    company = None
        
        # Clean and validate location filter
        if location is not None:
            if isinstance(location, str):
                location = [location.strip()] if location.strip() else None
            elif isinstance(location, list):
                location = [l.strip() for l in location if l.strip()]
                if not location:
                    location = None
        
        # Validate date_filter parameter
        if date_filter is not None and date_filter not in ['24h', '7d', 'new']:
            logger.warning(f"Invalid date_filter parameter {date_filter}. Ignoring filter.")
            date_filter = None

        # Build query with eager loading to prevent N+1 queries
        if search:
            logger.info(f"Processing search query: '{search}'")
            # Escape special characters for SQL LIKE queries
            search_escaped = search.replace('%', '\\%').replace('_', '\\_')
            logger.info(f"Escaped search query: '{search_escaped}'")
            
            # Enhanced relevance scoring
            relevance_score = case(
                
                # Exact title match gets highest score
                (func.lower(Listing.title) == func.lower(search), 100),
                # Title starts with search term
                (func.lower(Listing.title).like(func.lower(f"{search_escaped}%")), 80),
                # Title contains search term
                (func.lower(Listing.title).like(func.lower(f"%{search_escaped}%")), 60),
                # Description contains search term
                (func.lower(Listing.description).like(func.lower(f"%{search_escaped}%")), 20),
            
                else_=0
            )
            
            # Query with relevance score for search results
            query = db_session.query(Listing, relevance_score.label('relevance_score')).options(
                joinedload(Listing.company),
                joinedload(Listing.job_board)
            )
            
            # Apply search filters
            search_filter = or_(
                func.lower(Listing.title).like(func.lower(f"%{search_escaped}%")),
                func.lower(Listing.description).like(func.lower(f"%{search_escaped}%"))
            )
            query = query.filter(search_filter)
            query = query.order_by(desc(relevance_score), desc(Listing.date_posted))
        else:
            # Default query without relevance score when no search
            query = db_session.query(Listing).options(
                joinedload(Listing.company),
                joinedload(Listing.job_board)
            )
            query = query.order_by(desc(Listing.date_posted))

        # Location filtering with case-insensitive search
        if city:
            city_escaped = city.replace('%', '\\%').replace('_', '\\_')
            query = query.filter(func.lower(Listing.city).like(func.lower(f"%{city_escaped}%")))
        if country:
            country_escaped = country.replace('%', '\\%').replace('_', '\\_')
            query = query.filter(func.lower(Listing.country).like(func.lower(f"%{country_escaped}%")))
        
        # Company filtering
        if company:
            query = query.join(Company).filter(Company.name.in_(company))
            
        # Location filtering
        if location:
            location_filters = []
            for loc in location:
                loc_escaped = loc.replace('%', '\\%').replace('_', '\\_')
                location_filters.append(func.lower(Listing.location).like(func.lower(f"%{loc_escaped}%")))
            query = query.filter(or_(*location_filters))

        # Date filtering with null-safe comparisons
        if date_filter == "24h":
            date_threshold = datetime.now() - timedelta(days=1)
            query = query.filter(
                Listing.date_posted.isnot(None),
                Listing.date_posted >= date_threshold
            )
        elif date_filter == "7d":
            date_threshold = datetime.now() - timedelta(days=7)
            query = query.filter(
                Listing.date_posted.isnot(None),
                Listing.date_posted >= date_threshold
            )
        elif date_filter == "new":
            date_threshold = datetime.now() - timedelta(hours=24)
            query = query.filter(
                Listing.date_posted.isnot(None),
                Listing.date_posted >= date_threshold
            )

        # Get total count before applying pagination
        if search:
            # For search queries, we need to count the base query without the added columns
            count_query = db_session.query(Listing).options(
                joinedload(Listing.company),
                joinedload(Listing.job_board)
            )
            count_query = count_query.filter(search_filter)
            if city:
                count_query = count_query.filter(func.lower(Listing.city).like(func.lower(f"%{city_escaped}%")))
            if country:
                count_query = count_query.filter(func.lower(Listing.country).like(func.lower(f"%{country_escaped}%")))
            if company:
                count_query = count_query.join(Company).filter(Company.name.in_(company))
            if location:
                location_filters = []
                for loc in location:
                    loc_escaped = loc.replace('%', '\\%').replace('_', '\\_')
                    location_filters.append(func.lower(Listing.location).like(func.lower(f"%{loc_escaped}%")))
                count_query = count_query.filter(or_(*location_filters))
            if date_filter == "24h":
                count_query = count_query.filter(
                    Listing.date_posted.isnot(None),
                    Listing.date_posted >= datetime.now() - timedelta(days=1)
                )
            elif date_filter == "7d":
                count_query = count_query.filter(
                    Listing.date_posted.isnot(None),
                    Listing.date_posted >= datetime.now() - timedelta(days=7)
                )
            elif date_filter == "new":
                count_query = count_query.filter(
                    Listing.date_posted.isnot(None),
                    Listing.date_posted >= datetime.now() - timedelta(hours=24)
                )
            total_items = count_query.count()
        else:
            total_items = query.count()

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.limit(per_page).offset(offset)

        listings = query.all()
        
        # Process results based on whether we have search results with relevance scores
        if search:
            # For search results, listings is a list of tuples (Listing, relevance_score)
            processed_listings = []
            for listing_tuple in listings:
                listing_obj = listing_tuple[0]
                relevance_score = listing_tuple[1]
                processed_listings.append((listing_obj, relevance_score))
            logger.info(f"Retrieved {len(processed_listings)} search listings (page {page}, total: {total_items})")
            return processed_listings, total_items
        else:
            # For non-search results, listings are just Listing objects
            logger.info(f"Retrieved {len(listings)} listings (page {page}, total: {total_items})")
            return listings, total_items

    except Exception as e:
        logger.error(f"Error fetching listings: {e}")
        return [], 0
    finally:
        db_session.close()

def get_unique_cities():
    """
    Fetches all unique cities from job listings.
    
    Returns:
        list: List of unique city names (excluding None/empty values)
    """
    db_session = SessionLocal()
    try:
        cities = db_session.query(Listing.city).distinct().filter(
            Listing.city.isnot(None),
            Listing.city != ''
        ).order_by(Listing.city).all()
        
        # Extract city names from result tuples and filter out any remaining empty values
        city_list = [city[0] for city in cities if city[0] and city[0].strip()]
        
        logger.info(f"Retrieved {len(city_list)} unique cities")
        return city_list
        
    except Exception as e:
        logger.error(f"Error fetching unique cities: {e}")
        return []
    finally:
        db_session.close()

def get_unique_countries():
    """
    Fetches all unique countries from job listings.
    
    Returns:
        list: List of unique country names (excluding None/empty values)
    """
    db_session = SessionLocal()
    try:
        countries = db_session.query(Listing.country).distinct().filter(
            Listing.country.isnot(None),
            Listing.country != ''
        ).order_by(Listing.country).all()
        
        # Extract country names from result tuples and filter out any remaining empty values
        country_list = [country[0] for country in countries if country[0] and country[0].strip()]
        
        logger.info(f"Retrieved {len(country_list)} unique countries")
        return country_list
        
    except Exception as e:
        logger.error(f"Error fetching unique countries: {e}")
        return []
    finally:
        db_session.close()

def get_unique_companies():
    """
    Fetches all unique company names from job listings.
    
    Returns:
        list: List of unique company names (excluding None/empty values)
    """
    db_session = SessionLocal()
    try:
        companies = db_session.query(Company.name).distinct().filter(
            Company.name.isnot(None),
            Company.name != ''
        ).order_by(Company.name).all()
        
        # Extract company names from result tuples and filter out any remaining empty values
        company_list = [company[0] for company in companies if company[0] and company[0].strip()]
        
        logger.info(f"Retrieved {len(company_list)} unique companies")
        return company_list
        
    except Exception as e:
        logger.error(f"Error fetching unique companies: {e}")
        return []
    finally:
        db_session.close()

def get_unique_locations():
    """
    Fetches all unique location strings from job listings.
    
    Returns:
        list: List of unique location strings (excluding None/empty values)
    """
    db_session = SessionLocal()
    try:
        locations = db_session.query(Listing.location).distinct().filter(
            Listing.location.isnot(None),
            Listing.location != ''
        ).order_by(Listing.location).all()
        
        # Extract location strings from result tuples and filter out any remaining empty values
        location_list = [location[0] for location in locations if location[0] and location[0].strip()]
        
        logger.info(f"Retrieved {len(location_list)} unique locations")
        return location_list
        
    except Exception as e:
        logger.error(f"Error fetching unique locations: {e}")
        return []
    finally:
        db_session.close()
