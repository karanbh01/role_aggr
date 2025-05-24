import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, UniqueConstraint, DateTime # Import DateTime
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
import datetime
from datetime import datetime as dt # Import datetime for default value
from role_aggr.environment import DATABASE_FILE

# Create the base class for declarative models
Base = declarative_base()

# Define the Company model
class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sector = Column(String)
    added_at = Column(DateTime(timezone=True), nullable=False, default=dt.now(datetime.timezone.utc)) 
    updated_at = Column(DateTime(timezone=True), onupdate=dt.now(datetime.timezone.utc)) 
    
    # Relationships
    job_boards = relationship("JobBoard", back_populates="company")
    listings = relationship("Listing", back_populates="company")

    def __repr__(self):
        return f"<Company(name='{self.name}', sector='{self.sector}')>"

# Define the JobBoard model
class JobBoard(Base):
    __tablename__ = 'job_boards'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True) # Nullable for aggregate boards
    type = Column(String) # e.g., 'Aggregate', 'Company'
    platform = Column(String)
    link = Column(String, unique=True, nullable=False)
    added_at = Column(DateTime(timezone=True), nullable=False, default=dt.now(datetime.timezone.utc)) 
    updated_at = Column(DateTime(timezone=True), onupdate=dt.now(datetime.timezone.utc)) 
    
    # Relationships
    company = relationship("Company", back_populates="job_boards")
    listings = relationship("Listing", back_populates="job_board")

    def __repr__(self):
        return f"<JobBoard(name='{self.name}', type='{self.type}', link='{self.link}')>"

# Define the Listing model
class Listing(Base):
    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    job_board_id = Column(Integer, ForeignKey('job_boards.id'), nullable=False)
    title = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text, nullable=True) # Allow for longer descriptions
    link = Column(String, unique=True, nullable=False) # Unique link to avoid duplicates
    # Change date_posted to DateTime type
    date_posted = Column(DateTime(timezone=True), nullable=True, default=dt.min.replace(tzinfo=datetime.timezone.utc)) # Use timezone-aware DateTime
    added_at = Column(DateTime(timezone=True), nullable=False, default=dt.now(datetime.timezone.utc)) 
    updated_at = Column(DateTime(timezone=True), onupdate=dt.now(datetime.timezone.utc)) 

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
