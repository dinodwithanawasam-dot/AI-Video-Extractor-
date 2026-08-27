import os
import sys
import json
from pathlib import Path
import whisper

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import WHISPER_CONFIG, PATHS_CONFIG
from log import get_logger

logger = get_logger(__name__)

TEMP_DIR = ROOT_DIR / PATHS_CONFIG.get("temp_dir", "data/temp")

def load_whisper_model():
    """Loads the Whisper model into memory."""
    model_size = WHISPER_CONFIG.get("model_size", "base")
    device = WHISPER_CONFIG.get("device", "cpu")
    logger.info(f"Loading Whisper model '{model_size}' on '{device}'...")
    return whisper.load_model(model_size, device=device)

def transcribe_audio(audio_path: str, model=None) -> list[dict]:
    """
    Transcribes an audio file using OpenAI Whisper.
    Returns a list of segments with start time, end time, and text.
    Also saves the transcript to a JSON file so it doesn't need to be re-run if testing.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        logger.error(f"Audio file not found: {audio_path}")
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    # Create a filename for the cached transcript
    transcript_file = TEMP_DIR / f"{audio_path.stem}_transcript.json"
    
    # Cache mechanism: If already transcribed, load from JSON
    if transcript_file.exists():
        logger.info(f"Found existing transcript at {transcript_file}. Loading from cache...")
        with open(transcript_file, "r", encoding="utf-8") as f:
            return json.load(f)

    if model is None:
        try:
            model = load_whisper_model()
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
        
    logger.info(f"Starting transcription for {audio_path.name}...")
    try:
        language = WHISPER_CONFIG.get("language")
        transcribe_kwargs = {}
        if language:
            transcribe_kwargs["language"] = language
            
        result = model.transcribe(str(audio_path), **transcribe_kwargs)
        segments = result.get("segments", [])
        
        # Save the result to a JSON file
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
            
        logger.info(f"Transcription complete. Found {len(segments)} segments. Saved to {transcript_file}")
        
        return segments
    
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        raise

