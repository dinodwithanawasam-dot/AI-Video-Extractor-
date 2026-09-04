import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.concurrency import run_in_threadpool
from starlette.responses import PlainTextResponse

load_dotenv()

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from log import get_logger
from src.ingestion import process_video_input
from src.transcription import load_whisper_model, transcribe_audio
from src.ai_logic import analyze_transcript
from src.video_editor import cut_and_save_reels, create_highlights_video
from src.cloudinary_storage import build_folder, upload_pipeline_results, delete_local_files
from src.utils.db_utils import get_all_videos

logger = get_logger("FastAPI_Server")

# Lifespan context manager to load the model on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI Server...")
    logger.info("Pre-loading OpenAI Whisper model for zero-latency inference...")
    # Load model synchronously in a threadpool so we don't block the async event loop during startup
    app.state.whisper_model = await run_in_threadpool(load_whisper_model)
    logger.info("Whisper model loaded successfully!")
    yield
    logger.info("Shutting down FastAPI Server...")
    app.state.whisper_model = None

app = FastAPI(title="Autonomous Video Extraction AI", lifespan=lifespan)

@app.get("/health")
async def health_check():
    """Docker/load-balancer healthcheck endpoint."""
    whisper_ready = hasattr(app.state, "whisper_model") and app.state.whisper_model is not None
    return {
        "status": "ok" if whisper_ready else "starting",
        "whisper_model_loaded": whisper_ready
    }

# ── Module-level SQS client ──────────────────────────────────────
import boto3 as _boto3
import json as _json
_sqs = _boto3.client('sqs', region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
_WEBHOOK_TOKEN = os.getenv("PUBLIC_WEBHOOK_TOKEN", "")
_INPUT_FOLDER   = os.getenv("GDRIVE_INPUT_FOLDER_ID", "")

@app.get("/webhook/drive")
async def drive_webhook_verify(token: str = ""):
    """Google calls this GET to confirm our URL is real before sending notifications."""
    if token != _WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return PlainTextResponse(token)

@app.post("/webhook/drive")
async def drive_webhook_receive(request: Request):
    """Google calls this POST whenever a file is added to the Input folder."""
    state = request.headers.get("X-Goog-Resource-State", "")

    # Only care about file additions
    if state not in ("add", "update", "change"):
        return {"status": "ignored", "state": state}

    # Find the newest file in the Input folder
    from src.utils.drive_utils import get_drive_service
    service = get_drive_service()
    result = service.files().list(
        q=f"'{_INPUT_FOLDER}' in parents and trashed=false",
        orderBy="createdTime desc",
        pageSize=1,
        fields="files(id, name, mimeType)"
    ).execute()

    files = result.get("files", [])
    if not files:
        return {"status": "no_file_found"}

    f = files[0]
    if "video" not in f.get("mimeType", ""):
        return {"status": "not_a_video", "mime": f.get("mimeType")}

    # Push job to SQS
    _sqs.send_message(
        QueueUrl=os.getenv("AWS_SQS_QUEUE_URL"),
        MessageBody=_json.dumps({"file_id": f["id"], "file_name": f["name"]})
    )
    logger.info(f"Queued job: {f['name']}")
    return {"status": "queued", "file_name": f["name"]}


@app.get("/api/videos")
async def fetch_videos(limit: int = 50):
    """Fetches the latest processed videos from DynamoDB for the Dashboard."""
    try:
        videos = await run_in_threadpool(get_all_videos, limit)
        return {"status": "success", "data": videos}
    except Exception as e:
        logger.error(f"Failed to fetch videos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch videos from DB: {str(e)}")

def apply_ffmpeg_processing(video_path: str, with_logo: bool = False) -> str:
    import subprocess
    from src.utils.ffmpeg_utils import build_concat_command
    
    output_dir = ROOT_DIR / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    stem = Path(video_path).stem
    suffix = "_longform" if with_logo else "_denoised"
    out_path = output_dir / f"{stem}{suffix}.mp4"
    
    logo_path = ROOT_DIR / "logo" / "branding.jpeg"
    intro_path = ROOT_DIR / "media" / "video" / "start.mp4"
    outro_path = ROOT_DIR / "media" / "video" / "end.mp4"
    
    has_media = intro_path.exists() and outro_path.exists()
    use_logo = str(logo_path) if (with_logo and logo_path.exists()) else None

    if has_media:
        # Use our new robust concat command that handles different resolutions and adds the logo
        cmd = build_concat_command(
            main_video_path = video_path,
            intro_path      = str(intro_path),
            outro_path      = str(outro_path),
            out_path        = str(out_path),
            logo_path       = use_logo
        )
    else:
        # Fallback to old behavior if media files are missing
        if use_logo:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", use_logo,
                "-filter_complex",
                "[1:v]format=yuva420p,colorchannelmixer=aa=0.7,scale=-1:ih*0.055[logo];[0:v][logo]overlay=W-w-20:20[vout]",
                "-map", "[vout]", "-map", "0:a",
                "-af", "afftdn=nf=-25",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path)
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-c:v", "copy",
                "-af", "afftdn=nf=-25",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path)
            ]
        
    subprocess.run(cmd, capture_output=True, check=True)
    return str(out_path)

@app.post("/process/long")
async def process_long(
    email: str     = Form(...),
    file:  UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
    if not email:
        raise HTTPException(status_code=400, detail="Email must be provided.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"[{email}] Received file upload for long form: {file.filename}")
    try:
        # Save uploaded file locally
        input_dir = ROOT_DIR / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        source = str(input_dir / file.filename)

        with open(source, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info("[STEP 1/3] Ingesting Video...")
        video_path, _ = await run_in_threadpool(process_video_input, source)

        logger.info("[STEP 2/3] Applying Noise Cancellation & Watermark...")
        final_video = await run_in_threadpool(apply_ffmpeg_processing, video_path, True)

        logger.info("[STEP 3/3] Extracting audio from final video...")
        audio_path = final_video.replace('.mp4', '.mp3')
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", final_video,
                "-vn", "-c:a", "libmp3lame", "-b:a", "192k", audio_path
            ], capture_output=True, check=True)
            logger.info(f"Audio extracted to: {audio_path}")
        except Exception as e:
            logger.warning(f"Audio extraction failed: {e}")
            audio_path = ""

        # --- Upload to Cloudinary & clean up local files ---
        # Keys MUST match what upload_pipeline_results and delete_local_files expect
        local_results = {
            "denoised_video": final_video,
            "denoised_audio": audio_path,
        }
        folder = build_folder(email, file.filename, timestamp)
        logger.info(f"[STEP +] Uploading outputs to Cloudinary folder: {folder}")
        cdn_results = await run_in_threadpool(upload_pipeline_results, local_results, folder)
        await run_in_threadpool(delete_local_files, local_results, source)
        logger.info("Cloudinary upload complete, local files cleaned up.")

        return {
            "status":       "success",
            "folder":       folder,
            "video_path":   cdn_results.get("denoised_video", ""),
            "audio_path":   cdn_results.get("denoised_audio", ""),
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

@app.post("/process/short")
async def process_short(
    email: str        = Form(...),
    file:  UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
    if not email:
        raise HTTPException(status_code=400, detail="Email must be provided.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"[{email}] Received file upload for short form: {file.filename}")
    try:
        # Save uploaded file locally
        input_dir = ROOT_DIR / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        source = str(input_dir / file.filename)

        with open(source, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info("[STEP 1/5] Ingesting Video & Extracting Audio...")
        video_path, audio_path = await run_in_threadpool(process_video_input, source)

        import asyncio
        logger.info("[STEP 2/5 & 3/5] (PARALLEL) Creating base video with branding & Transcribing Audio...")
        
        # We can run video processing and transcription simultaneously to save massive latency!
        denoised_task = run_in_threadpool(apply_ffmpeg_processing, video_path, True)
        whisper_task = run_in_threadpool(transcribe_audio, audio_path, app.state.whisper_model)
        
        denoised_video_path, transcript_segments = await asyncio.gather(denoised_task, whisper_task)

        if not transcript_segments:
            raise HTTPException(status_code=500, detail="No transcript generated.")

        logger.info("[STEP 4/5] Analyzing Transcript & Generating Article...")
        ai_analysis = await analyze_transcript(transcript_segments)

        from src.article_generator import generate_article_from_json
        output_dir = ROOT_DIR / "data" / "output"
        article_path = output_dir / f"{Path(video_path).stem}_article.md"
        await generate_article_from_json(ai_analysis, str(article_path))

        logger.info("[STEP 5/5] Cutting Reels and Highlights...")
        reels_data = ai_analysis.get('reels', [])
        hl_data    = ai_analysis.get('highlight_segments', [])

        saved_reels = []
        if reels_data:
            saved_reels = await run_in_threadpool(cut_and_save_reels, denoised_video_path, reels_data)

        hl_result = {"mp4": "", "mp3": ""}
        if hl_data:
            hl_result = await run_in_threadpool(create_highlights_video, denoised_video_path, hl_data)

        # Merge AI metadata (title, caption, reason) with file paths for each reel
        enriched_reels = []
        for i, paths in enumerate(saved_reels):
            meta = reels_data[i] if i < len(reels_data) else {}
            enriched_reels.append({
                "title":      meta.get("title", f"Reel {i+1}"),
                "caption":    meta.get("caption", ""),
                "reason":     meta.get("reason", ""),
                "start_time": meta.get("start_time", 0),
                "end_time":   meta.get("end_time", 0),
                "mp4":        paths.get("mp4", ""),
                "mp3":        paths.get("mp3", ""),
            })

        # Merge AI metadata for highlights (now just start and end times)
        enriched_highlights = []
        for i, hl in enumerate(hl_data):
            enriched_highlights.append({
                "start_time": hl.get("start_time", 0),
                "end_time":   hl.get("end_time", 0),
            })

        local_results = {
            "status":         "success",
            "main_title":     ai_analysis.get("main_title", ""),
            "summary":        ai_analysis.get("summary", ""),
            "article_path":   str(article_path),
            "denoised_video": denoised_video_path,
            "denoised_audio": audio_path,
            "highlights": {
                "title":    ai_analysis.get("highlight_title", ""),
                "caption":  ai_analysis.get("highlight_caption", ""),
                "reason":   ai_analysis.get("highlight_reason", ""),
                "mp4":      hl_result.get("mp4", ""),
                "mp3":      hl_result.get("mp3", ""),
                "segments": enriched_highlights,
            },
            "reels": enriched_reels,
        }

        # --- Upload to Cloudinary & clean up local files ---
        folder = build_folder(email, file.filename, timestamp)
        logger.info(f"[STEP +] Uploading outputs to Cloudinary folder: {folder}")
        cdn_results = await run_in_threadpool(upload_pipeline_results, local_results, folder)
        await run_in_threadpool(delete_local_files, local_results, source)
        logger.info("Short Form Pipeline + Cloudinary upload complete!")

        return {"folder": folder, **cdn_results}
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


# ── AWS Lambda entry point ───────────────────────────────────────
from mangum import Mangum
lambda_handler = Mangum(app, lifespan="off")
