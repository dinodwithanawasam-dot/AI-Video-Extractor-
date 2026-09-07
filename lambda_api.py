"""
Lightweight AWS Lambda Handler for Flipline API Gateway.
Exclusively handles:
  1. GET /health
  2. GET /webhook/drive (Google verification challenge)
  3. POST /webhook/drive (Drive file event -> Pushes job to AWS SQS)
  4. GET /api/videos (Fetches processed videos from DynamoDB)

Zero heavy dependencies (No Torch, No Whisper, No MoviePy) to keep
the Lambda deployment package tiny (< 25 MB) and execution ultra-fast (< 50ms).
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from starlette.responses import PlainTextResponse
import boto3

load_dotenv()

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from log import get_logger
from src.utils.db_utils import get_all_videos

logger = get_logger("Lambda_API")

app = FastAPI(title="Flipline Serverless Ingestion API")

# SQS client initialization
_sqs = boto3.client('sqs', region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
_WEBHOOK_TOKEN = os.getenv("PUBLIC_WEBHOOK_TOKEN", "")
_INPUT_FOLDER = os.getenv("GDRIVE_INPUT_FOLDER_ID", "")


@app.get("/health")
@app.get("/prod/health")
async def health_check():
    """Health check endpoint for API Gateway / monitoring."""
    return {
        "status": "ok",
        "service": "flipline-lambda-api",
        "timestamp": str(os.getenv("AWS_LAMBDA_FUNCTION_NAME", "local"))
    }


@app.get("/webhook/drive")
@app.get("/prod/webhook/drive")
async def drive_webhook_verify(token: str = ""):
    """Google calls this GET to confirm our URL is real before sending notifications."""
    expected = os.getenv("PUBLIC_WEBHOOK_TOKEN") or _WEBHOOK_TOKEN
    if not token or token != expected:
        raise HTTPException(status_code=403, detail="Invalid token")
    return PlainTextResponse(token)


@app.post("/webhook/drive")
@app.post("/prod/webhook/drive")
async def drive_webhook_receive(request: Request):
    """Google calls this POST whenever a file is added to the Input folder."""
    state = request.headers.get("X-Goog-Resource-State", "")
    channel_id = request.headers.get("X-Goog-Channel-ID", "")
    logger.info(f"Incoming Google Drive webhook notification: state='{state}', channel='{channel_id}'")

    # Ignore channel setup sync ping
    if state == "sync":
        logger.info("Ignoring 'sync' handshake notification.")
        return {"status": "sync_acknowledged"}

    # Find the newest file in the Input folder
    from src.utils.drive_utils import get_drive_service
    service = get_drive_service()
    if not service:
        logger.error("Failed to acquire Google Drive service")
        raise HTTPException(status_code=500, detail="Google Drive service unavailable")

    folder_id = os.getenv("GDRIVE_INPUT_FOLDER_ID", _INPUT_FOLDER)
    logger.info(f"Checking Google Drive Input Folder: {folder_id}...")

    result = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        orderBy="createdTime desc",
        pageSize=5,
        fields="files(id, name, mimeType)"
    ).execute()

    files = result.get("files", [])
    logger.info(f"Files found in Input folder: {len(files)}")
    if not files:
        logger.warning(f"No files found in Input folder {folder_id}.")
        return {"status": "no_file_found"}

    # Select the first video file or first file
    f = None
    for item in files:
        if "video" in item.get("mimeType", "") or item.get("name", "").endswith((".mp4", ".mov", ".mkv", ".avi")):
            f = item
            break

    if not f:
        f = files[0]
        logger.info(f"No explicitly typed video found, using top file: {f.get('name')}")

    # Push job ticket directly to AWS SQS
    queue_url = os.getenv("AWS_SQS_QUEUE_URL")
    if not queue_url:
        logger.error("AWS_SQS_QUEUE_URL environment variable is missing")
        raise HTTPException(status_code=500, detail="SQS queue not configured")

    _sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"file_id": f["id"], "file_name": f["name"]})
    )
    logger.info(f"Successfully queued SQS job for file: {f['name']} (ID: {f['id']})")
    return {"status": "queued", "file_name": f["name"], "file_id": f["id"]}


@app.get("/api/videos")
@app.get("/prod/api/videos")
async def fetch_videos(limit: int = 50):
    """Fetches the latest processed video metadata records from DynamoDB."""
    try:
        videos = await run_in_threadpool(get_all_videos, limit)
        return {"status": "success", "data": videos}
    except Exception as e:
        logger.error(f"Failed to fetch videos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch videos from DB: {str(e)}")


# ── AWS Lambda Entrypoint (Mangum) ───────────────────────────────
from mangum import Mangum
lambda_handler = Mangum(app, lifespan="off")
