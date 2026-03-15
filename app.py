"""
FastAPI web application for role/aggr.

Routes:
  GET  /               -> Job listings page (HTML)
  GET  /api/jobs       -> Job listings (JSON)
  POST /api/scrape     -> Trigger a scrape run (background)
  GET  /api/status     -> Scrape status
  GET  /api/boards     -> List job boards
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import TEMPLATES_DIR, STATIC_DIR, SUPPORTED_PLATFORMS
from db import init_db, load_job_boards_from_csv, get_listings, get_filter_options, get_job_boards, save_jobs
from scrapers import SCRAPERS

logger = logging.getLogger("role_aggr")

# -- Scrape state (simple in-memory tracker) --------------------------------
_scrape_status = {
    "running": False,
    "last_run": None,
    "last_result": None,
    "current_company": None,
}


# -- App lifecycle ----------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB and load job boards."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-12s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("Starting role/aggr v2")

    await init_db()
    await load_job_boards_from_csv()

    logger.info("Ready -- database initialized, job boards loaded")
    yield
    logger.info("Shutting down")


app = FastAPI(title="role/aggr", version="2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# -- HTML routes ------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    company: list[str] = Query(default=[]),
    location: list[str] = Query(default=[]),
    search: str = Query(default=""),
):
    """Main page -- job listings with filters."""
    # Clean empty strings from filter lists
    companies = [c for c in company if c.strip()]
    locations = [l for l in location if l.strip()]
    search = search.strip()

    jobs = await get_listings(
        companies=companies or None,
        locations=locations or None,
        search=search or None,
    )
    filters = await get_filter_options()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "companies": filters["companies"],
            "locations": filters["locations"],
            "total_jobs": filters["total_jobs"],
            "selected_companies": companies,
            "selected_locations": locations,
            "search_query": search,
            "scrape_status": _scrape_status,
        },
    )


# -- API routes -------------------------------------------------------------

@app.get("/api/jobs")
async def api_jobs(
    company: list[str] = Query(default=[]),
    location: list[str] = Query(default=[]),
    search: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
):
    """Get job listings as JSON."""
    companies = [c for c in company if c.strip()] or None
    locations = [l for l in location if l.strip()] or None
    return await get_listings(
        companies=companies,
        locations=locations,
        search=search.strip() or None,
        limit=limit,
    )


@app.get("/api/boards")
async def api_boards(platform: str = None):
    """List configured job boards."""
    return await get_job_boards(platform=platform)


@app.get("/api/status")
async def api_status():
    """Get current scrape status."""
    return _scrape_status


@app.post("/api/scrape")
async def api_scrape(
    platform: str = Query(default="workday"),
    max_pages: int = Query(default=5, le=50),
):
    """Trigger a background scrape. Returns immediately."""
    if _scrape_status["running"]:
        return {"status": "already_running", "current_company": _scrape_status["current_company"]}

    if platform.lower() not in SCRAPERS:
        return {"status": "error", "message": f"Unknown platform: {platform}. Available: {list(SCRAPERS.keys())}"}

    # Launch scraping in background
    asyncio.create_task(_run_scrape(platform.lower(), max_pages))
    return {"status": "started", "platform": platform, "max_pages": max_pages}


# -- Background scraping ----------------------------------------------------

async def _run_scrape(platform: str, max_pages: int):
    """Run a full scrape cycle in the background."""
    _scrape_status["running"] = True
    _scrape_status["last_result"] = None
    total_saved = 0
    total_errors = []

    try:
        boards = await get_job_boards(platform=platform)
        scrape_fn = SCRAPERS[platform]

        logger.info(f"Scraping {len(boards)} {platform} boards (max_pages={max_pages})")

        for board in boards:
            company = board["company_name"] or platform.title()
            url = board["link"]
            _scrape_status["current_company"] = company

            logger.info(f"Scraping: {company} @ {url}")

            try:
                jobs = await scrape_fn(
                    url=url,
                    company=company,
                    max_pages=max_pages,
                    show_progress=False,
                )

                if jobs:
                    stats = await save_jobs(jobs)
                    total_saved += stats["saved"]
                    total_errors.extend(stats["errors"])
                    logger.info(f"  {company}: {stats['saved']} saved, {stats['skipped']} skipped")
                else:
                    logger.warning(f"  {company}: no jobs found")

            except Exception as e:
                logger.error(f"  {company}: scrape failed -- {e}")
                total_errors.append(f"{company}: {e}")

            # Brief pause between boards
            await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"Scrape cycle failed: {e}", exc_info=True)
        total_errors.append(str(e))

    finally:
        _scrape_status["running"] = False
        _scrape_status["current_company"] = None
        _scrape_status["last_run"] = datetime.now().isoformat()
        _scrape_status["last_result"] = {
            "platform": platform,
            "saved": total_saved,
            "errors": total_errors[:10],
        }
        logger.info(f"Scrape cycle complete: {total_saved} jobs saved")
