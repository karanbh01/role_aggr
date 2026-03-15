"""
CLI for running scrapes directly from the terminal.

Usage:
    python scrape.py                    # Scrape all Workday boards (5 pages each)
    python scrape.py --platform workday --max-pages 10
    python scrape.py --platform linkedin --keywords "portfolio manager"
    python scrape.py --test              # Quick test with Deutsche Bank only
"""

import argparse
import asyncio
import logging
import sys

from config import CSV_FILE_PATH
from db import init_db, load_job_boards_from_csv, get_job_boards, save_jobs
from scrapers import SCRAPERS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-12s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("role_aggr")


async def run(args):
    await init_db()
    await load_job_boards_from_csv()

    platform = args.platform.lower()
    scrape_fn = SCRAPERS.get(platform)
    if not scrape_fn:
        logger.error(f"Unknown platform: {platform}. Available: {list(SCRAPERS.keys())}")
        sys.exit(1)

    if args.test:
        # Quick test with one board
        boards = [{"company_name": "Deutsche Bank", "link": "https://db.wd3.myworkdayjobs.com/en-US/DBWebsite"}]
    else:
        boards = await get_job_boards(platform=platform)

    if not boards:
        logger.warning(f"No {platform} boards configured")
        return

    logger.info(f"Scraping {len(boards)} {platform} boards (max_pages={args.max_pages})")
    total_saved = 0

    for board in boards:
        company = board["company_name"] or platform.title()
        url = board["link"]
        logger.info(f"-> {company}")

        try:
            kwargs = {
                "url": url,
                "company": company,
                "max_pages": args.max_pages,
                "show_progress": True,
            }

            # LinkedIn supports keywords
            if platform == "linkedin" and args.keywords:
                kwargs["keywords"] = [args.keywords]

            jobs = await scrape_fn(**kwargs)

            if jobs:
                stats = await save_jobs(jobs)
                total_saved += stats["saved"]
                logger.info(f"  saved={stats['saved']}, skipped={stats['skipped']}")
            else:
                logger.warning(f"  No jobs found")

        except Exception as e:
            logger.error(f"  Failed: {e}")

    logger.info(f"Done. Total saved: {total_saved}")


def main():
    parser = argparse.ArgumentParser(description="role/aggr scraper CLI")
    parser.add_argument("--platform", default="workday", help="Platform to scrape (workday, linkedin)")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per board")
    parser.add_argument("--keywords", default=None, help="Search keywords (LinkedIn only)")
    parser.add_argument("--test", action="store_true", help="Quick test with one board")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
