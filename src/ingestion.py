import os
import sys
from pathlib import Path
import yt_dlp
from moviepy import VideoFileClip

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import CONFIG, PATHS_CONFIG, VIDEO_CONFIG
from log import get_logger

logger = get_logger(__name__)

INPUT_DIR = ROOT_DIR / PATHS_CONFIG.get("input_dir", "data/input")
TEMP_DIR = ROOT_DIR / PATHS_CONFIG.get("temp_dir", "data/temp")
RESOLUTION = VIDEO_CONFIG.get("download_resolution", "720p")
AUDIO_FORMAT = VIDEO_CONFIG.get("audio_extract_format", "mp3")

def _try_download(url: str, ydl_opts: dict) -> str:
    """Helper: attempt download with given opts, return file path on success."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        if not file_path.endswith('.mp4'):
            file_path = file_path.rsplit('.', 1)[0] + '.mp4'
        return file_path

def download_youtube_video(url: str) -> str:
    """
    Downloads a YouTube video and returns the saved file path.
    Tries multiple player clients to bypass 403 Forbidden without needing a JS runtime.
    """
    logger.info(f"Starting download for URL: {url}")
    
    base_opts = {
        'outtmpl': str(INPUT_DIR / '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        'retries': 5,
        'fragment_retries': 5,
    }

    # List of strategies to attempt in order
    strategies = [
        {
            'name': 'iOS client (no JS needed)',
            'extra': {
                'format': f'bestvideo[height<={RESOLUTION[:-1]}]+bestaudio/best',
                'extractor_args': {'youtube': {'player_client': ['ios']}},
            }
        },
        {
            'name': 'mweb client (no JS needed)',
            'extra': {
                'format': f'bestvideo[height<={RESOLUTION[:-1]}]+bestaudio/best',
                'extractor_args': {'youtube': {'player_client': ['mweb']}},
            }
        },
        {
            'name': 'Android client (no JS needed)',
            'extra': {
                'format': f'bestvideo[height<={RESOLUTION[:-1]}]+bestaudio/best',
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }
        },
    ]

    for strategy in strategies:
        logger.info(f"Trying download strategy: {strategy['name']}...")
        opts = {**base_opts, **strategy['extra']}
        try:
            file_path = _try_download(url, opts)
            logger.info(f"Download successful with strategy '{strategy['name']}': {file_path}")
            return file_path
        except Exception as e:
            logger.warning(f"Strategy '{strategy['name']}' failed: {e}. Trying next...")

    logger.error("All download strategies failed.")
    raise RuntimeError("Could not download the YouTube video. Please try uploading the MP4 file directly.")

def extract_audio(video_path: str) -> str:
    """
    Extracts audio from a video file, applies background noise suppression,
    and saves the cleaned audio to the temp directory.
    Returns the path to the extracted (denoised) audio file.
    """
    import subprocess
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error(f"Video file not found at: {video_path}")
        raise FileNotFoundError(f"Video file not found at: {video_path}")
        
    audio_path = TEMP_DIR / f"{video_path.stem}.{AUDIO_FORMAT}"
    
    logger.info(f"Extracting audio with noise suppression to: {audio_path}")
    
    try:
        # Use FFmpeg directly with afftdn (Audio Fast Fourier Transform DeNoise) filter
        # This removes background hiss/hum while preserving speech clearly
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-af", "afftdn=nf=-25",   # nf=-25: noise floor threshold in dBFS
            "-ar", "16000",           # 16kHz sample rate (optimal for Whisper)
            "-ac", "1",               # Mono channel (reduces file size, fine for speech)
            "-vn",                    # No video stream
            str(audio_path)
        ]
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.warning(f"FFmpeg noise suppression failed, falling back to MoviePy: {result.stderr}")
            # Fallback: extract audio without noise suppression using MoviePy
            video = VideoFileClip(str(video_path))
            if video.audio is None:
                raise ValueError("The provided video does not contain an audio track.")
            video.audio.write_audiofile(str(audio_path), logger=None)
            video.close()
        else:
            logger.info("Background noise suppression applied successfully.")
            
        logger.info(f"Successfully extracted audio to: {audio_path}")
        return str(audio_path)
    except Exception as e:
        logger.error(f"Error extracting audio: {str(e)}")
        raise e


def process_video_input(source: str) -> tuple[str, str]:
    """
    Handles both YouTube URLs and local MP4 file paths.
    Returns a tuple of (video_file_path, extracted_audio_path).
    """
    if source.startswith("http://") or source.startswith("https://") or "youtube.com" in source or "youtu.be" in source:
        logger.info("Detected YouTube URL. Initiating download...")
        video_path = download_youtube_video(source)
    else:
        logger.info("Detected local file path.")
        video_path = source
        
    audio_path = extract_audio(video_path)
    
    return str(video_path), str(audio_path)

