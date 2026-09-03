import subprocess
import json
from pathlib import Path
from log import get_logger

logger = get_logger(__name__)

def get_video_properties(video_path: str) -> dict:
    """Uses ffprobe to get the width, height, fps, and audio sample rate of a video."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        
        width = int(stream.get("width", 1920))
        height = int(stream.get("height", 1080))
        
        # Calculate fps from rational string like "30000/1001"
        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)
            
        return {"width": width, "height": height, "fps": fps}
    except Exception as e:
        logger.warning(f"Failed to probe video properties for {video_path}: {e}")
        return {"width": 1920, "height": 1080, "fps": 30.0}

def build_concat_command(
    main_video_path: str,
    intro_path: str,
    outro_path: str,
    out_path: str,
    logo_path: str = None,
    start_time: float = None,
    duration: float = None
) -> list:
    """
    Builds the FFmpeg command to scale intro and outro to match the main video,
    apply the watermark (optional), cut the main video (optional), and concatenate them all.
    """
    props = get_video_properties(main_video_path)
    w, h, fps = props["width"], props["height"], props["fps"]
    
    # Scale filter for intro/outro to fit within main video dimensions, padding with black if aspect ratio differs.
    # setsar=1 ensures square pixels.
    scale_pad_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", intro_path
    ]
    
    if start_time is not None and duration is not None:
        cmd.extend(["-ss", str(start_time), "-t", str(duration)])
        
    cmd.extend([
        "-i", main_video_path,
        "-i", outro_path
    ])
    
    if logo_path:
        cmd.extend(["-i", logo_path])
        
    # Build filter_complex
    # [0:v] Intro, [1:v] Main, [2:v] Outro, [3:v] Logo (if exists)
    fc = f"[0:v]{scale_pad_filter}[v0];"  # Format intro
    
    if logo_path:
        # Scale logo to 11% of main height, overlay on main video
        fc += f"[3:v]format=yuva420p,colorchannelmixer=aa=0.7,scale=-1:ih*0.055[logo];[1:v][logo]overlay=W-w-20:20,setsar=1,fps={fps}[v1];"
    else:
        fc += f"[1:v]setsar=1,fps={fps}[v1];" # Just format main video
        
    fc += f"[2:v]{scale_pad_filter}[v2];" # Format outro
    
    # Concatenate: v0,a0 -> v1,a1 -> v2,a2
    fc += "[v0][0:a][v1][1:a][v2][2:a]concat=n=3:v=1:a=1[vout][aout]"
    
    cmd.extend([
        "-filter_complex", fc,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        out_path
    ])
    
    return cmd

def build_audio_concat_command(
    main_audio_path: str,
    intro_audio_path: str,
    outro_audio_path: str,
    out_path: str
) -> list:
    """Builds command to concatenate 3 audio files."""
    cmd = [
        "ffmpeg", "-y",
        "-i", intro_audio_path,
        "-i", main_audio_path,
        "-i", outro_audio_path,
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[aout]",
        "-map", "[aout]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        out_path
    ]
    return cmd
