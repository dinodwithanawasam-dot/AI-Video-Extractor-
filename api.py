import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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

class ProcessRequest(BaseModel):
    url: str

@app.post("/process")
async def process_video(request: ProcessRequest):
    source = request.url
    if not source:
        raise HTTPException(status_code=400, detail="URL must be provided.")
        
    logger.info(f"Received request to process: {source}")
    
    try:
        # Step 1: Ingestion (blocking, run in threadpool)
        logger.info("[STEP 1/4] Ingesting Video & Extracting Audio...")
        video_path, audio_path = await run_in_threadpool(process_video_input, source)
        
        # Step 2: Transcription (blocking, run in threadpool)
        logger.info("[STEP 2/4] Transcribing Audio with Whisper...")
        # Pass the pre-loaded model from app state
        transcript_segments = await run_in_threadpool(
            transcribe_audio, 
            audio_path, 
            app.state.whisper_model
        )
        if not transcript_segments:
            raise HTTPException(status_code=500, detail="No transcript generated.")
            
        # Step 3: AI Analysis (already async, await natively)
        logger.info("[STEP 3/4] Analyzing Transcript with LLM...")
        ai_analysis = await analyze_transcript(transcript_segments)
        
        # Step 4: Video Editing (blocking, run in threadpool)
        logger.info("[STEP 4/4] Cutting Reels and Highlights...")
        reels_data = ai_analysis.get('reels', [])
        hl_data = ai_analysis.get('highlight_segments', [])
        
        saved_reels = []
        if reels_data:
            saved_reels = await run_in_threadpool(cut_and_save_reels, video_path, reels_data)
            
        hl_path = ""
        if hl_data:
            hl_path = await run_in_threadpool(create_highlights_video, video_path, hl_data)
            
        logger.info("Pipeline Completed Successfully!")
        
        return {
            "status": "success",
            "summary": ai_analysis.get('summary', ''),
            "highlights_video": hl_path,
            "reels": saved_reels
        }
        
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")
