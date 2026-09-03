import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

from log import get_logger

logger = get_logger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']


def get_drive_service(credentials_path="credentials.json"):
    """Authenticates and returns a Google Drive API service instance."""
    try:
        creds_path = ROOT_DIR / credentials_path
        if not creds_path.exists():
            logger.error(f"Credentials file not found at {creds_path}")
            return None

        creds = service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error authenticating with Google Drive: {e}")
        return None


def list_mp4_files(service, folder_id):
    """Lists all .mp4 files inside a specific Google Drive folder."""
    if not service:
        return []

    try:
        query = f"'{folder_id}' in parents and mimeType='video/mp4' and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType)',
            pageSize=50
        ).execute()
        return results.get('files', [])
    except Exception as e:
        logger.error(f"Error listing files in folder {folder_id}: {e}")
        return []


def move_file(service, file_id, dest_folder_id):
    """Moves a file to a new folder by updating its parents."""
    if not service:
        return False

    try:
        # Retrieve the existing parents to remove
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))

        # Move the file to the new folder
        service.files().update(
            fileId=file_id,
            addParents=dest_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

        logger.info(f"Successfully moved file {file_id} to folder {dest_folder_id}")
        return True
    except Exception as e:
        logger.error(f"Error moving file {file_id}: {e}")
        return False


def download_file(service, file_id: str, output_path: str) -> bool:
    """
    Downloads a file from Google Drive to a local path using chunked streaming.
    Uses 10MB chunks to handle large video files without running out of memory.
    Returns True on success, False on failure.
    """
    if not service:
        return False

    try:
        request = service.files().get_media(fileId=file_id)
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)  # 10 MB chunks
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(f"Downloading {dest.name}: {int(status.progress() * 100)}%")

        logger.info(f"✓ Downloaded: {dest.name}")
        return True
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}")
        # Clean up any partial download
        dest = Path(output_path)
        if dest.exists():
            dest.unlink()
        return False
