import sys
import os

# Add the parent directory to the path so we can import role_aggr
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from role_aggr.scraper.common.logging import setup_scraper_logger


if __name__ == '__main__':
    # Example usage:
    scraper_logger = setup_scraper_logger()

    scraper_logger.info("Logger setup complete.")
    scraper_logger.warning("This is a warning message.")
    scraper_logger.error("This is an error message.")
    scraper_logger.debug("This debug message should not appear if level is INFO.")

    # Simulate writing multiple log messages to test rotation
    for i in range(10000): # Write enough messages to potentially trigger rotation
        scraper_logger.info(f"Log message number {i}")

    print("Example logging complete. Check role_aggr/logs/scraper/scraper.log for output.")