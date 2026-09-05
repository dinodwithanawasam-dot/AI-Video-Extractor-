import os
import json
import boto3
from dotenv import load_dotenv
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from src.utils.drive_utils import get_drive_service

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)
sqs = session.client("sqs")
queue_url = os.getenv("AWS_SQS_QUEUE_URL")
folder_id = os.getenv("GDRIVE_INPUT_FOLDER_ID")

print(f">> Checking Google Drive folder ({folder_id}) for videos...")
service = get_drive_service()

if not service:
    print("❌ Failed to connect to Google Drive service.")
    exit(1)

result = service.files().list(
    q=f"'{folder_id}' in parents and trashed=false",
    orderBy="createdTime desc",
    pageSize=5,
    fields="files(id, name, mimeType)"
).execute()

files = result.get("files", [])
if not files:
    print("⚠️ No files found in the Google Drive Input folder!")
    print("👉 Please drop a small MP4 video into your Google Drive input folder and re-run.")
    exit(0)

# Pick first video file or first file
video_file = None
for f in files:
    if "video" in f.get("mimeType", "") or f.get("name", "").endswith((".mp4", ".mov", ".mkv")):
        video_file = f
        break

if not video_file:
    video_file = files[0]
    print(f"⚠️ Note: First file is not marked video, using anyway: {video_file['name']}")

payload = {"file_id": video_file["id"], "file_name": video_file["name"]}
print(f">> Enqueuing job to AWS SQS: {video_file['name']} ({video_file['id']})...")

response = sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(payload)
)

print(f"✅ Successfully sent message to SQS! MessageId: {response.get('MessageId')}")
print(f">> Payload: {payload}")
