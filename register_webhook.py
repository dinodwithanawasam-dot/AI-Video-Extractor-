"""
Run this EXACTLY ONCE after deployment to register the initial Google Drive webhook.
Note: You do NOT need to re-run this manually! EventBridge Scheduler automatically 
calls flipline-webhook-renewer Lambda every 6 days to renew it permanently.
"""
import os, uuid, time
from dotenv import load_dotenv
from src.utils.drive_utils import get_drive_service

load_dotenv()

API_URL   = input("Paste your API Gateway URL (e.g. https://abc.execute-api.us-east-1.amazonaws.com/prod): ").strip()
FOLDER_ID = os.getenv("GDRIVE_INPUT_FOLDER_ID")
TOKEN     = os.getenv("PUBLIC_WEBHOOK_TOKEN")

service = get_drive_service()
response = service.files().watch(
    fileId=FOLDER_ID,
    body={
        "id":         str(uuid.uuid4()),
        "type":       "web_hook",
        "address":    f"{API_URL}/webhook/drive",
        "token":      TOKEN,
        "expiration": str((int(time.time()) + 604800) * 1000),  # 7 days in ms
    }
).execute()

print(f"✅ Initial webhook registered successfully! Channel ID: {response.get('id')}")
print(f"   Expires: {response.get('expiration')}")
print(f"   🔄 Automatic renewal is active via EventBridge Scheduler (every 6 days). No manual re-runs needed!")

