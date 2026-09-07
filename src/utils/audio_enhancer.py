import subprocess
import shutil
from pathlib import Path
import numpy as np
import scipy.io.wavfile as wav
from log import get_logger

logger = get_logger(__name__)


def clean_audio_with_noisereduce(
    input_wav_path: str,
    output_wav_path: str,
    prop_decrease: float = 0.90,
    time_mask_smooth_ms: int = 64,
    freq_mask_smooth_hz: int = 400,
) -> str:
    """
    Cleans an uncompressed WAV file using adaptive non-stationary noise reduction.
    Removes crows, birds, traffic, and environmental noise smoothly without fluttering artifacts.
    """
    import noisereduce as nr

    logger.info(f"[AUDIO ENHANCE] Processing {Path(input_wav_path).name} with noisereduce...")
    sr, audio = wav.read(input_wav_path)

    # Handle stereo vs mono
    if audio.ndim == 2:
        # Process each channel
        cleaned_channels = [
            nr.reduce_noise(
                y=audio[:, ch],
                sr=sr,
                stationary=False,
                prop_decrease=prop_decrease,
                time_mask_smooth_ms=time_mask_smooth_ms,
                freq_mask_smooth_hz=freq_mask_smooth_hz,
            )
            for ch in range(audio.shape[1])
        ]
        cleaned_audio = np.column_stack(cleaned_channels)
    else:
        cleaned_audio = nr.reduce_noise(
            y=audio,
            sr=sr,
            stationary=False,
            prop_decrease=prop_decrease,
            time_mask_smooth_ms=time_mask_smooth_ms,
            freq_mask_smooth_hz=freq_mask_smooth_hz,
        )

    wav.write(output_wav_path, sr, cleaned_audio.astype(np.int16))
    logger.info(f"[AUDIO ENHANCE] Saved clean audio to {output_wav_path}")
    return output_wav_path


def denoise_video_audio(video_path: str) -> tuple[str, str]:
    """
    Takes an input video, extracts its audio, applies adaptive noisereduce,
    and replaces the video's audio track in-place with the pristine studio-clean audio.

    Returns:
      (video_path, clean_audio_mp3_path)
    """
    video_path_obj = Path(video_path)
    parent_dir = video_path_obj.parent
    stem = video_path_obj.stem

    temp_raw_wav = str(parent_dir / f"{stem}_temp_raw.wav")
    temp_clean_wav = str(parent_dir / f"{stem}_temp_clean.wav")
    clean_audio_mp3 = str(parent_dir / f"{stem}_clean.mp3")
    temp_muxed_video = str(parent_dir / f"{stem}_temp_muxed.mp4")

    try:
        # Step 1: Extract 24kHz audio for high-res fast processing
        logger.info(f"[AUDIO ENHANCE] Extracting audio track from {video_path_obj.name}...")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path_obj),
            "-vn",
            "-ar", "24000",
            "-ac", "2",
            temp_raw_wav
        ], check=True, capture_output=True)

        # Step 2: Denoise via noisereduce
        clean_audio_with_noisereduce(temp_raw_wav, temp_clean_wav)

        # Step 3: Export clean MP3 for Whisper / API
        subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_clean_wav,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ac", "2",
            clean_audio_mp3
        ], check=True, capture_output=True)

        # Step 4: Mux clean audio back into source video (stream copy video frames = lossless & fast)
        logger.info(f"[AUDIO ENHANCE] Remuxing cleaned audio into {video_path_obj.name}...")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path_obj),
            "-i", temp_clean_wav,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ac", "2",
            temp_muxed_video
        ], check=True, capture_output=True)

        # Replace original video file with the clean muxed video
        shutil.move(temp_muxed_video, str(video_path_obj))
        logger.info(f"[AUDIO ENHANCE] Successfully upgraded {video_path_obj.name} with clean audio!")

    except Exception as e:
        logger.error(f"[AUDIO ENHANCE] Failed to denoise video audio: {e}. Keeping original audio.")
        # Fallback: extract audio as-is
        if not Path(clean_audio_mp3).exists():
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(video_path_obj),
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ac", "2",
                clean_audio_mp3
            ], capture_output=True)
    finally:
        # Cleanup temporary wav files
        for p in (temp_raw_wav, temp_clean_wav, temp_muxed_video):
            Path(p).unlink(missing_ok=True)

    return str(video_path_obj), clean_audio_mp3
