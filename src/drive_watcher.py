import os
import time
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
import redis

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from src.utils.drive_utils import get_drive_service, list_mp4_files, move_file
from log import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv(ROOT_DIR / ".env")

INPUT_FOLDER_ID = os.getenv("GDRIVE_INPUT_FOLDER_ID")
ARCHIVE_FOLDER_ID = os.getenv("GDRIVE_ARCHIVE_FOLDER_ID")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Redis connection
try:
    redis_client = redis.Redis.from_url(REDIS_URL)
    redis_client.ping()
    logger.info("Connected to Redis successfully.")
except Exception as e:
    logger.error(f"Could not connect to Redis: {e}")
    sys.exit(1)

def run_watcher():
    """Polls Google Drive every 60 seconds for new files and queues them."""
    if not INPUT_FOLDER_ID or not ARCHIVE_FOLDER_ID:
        logger.error("Missing Google Drive folder IDs in .env")
        sys.exit(1)

    logger.info("Starting Google Drive Watcher...")
    
    while True:
        try:
            # 1. Authenticate with Google Drive
            service = get_drive_service()
            if not service:
                logger.error("Failed to authenticate with Google Drive. Retrying in 60s...")
                time.sleep(60)
                continue

            # 2. Check for new .mp4 files in the Input folder
            logger.info("Checking for new files...")
            files = list_mp4_files(service, INPUT_FOLDER_ID)
            
            if files:
                logger.info(f"Found {len(files)} new file(s) in Drive.")
                
                for f in files:
                    file_id = f.get('id')
                    file_name = f.get('name')
                    
                    # 3. Push to Redis Queue
                    job_data = json.dumps({"file_id": file_id, "file_name": file_name})
                    redis_client.lpush("video_processing_queue", job_data)
                    logger.info(f"Queued job for: {file_name}")
                    
                    # 4. Move file to Archive folder
                    move_file(service, file_id, ARCHIVE_FOLDER_ID)
            else:
                logger.info("No new files found.")

        except Exception as e:
            logger.error(f"Error in Watcher loop: {e}")

        # Wait 60 seconds before polling again
        time.sleep(60)

if __name__ == "__main__":
    run_watcher()
