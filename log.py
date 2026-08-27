import logging
import os
from pathlib import Path

# Setup logs directory in the project root
ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def get_logger(name: str) -> logging.Logger:
    """
    Creates and returns a logger that logs to both console and app.log file.
    Usage: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding handlers multiple times if logger already exists
    if not logger.handlers:
        # File handler (saves logs to logs/app.log)
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        
        # Console handler (prints logs to terminal)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
