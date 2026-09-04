"""
Webhook renewal handler — called by EventBridge Scheduler every 6 days.
Registers a fresh Google Drive webhook to replace the expiring one.
"""
import os
import uuid
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def renew_webhook(api_url: str = None):
    """Register/renew the Google Drive push notification webhook."""
    from src.utils.drive_utils import get_drive_service

    service   = get_drive_service()
    folder_id = os.getenv("GDRIVE_INPUT_FOLDER_ID")
    token     = os.getenv("PUBLIC_WEBHOOK_TOKEN", "")
    url       = api_url or os.getenv("PUBLIC_API_URL", "")

    if not url:
        raise ValueError("PUBLIC_API_URL environment variable is not set!")

    channel_id  = str(uuid.uuid4())
    expiry_ms   = str((int(time.time()) + 604800) * 1000)  # 7 days from now

    response = service.files().watch(
        fileId=folder_id,
        body={
            "id":         channel_id,
            "type":       "web_hook",
            "address":    f"{url}/webhook/drive",
            "token":      token,
            "expiration": expiry_ms,
        }
    ).execute()

    logger.info(f"✅ Webhook renewed! Channel: {channel_id}")
    logger.info(f"   Expires: {response.get('expiration')}")
    return response


# ── Lambda entry point ────────────────────────────────────────────
def lambda_handler(event, context):
    """Called by EventBridge Scheduler every 6 days."""
    try:
        result = renew_webhook()
        return {"status": "renewed", "channel_id": result.get("id")}
    except Exception as e:
        logger.error(f"Webhook renewal failed: {e}", exc_info=True)
        raise
