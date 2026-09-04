import logging
import os
import sys
from pathlib import Path

IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Setup logs directory in the project root (or /tmp/logs if inside Lambda)
ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = Path("/tmp/logs") if IS_LAMBDA else (ROOT_DIR / "logs")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError:
    pass

LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def get_logger(name: str) -> logging.Logger:
    """
    Creates and returns a logger that logs to console (and app.log file if not in Lambda).
    Usage: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # Console handler (stdout for terminal and AWS CloudWatch)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(console_handler)

        # File handler only if not in Lambda
        if not IS_LAMBDA:
            try:
                file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
                file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
                logger.addHandler(file_handler)
            except OSError:
                pass

    return logger
