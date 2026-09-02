import os
import re
import sys
import asyncio
import cloudinary
import cloudinary.uploader
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from log import get_logger
logger = get_logger(__name__)

# Configure Cloudinary from environment variables
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure     = True
)

# Mapping file extension → Cloudinary resource_type
_RESOURCE_TYPE = {
    ".mp4": "video",
    ".mp3": "video",   # Cloudinary treats audio as resource_type="video"
    ".md":  "raw",
    ".txt": "raw",
}


def _sanitize(name: str) -> str:
    """Remove characters that are invalid in Cloudinary public_id."""
    return re.sub(r"[^\w.\-]", "_", name)


def build_folder(email: str, video_filename: str, timestamp: str) -> str:
    """
    Builds the Cloudinary folder path:
      <email>/<video_name>_<timestamp>
    e.g. user@gmail.com/my_video_20240901_103000
    """
    safe_email    = _sanitize(email)
    safe_filename = _sanitize(Path(video_filename).stem)
    return f"{safe_email}/{safe_filename}_{timestamp}"


def _upload_one(local_path: str, folder: str, public_id: str) -> str:
    """
    Uploads a single file to Cloudinary (blocking — runs in threadpool).
    Returns the secure CDN URL, or empty string on failure.
    """
    if not local_path or not Path(local_path).exists():
        return ""

    ext           = Path(local_path).suffix.lower()
    resource_type = _RESOURCE_TYPE.get(ext, "raw")
    safe_public_id = Path(public_id).stem  # Cloudinary manages extensions

    try:
        logger.info(f"Uploading {Path(local_path).name} → {folder}/{safe_public_id}")
        result = cloudinary.uploader.upload(
            local_path,
            resource_type = resource_type,
            folder        = folder,
            public_id     = safe_public_id,
            overwrite     = True,
        )
        url = result.get("secure_url", "")
        logger.info(f"✓ Uploaded: {Path(local_path).name}")
        return url
    except Exception as e:
        logger.error(f"Cloudinary upload failed for {local_path}: {e}")
        return ""


def upload_pipeline_results(results: dict, folder: str) -> dict:
    """
    Collects ALL file paths from the pipeline results dict, uploads them
    ALL IN PARALLEL using a ThreadPoolExecutor, then returns a new dict
    with CDN URLs replacing every local path.
    """
    # ---- Gather all upload tasks: (key_path, local_path, public_id) ----
    # key_path is a tuple used to set the value back into the result dict
    tasks = []  # List of (tag, local_path, public_id)

    for key in ("denoised_video", "denoised_audio", "article_path"):
        lp = results.get(key, "")
        if lp:
            tasks.append((key, lp, Path(lp).name))

    hl = results.get("highlights", {})
    if isinstance(hl, dict):
        if hl.get("mp4"):
            tasks.append(("highlights_mp4", hl["mp4"], "highlights.mp4"))
        if hl.get("mp3"):
            tasks.append(("highlights_mp3", hl["mp3"], "highlights.mp3"))

    for i, reel in enumerate(results.get("reels", [])):
        if reel.get("mp4"):
            tasks.append((f"reel_{i}_mp4", reel["mp4"], f"reel_{i+1}.mp4"))
        if reel.get("mp3"):
            tasks.append((f"reel_{i}_mp3", reel["mp3"], f"reel_{i+1}.mp3"))

    if not tasks:
        logger.warning("No files to upload to Cloudinary.")
        return results

    logger.info(f"Starting parallel upload of {len(tasks)} files to Cloudinary...")

    # ---- Upload ALL files in parallel ----
    url_map = {}  # tag → CDN URL
    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as executor:
        future_to_tag = {
            executor.submit(_upload_one, lp, folder, pid): tag
            for tag, lp, pid in tasks
        }
        for future in as_completed(future_to_tag):
            tag = future_to_tag[future]
            try:
                url_map[tag] = future.result()
            except Exception as e:
                logger.error(f"Upload task failed for {tag}: {e}")
                url_map[tag] = ""

    logger.info(f"All {len(tasks)} uploads done!")

    # ---- Build the final response dict with CDN URLs ----
    cdn = dict(results)

    for key in ("denoised_video", "denoised_audio", "article_path"):
        if key in url_map:
            cdn[key] = url_map[key]

    if isinstance(hl, dict):
        cdn["highlights"] = {
            **hl,
            "mp4": url_map.get("highlights_mp4", hl.get("mp4", "")),
            "mp3": url_map.get("highlights_mp3", hl.get("mp3", "")),
        }

    cdn_reels = []
    for i, reel in enumerate(results.get("reels", [])):
        cdn_reels.append({
            **reel,
            "mp4": url_map.get(f"reel_{i}_mp4", reel.get("mp4", "")),
            "mp3": url_map.get(f"reel_{i}_mp3", reel.get("mp3", "")),
        })
    cdn["reels"] = cdn_reels

    return cdn


def delete_local_files(results: dict, input_path: str = "", source_video: str = "") -> None:
    """
    Deletes ALL local files after a successful Cloudinary upload:
      - Output files (video, audio, article, reels, highlights)
      - The original uploaded input file
      - The entire data/temp folder contents (transcripts, ai_analysis JSON, etc.)
    """
    paths_to_delete = []

    # Output files
    for key in ("denoised_video", "denoised_audio", "article_path"):
        p = results.get(key, "")
        if p:
            paths_to_delete.append(p)

    hl = results.get("highlights", {})
    if isinstance(hl, dict):
        paths_to_delete += [hl.get("mp4", ""), hl.get("mp3", "")]

    for reel in results.get("reels", []):
        paths_to_delete += [reel.get("mp4", ""), reel.get("mp3", "")]

    # Input file (the original uploaded video)
    if input_path:
        paths_to_delete.append(input_path)

    # Delete all collected output files
    for p in paths_to_delete:
        try:
            if p and Path(p).exists():
                Path(p).unlink()
                logger.info(f"Deleted: {p}")
        except Exception as e:
            logger.warning(f"Could not delete {p}: {e}")

    # Wipe entire data/temp folder (transcripts, whisper cache, ai_analysis.json, etc.)
    temp_dir = ROOT_DIR / "data" / "temp"
    if temp_dir.exists():
        for f in temp_dir.iterdir():
            try:
                if f.is_file():
                    f.unlink()
                    logger.info(f"Deleted temp file: {f.name}")
            except Exception as e:
                logger.warning(f"Could not delete temp file {f}: {e}")

    logger.info("Local cleanup complete.")



