"""
Database models and plain CRUD functions.

No dependency injection, no session yielding. Each function creates its own
async session and cleans up after itself.
"""

import csv
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, desc, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import relationship, declarative_base, selectinload

from config import DATABASE_URL, DATABASE_DIR, CSV_FILE_PATH

logger = logging.getLogger("role_aggr")

# -- Engine & session factory -----------------------------------------------
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


# -- Models -----------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sector = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job_boards = relationship("JobBoard", back_populates="company")
    listings = relationship("Listing", back_populates="company")

    def __repr__(self):
        return f"<Company {self.name}>"


class JobBoard(Base):
    __tablename__ = "job_boards"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    type = Column(String)          # "Company" or "Aggregate"
    platform = Column(String)      # "workday", "linkedin", etc.
    link = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="job_boards")
    listings = relationship("Listing", back_populates="job_board")

    def __repr__(self):
        return f"<JobBoard {self.platform} {self.link[:40]}>"


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    job_board_id = Column(Integer, ForeignKey("job_boards.id"), nullable=False)
    title = Column(String, nullable=False)
    location = Column(String)
    city = Column(String)
    country = Column(String)
    region = Column(String)
    description = Column(Text)
    link = Column(String, unique=True, nullable=False)
    job_id = Column(String)
    date_posted = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="listings")
    job_board = relationship("JobBoard", back_populates="listings")

    __table_args__ = (
        UniqueConstraint("title", "company_id", "link", name="_title_company_link_uc"),
    )

    def __repr__(self):
        return f"<Listing {self.title[:30]}>"


# -- Database lifecycle -----------------------------------------------------

async def init_db():
    """Create all tables if they don't exist."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database initialized at {DATABASE_DIR / 'jobs.db'}")


# -- Company helpers --------------------------------------------------------

async def get_or_create_company(session: AsyncSession, name: str, sector: str = None) -> Company:
    """Get existing company by name, or create a new one."""
    result = await session.execute(select(Company).where(Company.name == name))
    company = result.scalar_one_or_none()
    if company:
        return company

    company = Company(name=name, sector=sector)
    session.add(company)
    await session.flush()
    logger.info(f"Created company: {name}")
    return company


# -- Job board functions ----------------------------------------------------

async def load_job_boards_from_csv(csv_path: str = None):
    """Read job boards CSV and upsert into database."""
    csv_path = csv_path or str(CSV_FILE_PATH)
    logger.info(f"Loading job boards from {csv_path}")

    async with async_session() as session:
        async with session.begin():
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("Name", "").strip()
                    board_type = row.get("Type", "").strip()
                    sector = row.get("Sector", "").strip()
                    link = row.get("Link", "").strip()
                    platform = row.get("Platform", "").strip().lower()

                    if not all([board_type, link, platform]):
                        continue

                    # Check if job board already exists
                    result = await session.execute(select(JobBoard).where(JobBoard.link == link))
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.type = board_type
                        existing.platform = platform
                        if board_type == "Company" and name:
                            company = await get_or_create_company(session, name, sector)
                            existing.company_id = company.id
                    else:
                        company_id = None
                        if board_type == "Company" and name:
                            company = await get_or_create_company(session, name, sector)
                            company_id = company.id

                        board = JobBoard(
                            type=board_type,
                            platform=platform,
                            link=link,
                            company_id=company_id,
                        )
                        session.add(board)

    logger.info("Job boards loaded successfully")


async def get_job_boards(platform: str = None) -> list[dict]:
    """Fetch job boards, optionally filtered by platform. Returns list of dicts."""
    async with async_session() as session:
        query = select(JobBoard).options(selectinload(JobBoard.company))
        if platform:
            query = query.where(func.lower(JobBoard.platform) == platform.lower())
        result = await session.execute(query)
        boards = result.scalars().all()

        return [
            {
                "id": b.id,
                "company_name": b.company.name if b.company else None,
                "type": b.type,
                "platform": b.platform,
                "link": b.link,
            }
            for b in boards
        ]


# -- Listing functions ------------------------------------------------------

async def save_jobs(jobs: list[dict]) -> dict:
    """
    Save a list of job dicts to the database. Returns stats.

    Each job dict should have: title, company, url, job_board_url,
    and optionally: location, city, country, region, description,
    job_id, date_posted (datetime or ISO string).
    """
    saved = 0
    skipped = 0
    errors = []

    async with async_session() as session:
        async with session.begin():
            for job in jobs:
                try:
                    title = job.get("title")
                    company_name = job.get("company")
                    link = job.get("url")
                    board_url = job.get("job_board_url")

                    if not all([title, company_name, link, board_url]):
                        skipped += 1
                        continue

                    # Resolve company
                    company = await get_or_create_company(session, company_name)

                    # Resolve job board
                    result = await session.execute(
                        select(JobBoard).where(JobBoard.link == board_url)
                    )
                    job_board = result.scalar_one_or_none()
                    if not job_board:
                        skipped += 1
                        errors.append(f"No job board for URL: {board_url}")
                        continue

                    # Check for duplicate
                    result = await session.execute(
                        select(Listing).where(Listing.link == link)
                    )
                    if result.scalar_one_or_none():
                        skipped += 1
                        continue

                    # Parse date if string
                    date_posted = job.get("date_posted")
                    if isinstance(date_posted, str):
                        try:
                            date_posted = datetime.fromisoformat(date_posted)
                        except ValueError:
                            date_posted = None

                    listing = Listing(
                        title=title,
                        link=link,
                        location=job.get("location"),
                        city=job.get("city"),
                        country=job.get("country"),
                        region=job.get("region"),
                        description=job.get("description"),
                        job_id=job.get("job_id"),
                        date_posted=date_posted,
                        company_id=company.id,
                        job_board_id=job_board.id,
                    )
                    session.add(listing)
                    saved += 1

                except Exception as e:
                    skipped += 1
                    errors.append(f"{job.get('title', '?')}: {e}")
                    logger.warning(f"Error saving job: {e}")

    stats = {"saved": saved, "skipped": skipped, "errors": errors[:10]}
    logger.info(f"save_jobs: {saved} saved, {skipped} skipped")
    return stats


async def get_listings(
    companies: list[str] = None,
    locations: list[str] = None,
    search: str = None,
    limit: int = 500,
) -> list[dict]:
    """Fetch listings with optional filters. Returns list of dicts."""
    async with async_session() as session:
        query = (
            select(Listing)
            .options(selectinload(Listing.company), selectinload(Listing.job_board))
            .order_by(desc(Listing.date_posted).nullslast(), desc(Listing.id))
            .limit(limit)
        )

        if companies:
            query = query.join(Company).where(Company.name.in_(companies))
        if locations:
            query = query.where(Listing.location.in_(locations))
        if search:
            query = query.where(Listing.title.ilike(f"%{search}%"))

        result = await session.execute(query)
        listings = result.scalars().all()

        now = datetime.now(timezone.utc)
        return [
            {
                "title": l.title,
                "company": l.company.name if l.company else "N/A",
                "location": l.location or "N/A",
                "city": l.city,
                "country": l.country,
                "region": l.region,
                "date_posted": l.date_posted.strftime("%b %d, %Y") if l.date_posted else "Unknown",
                "url": l.link,
                "is_new": l.date_posted and (now - l.date_posted).total_seconds() < 86400 if l.date_posted else False,
            }
            for l in listings
        ]


async def get_filter_options() -> dict:
    """Get unique company names and locations for filter dropdowns."""
    async with async_session() as session:
        # Companies
        result = await session.execute(
            select(Company.name).distinct().order_by(Company.name)
        )
        companies = [row[0] for row in result.all()]

        # Locations
        result = await session.execute(
            select(Listing.location)
            .distinct()
            .where(Listing.location.isnot(None), Listing.location != "", Listing.location != "N/A")
            .order_by(Listing.location)
        )
        locations = [row[0] for row in result.all() if row[0] and row[0].strip()]

        # Job count
        result = await session.execute(select(func.count(Listing.id)))
        total = result.scalar()

        return {"companies": companies, "locations": locations, "total_jobs": total}
