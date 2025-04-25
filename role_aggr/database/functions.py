import os
import csv
from sqlalchemy.exc import IntegrityError
from database.model import SessionLocal, Listing, Company, JobBoard, Base, engine
from environment import DATABASE_DIR, DATABASE_FILE, CSV_FILE_PATH

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

def load_job_boards_from_csv(db_session, csv_file=CSV_FILE_PATH):
    """Loads job boards and companies from the CSV file into the database."""
    print(f"Loading data from CSV: {csv_file}")
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                company_name = row['Name']
                job_board_type = row['Type']
                sector = row['Sector']
                link = row['Link']

                company = None
                if job_board_type == 'Company':
                    # Check if company already exists
                    company = db_session.query(Company).filter_by(name=company_name).first()
                    if not company:
                        # Create new company
                        company = Company(name=company_name, sector=sector)
                        db_session.add(company)
                        try:
                            db_session.flush() # Assign ID to company before using it
                            print(f"Added Company: {company_name}")
                        except IntegrityError:
                            db_session.rollback()
                            print(f"Company '{company_name}' already exists (concurrent add?). Fetching existing.")
                            company = db_session.query(Company).filter_by(name=company_name).first()
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error adding company {company_name}: {e}")
                            continue

                # Check if job board already exists by link
                job_board = db_session.query(JobBoard).filter_by(link=link).first()
                if not job_board:
                    # Create new job board
                    job_board = JobBoard(
                        name=company_name, # Use company name as job board name for consistency
                        type=job_board_type,
                        link=link,
                        company_id=company.id if company else None
                    )
                    db_session.add(job_board)
                    try:
                        db_session.flush()
                        print(f"Added Job Board: {company_name} ({link})")
                    except IntegrityError:
                        db_session.rollback()
                        print(f"Job Board with link '{link}' already exists (concurrent add?). Skipping.")
                    except Exception as e:
                        db_session.rollback()
                        print(f"Error adding job board {company_name} ({link}): {e}")

            db_session.commit()
            print("Finished loading data from CSV.")

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file}")
    except Exception as e:
        db_session.rollback()
        print(f"An error occurred during CSV loading: {e}")


def update_job_boards(csv_file=CSV_FILE_PATH):
    """
    Updates job boards from CSV file.
    If a job board exists, updates its properties.
    If it doesn't exist, creates a new job board.
    """
    print(f"Updating job boards from CSV: {csv_file}")
    print(f"CSV file exists: {os.path.exists(csv_file)}")
    db_session = SessionLocal()
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                company_name = row['Name']
                job_board_type = row['Type']
                sector = row['Sector']
                link = row['Link']

                try:
                    # First, check if the job board exists
                    job_board = db_session.query(JobBoard).filter_by(link=link).first()
                    
                    # If job board exists, we need to handle company updates differently
                    if job_board:
                        # Update existing job board
                        print(f"Updating Job Board: {company_name} ({link})")
                        old_name = job_board.name
                        job_board.name = company_name
                        job_board.type = job_board_type
                        
                        # If it's a company job board, handle company update
                        if job_board_type == 'Company':
                            # If the company name changed, we need to update the company or link to a different one
                            if job_board.company and job_board.company.name != company_name:
                                # Check if a company with the new name already exists
                                new_company = db_session.query(Company).filter_by(name=company_name).first()
                                if new_company:
                                    # Link to existing company with new name
                                    job_board.company_id = new_company.id
                                else:
                                    # Update the existing company's name
                                    job_board.company.name = company_name
                                    job_board.company.sector = sector
                                    print(f"Updated Company: {old_name} -> {company_name}")
                            elif job_board.company:
                                # Update sector if needed
                                if job_board.company.sector != sector:
                                    job_board.company.sector = sector
                                    print(f"Updated Company sector: {company_name}")
                            else:
                                # No company linked, create one
                                company = Company(name=company_name, sector=sector)
                                db_session.add(company)
                                try:
                                    db_session.flush()
                                    print(f"Added Company: {company_name}")
                                except IntegrityError:
                                    db_session.rollback()
                                    print(f"Company '{company_name}' already exists (concurrent add?). Fetching existing.")
                                    company = db_session.query(Company).filter_by(name=company_name).first()
                                job_board.company_id = company.id
                    else:
                        # Create new job board and possibly new company
                        company = None
                        if job_board_type == 'Company':
                            # Check if company already exists
                            company = db_session.query(Company).filter_by(name=company_name).first()
                            if not company:
                                # Create new company
                                company = Company(name=company_name, sector=sector)
                                db_session.add(company)
                                try:
                                    db_session.flush()  # Assign ID to company before using it
                                    print(f"Added Company: {company_name}")
                                except IntegrityError:
                                    db_session.rollback()
                                    print(f"Company '{company_name}' already exists (concurrent add?). Fetching existing.")
                                    company = db_session.query(Company).filter_by(name=company_name).first()
                                except Exception as e:
                                    db_session.rollback()
                                    print(f"Error adding company {company_name}: {e}")
                                    continue
                        
                        # Create new job board
                        job_board = JobBoard(
                            name=company_name,
                            type=job_board_type,
                            link=link,
                            company_id=company.id if company else None
                        )
                        db_session.add(job_board)
                        try:
                            db_session.flush()
                            print(f"Added Job Board: {company_name} ({link})")
                        except IntegrityError:
                            db_session.rollback()
                            print(f"Job Board with link '{link}' already exists (concurrent add?). Skipping.")
                            # Re-fetch the job board to update it instead
                            job_board = db_session.query(JobBoard).filter_by(link=link).first()
                            if job_board:
                                job_board.name = company_name
                                job_board.type = job_board_type
                                if company:
                                    job_board.company_id = company.id
                
                except Exception as e:
                    # Handle exceptions for individual rows without failing the entire process
                    print(f"Error processing job board {company_name} ({link}): {e}")
                    # Continue with the next row
            
            # Commit all successful changes
            db_session.commit()
            print("Finished updating job boards from CSV.")
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file}")
    except Exception as e:
        db_session.rollback()
        print(f"An error occurred during job board update: {e}")
    finally:
        db_session.close()