import logging
import os
from logging.handlers import RotatingFileHandler

def setup_scraper_logger():
    """
    Sets up a rotating file logger for the scraper.

    Configures logging to write to 'role_aggr/logs/scraper/scraper.log'
    with a specific format and file rotation. Includes both file and console handlers.
    """
    logger_name = 'scraper'
    log_file_path = 'role_aggr/logs/scraper/scraper.log'
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    max_log_size_bytes = 5 * 1024 * 1024  # 5MB
    backup_log_files = 5
    default_log_level = logging.INFO

    # Ensure the log directory exists
    log_dir = os.path.dirname(log_file_path)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            print(f"Error creating log directory {log_dir}: {e}")
            # Fallback: if directory creation fails, logger might not work as expected
            # but we continue to try and set up the logger.

    # Get the logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(default_log_level)

    # Prevent duplicate handlers if the function is called multiple times
    if not logger.handlers:
        # File Handler with Rotation
        try:
            file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=max_log_size_bytes,
                backupCount=backup_log_files,
                encoding='utf-8'
            )
            formatter = logging.Formatter(log_format)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Error setting up file handler for {log_file_path}: {e}")

        # Console Handler
        try:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter) # Use the same formatter
            logger.addHandler(console_handler)
        except Exception as e:
            print(f"Error setting up console handler: {e}")

    # Prevent logs from being passed to the root logger
    logger.propagate = False

    return logger

