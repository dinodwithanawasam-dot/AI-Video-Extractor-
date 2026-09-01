import os
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import PATHS_CONFIG
from log import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = ROOT_DIR / PATHS_CONFIG.get("output_dir", "data/output")
LOGO_PATH  = ROOT_DIR / "logo" / "branding.jpeg"


def _ffmpeg_cut_with_logo(video_path: str, start: float, end: float, out_mp4: str, out_mp3: str) -> dict:
    """
    Uses FFmpeg to cut a segment, overlay the branding logo, and export MP4 + MP3.
    Much faster than MoviePy — FFmpeg handles the encode natively without Python overhead.
    """
    duration = end - start

    if LOGO_PATH.exists():
        filter_complex = (
            "[1:v]scale=-1:ih*0.1[logo];"
            "[0:v][logo]overlay=W-w-20:20[vout]"
        )
        video_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(duration),
            "-i",  video_path,
            "-i",  str(LOGO_PATH),
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            out_mp4
        ]
    else:
        logger.warning("Logo not found — cutting reel without watermark.")
        video_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(duration),
            "-i",  video_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            out_mp4
        ]

    audio_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration),
        "-i",  video_path,
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
        out_mp3
    ]

    try:
        subprocess.run(video_cmd, capture_output=True, check=True)
        subprocess.run(audio_cmd, capture_output=True, check=True)
        return {"mp4": out_mp4, "mp3": out_mp3}
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e.stderr.decode()}")
        return {"mp4": "", "mp3": ""}


def _get_video_duration(video_path: str) -> float:
    """Uses ffprobe to get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def cut_and_save_reels(video_path: str, reels_data: list[dict]) -> list[dict]:
    """
    Cuts reels using FFmpeg (fast) and processes them in parallel using threads.
    Returns a list of dicts with 'mp4' and 'mp3' paths for each reel.
    """
    logger.info(f"Extracting {len(reels_data)} reels from {Path(video_path).name}...")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    video_duration = _get_video_duration(video_path)
    stem = Path(video_path).stem

    # Build validated task list
    tasks = []
    for i, reel in enumerate(reels_data):
        start = reel.get("start_time", 0)
        end   = reel.get("end_time", 0)
        if end <= start or start < 0 or (video_duration > 0 and end > video_duration):
            logger.warning(f"Skipping Reel {i+1} — invalid timestamps: {start}s - {end}s")
            continue
        out_mp4 = str(OUTPUT_DIR / f"{stem}_reel_{i+1}.mp4")
        out_mp3 = str(OUTPUT_DIR / f"{stem}_reel_{i+1}.mp3")
        tasks.append((i + 1, start, end, out_mp4, out_mp3))

    if not tasks:
        return []

    # Process all reels in parallel using threads (FFmpeg is CPU-bound, not GIL-bound)
    saved_reels_map = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 4)) as executor:
        futures = {
            executor.submit(_ffmpeg_cut_with_logo, video_path, start, end, mp4, mp3): idx
            for idx, start, end, mp4, mp3 in tasks
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                saved_reels_map[idx] = result
                logger.info(f"Reel {idx} done → {Path(result.get('mp4', 'FAILED')).name}")
            except Exception as e:
                logger.error(f"Reel {idx} failed: {e}")
                saved_reels_map[idx] = {"mp4": "", "mp3": ""}

    # Return in original index order
    return [saved_reels_map[t[0]] for t in tasks if t[0] in saved_reels_map]


def create_highlights_video(video_path: str, highlights_data: list[dict]) -> dict:
    """
    Cuts highlight segments and concatenates them into a single video using FFmpeg.
    Returns a dict with 'mp4' and 'mp3' paths.
    """
    logger.info(f"Creating highlights video from {len(highlights_data)} segments...")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(video_path).stem
    video_duration = _get_video_duration(video_path)

    # Step 1: Cut each segment to a temp file (stream copy = no re-encode)
    temp_files = []
    for i, hl in enumerate(highlights_data):
        start = hl.get("start_time", 0)
        end   = hl.get("end_time", 0)
        if end <= start or start < 0 or (video_duration > 0 and end > video_duration):
            logger.warning(f"Invalid highlight timestamps: {start}-{end}, skipping.")
            continue
        temp_path = str(OUTPUT_DIR / f"{stem}_hl_temp_{i}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(end - start),
            "-i", video_path,
            "-c", "copy",   # stream copy — very fast
            temp_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            temp_files.append(temp_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cut highlight segment {i}: {e.stderr.decode()}")

    if not temp_files:
        logger.warning("No valid highlight segments cut.")
        return {"mp4": "", "mp3": ""}

    # Step 2: Write FFmpeg concat list
    concat_list = OUTPUT_DIR / f"{stem}_hl_concat.txt"
    with open(concat_list, "w") as f:
        for tf in temp_files:
            f.write(f"file '{tf}'\n")

    mp4_path = str(OUTPUT_DIR / f"{stem}_highlights.mp4")
    mp3_path = str(OUTPUT_DIR / f"{stem}_highlights.mp3")

    # Step 3: Concatenate + overlay logo in one pass
    if LOGO_PATH.exists():
        concat_raw = str(OUTPUT_DIR / f"{stem}_hl_raw.mp4")
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy", concat_raw
            ], capture_output=True, check=True)
            subprocess.run([
                "ffmpeg", "-y",
                "-i", concat_raw, "-i", str(LOGO_PATH),
                "-filter_complex", "[1:v]scale=-1:ih*0.1[logo];[0:v][logo]overlay=W-w-20:20[vout]",
                "-map", "[vout]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                mp4_path
            ], capture_output=True, check=True)
            Path(concat_raw).unlink(missing_ok=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Highlights creation failed: {e.stderr.decode()}")
            return {"mp4": "", "mp3": ""}
    else:
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list), "-c", "copy", mp4_path
            ], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Highlights concatenation failed: {e.stderr.decode()}")
            return {"mp4": "", "mp3": ""}

    # Step 4: Extract audio
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", mp4_path,
            "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
            mp3_path
        ], capture_output=True, check=True)
        logger.info(f"Saved Highlights MP3 to {mp3_path}")
    except Exception as e:
        logger.warning(f"Highlights audio extraction failed: {e}")
        mp3_path = ""

    # Cleanup temp files
    for tf in temp_files:
        Path(tf).unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    logger.info(f"Saved Highlights MP4 to {mp4_path}")
    return {"mp4": mp4_path, "mp3": mp3_path}


if __name__ == "__main__":
    pass


