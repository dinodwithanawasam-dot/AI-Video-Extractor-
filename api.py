import os
import sys
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
import shutil
from fastapi.concurrency import run_in_threadpool

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from log import get_logger
from src.ingestion import process_video_input
from src.transcription import load_whisper_model, transcribe_audio
from src.ai_logic import analyze_transcript
from src.video_editor import cut_and_save_reels, create_highlights_video

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

def apply_ffmpeg_processing(video_path: str, with_logo: bool = False) -> str:
    import subprocess
    output_dir = ROOT_DIR / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    stem = Path(video_path).stem
    suffix = "_longform" if with_logo else "_denoised"
    out_path = output_dir / f"{stem}{suffix}.mp4"
    
    logo_path = ROOT_DIR / "logo" / "branding.jpeg"
    
    if with_logo and logo_path.exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", str(logo_path),
            "-filter_complex",
            # Scale logo to 10% of video height, place at top-right with 20px padding
            "[1:v]scale=-1:ih*0.1[logo];[0:v][logo]overlay=W-w-20:20[vout]",
            "-map", "[vout]",
            "-map", "0:a",
            "-af", "afftdn=nf=-25",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_path)
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "copy",
            "-af", "afftdn=nf=-25",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_path)
        ]
        
    subprocess.run(cmd, capture_output=True, check=True)
    return str(out_path)

@app.post("/process/long")
async def process_long(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
        
    logger.info(f"Received file upload for long form: {file.filename}")
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
        audio_cmd = [
            "ffmpeg", "-y",
            "-i", final_video,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            audio_path
        ]
        try:
            subprocess.run(audio_cmd, capture_output=True, check=True)
            logger.info(f"Audio extracted to: {audio_path}")
        except Exception as e:
            logger.warning(f"Audio extraction failed: {e}")
            audio_path = ""
        
        return {
            "status": "success",
            "video_path": final_video,
            "audio_path": audio_path
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

@app.post("/process/short")
async def process_short(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
        
    logger.info(f"Received file upload for short form: {file.filename}")
    try:
        # Save uploaded file locally
        input_dir = ROOT_DIR / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        source = str(input_dir / file.filename)
        
        with open(source, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logger.info("[STEP 1/5] Ingesting Video & Extracting Audio...")
        video_path, audio_path = await run_in_threadpool(process_video_input, source)
        
        logger.info("[STEP 2/5] Creating denoised base video...")
        denoised_video_path = await run_in_threadpool(apply_ffmpeg_processing, video_path, False)
        
        logger.info("[STEP 3/5] Transcribing Audio with Whisper...")
        transcript_segments = await run_in_threadpool(
            transcribe_audio, 
            audio_path, 
            app.state.whisper_model
        )
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
        hl_data = ai_analysis.get('highlight_segments', [])
        
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
        
        # Merge AI metadata for highlights
        enriched_highlights = []
        for i, hl in enumerate(hl_data):
            enriched_highlights.append({
                "title":      hl.get("title", f"Highlight {i+1}"),
                "caption":    hl.get("caption", ""),
                "reason":     hl.get("reason", ""),
                "start_time": hl.get("start_time", 0),
                "end_time":   hl.get("end_time", 0),
            })
            
        logger.info("Short Form Pipeline Completed Successfully!")
        
        return {
            "status":           "success",
            "main_title":       ai_analysis.get("main_title", ""),
            "summary":          ai_analysis.get("summary", ""),
            "article_path":     str(article_path),
            "denoised_video":   denoised_video_path,
            "denoised_audio":   audio_path,
            "highlights": {
                "mp4":      hl_result.get("mp4", ""),
                "mp3":      hl_result.get("mp3", ""),
                "segments": enriched_highlights,   # title, caption, reason per segment
            },
            "reels": enriched_reels,   # title, caption, reason, mp4, mp3 per reel
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")
