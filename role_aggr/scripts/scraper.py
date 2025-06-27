# scraper.py
import asyncio
import os, sys
from datetime import datetime as dt
from tqdm import tqdm

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from role_aggr.database.functions import get_job_boards
from role_aggr.scraper.config import TARGET_URL
from role_aggr.scraper import scraper


def run_scraper(platform_job_boards,
                max_pages=None, 
                to_csv=False, 
                output_filename=None, 
                show_loading_bar=True):
    
    for platform, boards in tqdm(platform_job_boards.items(), 
                                 desc="Processing Platforms", 
                                 unit="platform", 
                                 disable=not show_loading_bar):
        if platform != "Workday":
            print(f"Skipping {platform} as it is not Workday")
            continue
        
        for board_dict_list in tqdm(boards, 
                                    desc=f"Scraping {platform} Job Boards", 
                                    unit="job_board", 
                                    disable=not show_loading_bar):
            company_name = board_dict_list['company_name']
            target_url = board_dict_list['job_board_url']

            # conditional_print is removed as tqdm will handle progress indication
            # conditional_print(f"Scraping {board_dict['company_name'] if board_dict['company_name'] else platform} at {target_url}", show_loading_bar)
            asyncio.run(scraper(company_name,
                                target_url,
                                platform,
                                max_pages=max_pages,
                                to_csv=to_csv,
                                output_filename=output_filename,
                                show_loading_bar=show_loading_bar))

def main(test=False,
         to_csv=False,
         max_pages=None,
         show_loading_bar=True):
    """
    Main function to run the scraper.
    
    Args:
        test (bool): If True, runs in test mode scraping a predefined URL.
        max_pages (int, optional): The maximum number of pages to scrape when not in test mode.
                                   If None, all available pages will be scraped.
    """
    dt_str = dt.strftime(dt.now(),"%Y%m%d_%H%M%S")
    if test:
        platform_job_boards = {"Workday": [{'company_name': "Deutsche Bank",
                                            'job_board_url': TARGET_URL}]}
        
    else: 
        job_boards = get_job_boards()
        platform_job_boards = {platform: [{'company_name': board.company.name if board.company else None,
                                        'job_board_url': board.link}
                                        for board in job_boards if board.platform == platform]
                            for platform in {board.platform for board in job_boards}}

    run_scraper(platform_job_boards,
                max_pages=max_pages, 
                to_csv=to_csv, 
                output_filename=f"role_aggr/scripts/workday_jobs_playwright_{dt_str}.csv", 
                show_loading_bar=show_loading_bar)

if __name__ == "__main__": 
     main(test=True, max_pages=5)  # Set to True for testing, False for full run