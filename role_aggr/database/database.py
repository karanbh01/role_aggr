import os
import sys
import csv
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, UniqueConstraint, DateTime # Import DateTime
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.exc import IntegrityError
import datetime # Import datetime for default value

# Define the database file path relative to this script's location
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(DATABASE_DIR, 'job_database.db')
# Correct path: Go up three levels from database.py to reach the workspace root
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(DATABASE_DIR)))
CSV_FILE_PATH = os.path.join(WORKSPACE_ROOT, 'job_boards.csv')

# Create the base class for declarative models
Base = declarative_base()

# Define the Company model
class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sector = Column(String)

    # Relationships
    job_boards = relationship("JobBoard", back_populates="company")
    listings = relationship("Listing", back_populates="company")

    def __repr__(self):
        return f"<Company(name='{self.name}', sector='{self.sector}')>"

# Define the JobBoard model
class JobBoard(Base):
    __tablename__ = 'job_boards'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String) # e.g., 'Aggregate', 'Company'
    link = Column(String, unique=True, nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True) # Nullable for aggregate boards

    # Relationships
    company = relationship("Company", back_populates="job_boards")
    listings = relationship("Listing", back_populates="job_board")

    def __repr__(self):
        return f"<JobBoard(name='{self.name}', type='{self.type}', link='{self.link}')>"

# Define the Listing model
class Listing(Base):
    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text, nullable=True) # Allow for longer descriptions
    link = Column(String, unique=True, nullable=False) # Unique link to avoid duplicates
    # Change date_posted to DateTime type
    date_posted = Column(DateTime, nullable=True, default=datetime.datetime.min) # Use DateTime, provide a default
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    job_board_id = Column(Integer, ForeignKey('job_boards.id'), nullable=False)

    # Relationships
    company = relationship("Company", back_populates="listings")
    job_board = relationship("JobBoard", back_populates="listings")

    # Add a unique constraint for title, company_id, and link to further prevent duplicates
    __table_args__ = (UniqueConstraint('title', 'company_id', 'link', name='_title_company_link_uc'),)


    def __repr__(self):
        return f"<Listing(title='{self.title}', company='{self.company.name if self.company else 'N/A'}', link='{self.link}')>"


# Database setup
engine = create_engine(f'sqlite:///{DATABASE_FILE}')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


if __name__ == "__main__":
    # This allows running the script directly to initialize the DB and load data
    print("Running database setup...")
    init_db()
    db = next(get_db()) # Get a session
    load_job_boards_from_csv(db)
    db.close()
    print("Database setup complete.")