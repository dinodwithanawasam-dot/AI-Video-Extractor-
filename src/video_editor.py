import os
import sys
from pathlib import Path
from moviepy import VideoFileClip, concatenate_videoclips

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import PATHS_CONFIG
from log import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = ROOT_DIR / PATHS_CONFIG.get("output_dir", "data/output")

def cut_and_save_reels(video_path: str, reels_data: list[dict]) -> list[dict]:
    """
    Cuts the main video into short reels based on provided start and end times from the LLM.
    Returns a list of dicts with 'mp4' and 'mp3' paths for each saved reel.
    """
    logger.info(f"Extracting {len(reels_data)} reels from {Path(video_path).name}...")
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
        
    try:
        main_video = VideoFileClip(str(video_path))
    except Exception as e:
        logger.error(f"Failed to open video {video_path}: {e}")
        raise
        
    video_duration = main_video.duration
    main_video.close()
    
    saved_reels = []  # Track successfully saved reel paths
    
    for i, reel in enumerate(reels_data):
        start = reel.get("start_time", 0)
        end = reel.get("end_time", 0)
        
        # Validate timestamps
        if end <= start or start < 0 or end > video_duration:
            logger.warning(f"Skipping Reel {i+1} due to invalid timestamps: {start} - {end}")
            continue
            
        logger.info(f"Processing Reel {i+1} from {start}s to {end}s...")
        
        # Open a fresh VideoFileClip for each reel to avoid FFmpeg handle issues
        try:
            video = VideoFileClip(str(video_path))
            clip = video.subclipped(start, end)
            stem = Path(video_path).stem
            
            # Export MP4 (video)
            mp4_path = OUTPUT_DIR / f"{stem}_reel_{i+1}.mp4"
            clip.write_videofile(str(mp4_path), codec="libx264", audio_codec="aac", logger=None)
            logger.info(f"Saved Reel {i+1} MP4 to {mp4_path}")
            
            # Export MP3 (audio only)
            mp3_path = OUTPUT_DIR / f"{stem}_reel_{i+1}.mp3"
            if clip.audio is not None:
                clip.audio.write_audiofile(str(mp3_path), logger=None)
                logger.info(f"Saved Reel {i+1} MP3 to {mp3_path}")
            else:
                mp3_path = ""
                
            saved_reels.append({"mp4": str(mp4_path), "mp3": str(mp3_path)})
        except Exception as e:
            logger.error(f"Error saving Reel {i+1}: {e}")
        finally:
            try:
                clip.close()
                video.close()
            except Exception:
                pass
    
    return saved_reels

def create_highlights_video(video_path: str, highlights_data: list[dict]) -> str:
    """
    Cuts highlight segments and merges them into a single summary video.
    """
    logger.info(f"Creating highlights video from {len(highlights_data)} segments...")
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
        
    try:
        main_video = VideoFileClip(str(video_path))
    except Exception as e:
        logger.error(f"Failed to open video {video_path}: {e}")
        raise
        
    clips = []
    for i, hl in enumerate(highlights_data):
        start = hl.get("start_time", 0)
        end = hl.get("end_time", 0)
        
        if end <= start or start < 0 or end > main_video.duration:
            logger.warning(f"Invalid highlight timestamps: {start}-{end}")
            continue
            
        clip = main_video.subclipped(start, end)
        clips.append(clip)
        
    if not clips:
        logger.warning("No valid highlight clips found.")
        main_video.close()
        return ""
        
    logger.info("Concatenating highlight clips...")
    try:
        final_clip = concatenate_videoclips(clips)
        stem = Path(video_path).stem
        
        # Export MP4 (video)
        mp4_path = OUTPUT_DIR / f"{stem}_highlights.mp4"
        final_clip.write_videofile(str(mp4_path), codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"Saved Highlights MP4 to {mp4_path}")
        
        # Export MP3 (audio only)
        mp3_path = OUTPUT_DIR / f"{stem}_highlights.mp3"
        if final_clip.audio is not None:
            final_clip.audio.write_audiofile(str(mp3_path), logger=None)
            logger.info(f"Saved Highlights MP3 to {mp3_path}")
        
        out_path = mp4_path
    except Exception as e:
        logger.error(f"Error saving Highlights video: {e}")
        out_path = ""
    finally:
        for c in clips:
            c.close()
        if 'final_clip' in locals():
            final_clip.close()
        main_video.close()
    
    return str(out_path)

if __name__ == "__main__":
    pass
