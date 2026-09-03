"""
worker.py — Background AI Video Processing Worker

Listens to the Redis 'video_processing_queue', downloads each video from
Google Drive, runs it through the full AI pipeline (short-form), uploads
results to Cloudinary, and stores job metadata for the Flipline dashboard.

One video is processed at a time to prevent server overload. When a job
is done the worker immediately pulls the next ticket from the queue.
"""

import os
import sys
import json
import subprocess
import asyncio
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import redis

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

from log import get_logger
from src.ingestion import process_video_input
from src.transcription import load_whisper_model, transcribe_audio
from src.ai_logic import analyze_transcript
from src.video_editor import cut_and_save_reels, create_highlights_video
from src.cloudinary_storage import build_folder, upload_pipeline_results, delete_local_files
from src.utils.drive_utils import get_drive_service, download_file
from src.utils.db_utils import save_video_record

logger = get_logger("AI_Worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "video_processing_queue"


def apply_ffmpeg_processing(video_path: str, with_logo: bool = True) -> str:
    """Applies noise cancellation, watermark logo, and branding to a video."""
    from src.utils.ffmpeg_utils import build_concat_command

    output_dir = ROOT_DIR / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    stem    = Path(video_path).stem
    out_path = output_dir / f"{stem}_branded.mp4"
    logo_dir = ROOT_DIR / "logo"
    use_logo = None

    if with_logo:
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            found = list(logo_dir.glob(ext))
            if found:
                use_logo = str(found[0])
                break

    media_dir = ROOT_DIR / "media" / "video"
    intro_path = media_dir / "start.mp4"
    outro_path = media_dir / "end.mp4"

    if intro_path.exists() and outro_path.exists():
        cmd = build_concat_command(
            main_video_path=video_path,
            intro_path=str(intro_path),
            outro_path=str(outro_path),
            out_path=str(out_path),
            logo_path=use_logo
        )
    else:
        # Fallback: no intro/outro
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


async def process_job(job: dict, whisper_model) -> dict:
    """
    Runs the full short-form AI pipeline for a single video job.
    Returns a result dict with Cloudinary URLs.
    """
    file_id   = job.get("file_id")
    file_name = job.get("file_name", "video.mp4")
    email     = job.get("email", "auto@flipline.internal")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info(f"[JOB START] {file_name} ({file_id})")

    # ── Step 1: Download from Google Drive ────────────────────────────────
    logger.info("[STEP 1/6] Downloading from Google Drive...")
    input_dir = ROOT_DIR / "data" / "input"
    source = str(input_dir / file_name)

    service = get_drive_service()
    if not service:
        raise RuntimeError("Could not authenticate with Google Drive.")

    ok = download_file(service, file_id, source)
    if not ok:
        raise RuntimeError(f"Failed to download file_id={file_id} from Google Drive.")

    loop = asyncio.get_event_loop()

    # ── Step 2: Ingest (noise-suppressed audio extraction) ────────────────
    logger.info("[STEP 2/6] Ingesting video & extracting audio...")
    video_path, audio_path = await loop.run_in_executor(
        None, process_video_input, source)

    # ── Step 3 & 4: FFmpeg branding + Whisper (in parallel) ──────────────
    logger.info("[STEP 3+4/6] (PARALLEL) Branding video & transcribing audio...")
    denoised_video_path, transcript_segments = await asyncio.gather(
        loop.run_in_executor(None, apply_ffmpeg_processing, video_path, True),
        loop.run_in_executor(None, transcribe_audio, audio_path, whisper_model),
    )

    if not transcript_segments:
        raise RuntimeError("Whisper returned no transcript segments.")

    # ── Step 5: GPT-4o-mini analysis ─────────────────────────────────────
    logger.info("[STEP 5/6] Analyzing transcript with AI...")
    ai_analysis = await analyze_transcript(transcript_segments)

    # Generate article
    from src.article_generator import generate_article_from_json
    output_dir  = ROOT_DIR / "data" / "output"
    article_path = output_dir / f"{Path(video_path).stem}_article.md"
    await generate_article_from_json(ai_analysis, str(article_path))

    # ── Step 6: Cut reels & highlights ───────────────────────────────────
    logger.info("[STEP 6/6] Cutting reels and highlights...")
    reels_data = ai_analysis.get('reels', [])
    hl_data    = ai_analysis.get('highlight_segments', [])

    saved_reels = []
    if reels_data:
        saved_reels = await loop.run_in_executor(
            None, cut_and_save_reels, denoised_video_path, reels_data)

    hl_result = {"mp4": "", "mp3": ""}
    if hl_data:
        hl_result = await loop.run_in_executor(
            None, create_highlights_video, denoised_video_path, hl_data)

    # Enrich reels with AI metadata
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
            "segments": [{"start_time": h.get("start_time", 0), "end_time": h.get("end_time", 0)} for h in hl_data],
        },
        "reels": enriched_reels,
    }

    # ── Upload to Cloudinary & clean up ──────────────────────────────────
    folder = build_folder(email, file_name, timestamp)
    logger.info(f"[UPLOAD] Uploading to Cloudinary folder: {folder}")
    cdn_results = await loop.run_in_executor(
        None, upload_pipeline_results, local_results, folder)
    await loop.run_in_executor(
        None, delete_local_files, local_results, source)

    logger.info(f"[JOB DONE] {file_name} → folder: {folder}")
    return {"folder": folder, **cdn_results}


def run_worker():
    """Main blocking loop: pull one job at a time from Redis and process it."""
    # ── Connect to Redis ──────────────────────────────────────────────────
    logger.info("Connecting to Redis...")
    try:
        redis_client = redis.Redis.from_url(
            REDIS_URL, 
            decode_responses=True,
            socket_timeout=40,       # Socket timeout must be higher than brpop timeout
            socket_keepalive=True
        )
        redis_client.ping()
        logger.info(f"Connected to Redis at {REDIS_URL}")
    except Exception as e:
        logger.error(f"Cannot connect to Redis: {e}")
        sys.exit(1)

    # ── Pre-load Whisper so we don't reload it for every job ─────────────
    logger.info("Pre-loading Whisper model...")
    whisper_model = load_whisper_model()
    logger.info("Whisper model ready. Worker is listening for jobs...")

    # ── Main event loop ───────────────────────────────────────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            # brpop blocks until a job appears (timeout=30s to stay alive)
            result = redis_client.brpop(QUEUE_NAME, timeout=30)
            if result is None:
                # Timeout, no jobs — just continue listening
                continue

            _, raw_job = result
            job = json.loads(raw_job)
            logger.info(f"Picked up job: {job.get('file_name')}")

            try:
                cdn_results = loop.run_until_complete(process_job(job, whisper_model))
                logger.info(f"Job complete. Cloudinary folder: {cdn_results.get('folder')}")
                
                # Phase 3: save cdn_results to DynamoDB here
                # Prepare record schema matching implementation plan
                db_record = {
                    "video_id": job.get("file_id"), # Primary Key
                    "created_at": datetime.utcnow().isoformat() + "Z", # Timestamp for sorting
                    "status": "success",
                    "main_title": cdn_results.get("main_title", ""),
                    "summary": cdn_results.get("summary", ""),
                    "article_path": cdn_results.get("article_path", ""),
                    "denoised_video": cdn_results.get("denoised_video", ""),
                    "denoised_audio": cdn_results.get("denoised_audio", ""),
                    "highlights": cdn_results.get("highlights", {}),
                    "reels": cdn_results.get("reels", [])
                }
                save_video_record(db_record)
                
            except Exception as e:
                logger.error(f"Job failed for {job.get('file_name')}: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except redis.exceptions.TimeoutError:
            # Socket timed out before brpop returned (harmless, just loop again)
            continue
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis connection dropped: {e}. Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected worker error: {e}", exc_info=True)
            time.sleep(5)  # Brief pause before retrying on unexpected errors


if __name__ == "__main__":
    run_worker()
