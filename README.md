# role/aggr -- Finance Job Aggregator

## Quick Start

```bash
git clone <repo>
cd role_aggr
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python run.py
```

Open http://localhost:8000 (or the network URL shown in the terminal).

## Scraping Jobs

From the web UI: click "Scrape Workday" or "Scrape LinkedIn" in the sidebar.

From the terminal:
```bash
python scrape.py --test                    # Quick test (Deutsche Bank only)
python scrape.py --platform workday        # All Workday boards
python scrape.py --platform linkedin       # LinkedIn finance jobs
```

## Project Structure

```
├── app.py              # FastAPI web application
├── config.py           # All configuration
├── db.py               # Database models + CRUD
├── scrapers/
│   ├── __init__.py     # Platform registry
│   ├── helpers.py      # Shared utilities
│   ├── workday.py      # Workday scraper
│   └── linkedin.py     # LinkedIn scraper
├── templates/           # Jinja2 templates
├── static/css/          # Stylesheets
├── scrape.py           # CLI scraper
├── run.py              # Server entry point (LAN accessible)
└── job_boards.csv      # Seed data
```

## Adding a New Scraper

1. Create `scrapers/newplatform.py` with an async function
2. Add one line to `scrapers/__init__.py`
3. Done

## License

MIT
