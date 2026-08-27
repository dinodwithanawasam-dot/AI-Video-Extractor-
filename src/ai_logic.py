import os
import sys
import json
from pathlib import Path
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import CONFIG, LLM_CONFIG, GEMINI_API_KEY
from log import get_logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

logger = get_logger(__name__)

# Define Pydantic Models for structured JSON output from LLM
class ReelSegment(BaseModel):
    start_time: float = Field(description="Exact start time of the clip in seconds from the transcript")
    end_time: float = Field(description="Exact end time of the clip in seconds. MUST be at least 20 seconds greater than start_time.")
    title: str = Field(description="A short, catchy, viral-style title for this clip (max 10 words). Like a YouTube Short title.")
    caption: str = Field(description="A social media caption for this clip (1-2 sentences + 3-5 relevant hashtags).")
    reason: str = Field(description="Why this segment is highly engaging")

class HighlightsSummary(BaseModel):
    main_title: str = Field(description="A compelling main title for the entire video summary (max 12 words).")
    summary: str = Field(description="A concise, readable text summary of the entire video")
    highlight_segments: list[ReelSegment] = Field(description="Key moments that represent the core message of the video")
    reels: list[ReelSegment] = Field(description="Exactly 2 or 3 engaging segments. Each segment MUST be between 20 and 30 seconds long (end_time - start_time >= 20 AND end_time - start_time <= 30).")

def get_llm():
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in the environment variables.")
        raise ValueError("Please set GEMINI_API_KEY in your .env file")
        
    return ChatGoogleGenerativeAI(
        model=LLM_CONFIG.get("model_name", "gemini-1.5-flash"),
        temperature=LLM_CONFIG.get("temperature", 0.7),
        google_api_key=GEMINI_API_KEY
    )

async def analyze_transcript(transcript_segments: list[dict]) -> dict:
    """
    Analyzes the transcript using an LLM to generate summaries and identify reel timestamps.
    """
    logger.info("Starting AI analysis of transcript...")
    
    formatted_transcript = ""
    for seg in transcript_segments:
        start = round(seg.get("start", 0), 1)
        end = round(seg.get("end", 0), 1)
        text = seg.get("text", "").strip()
        formatted_transcript += f"[{start} - {end}] {text}\n"
        
    llm = get_llm()
    parser = JsonOutputParser(pydantic_object=HighlightsSummary)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert video editor and social media content creator. Analyze the transcript and return:
1. A compelling main_title for the overall video.
2. A concise text summary of the entire video.
3. 2-3 key highlight segments.
4. Exactly 2 or 3 short-form reels for TikTok/Shorts.

For EACH reel and highlight segment, you MUST also generate:
- title: A short, catchy, viral-style title (max 10 words). Make it hook the viewer instantly.
- caption: A social media caption (1-2 engaging sentences + 3-5 relevant hashtags).

REEL CONTENT RULES (WHAT TO SELECT):
- Pick the most engaging, emotional, or highly informative parts of the video.
- Look for clear advice, strong opinions, or impactful moments that hook a viewer's attention.
- The selected speech must make sense on its own (don't pick a segment that requires too much outside context).

REEL DURATION RULES (CRITICAL):
- Every reel MUST be exactly between 20 and 30 seconds: (end_time - start_time) >= 20 AND <= 30.
- Before finalizing, calculate the duration of each reel. If it is wrong, FIX IT:
  * If duration < 20s → extend end_time by adding more consecutive segments until duration >= 20s.
  * If duration > 30s → reduce end_time to be exactly (start_time + 28) seconds.
- After fixing, verify: 20 <= (end_time - start_time) <= 30. If not, fix again.
- NEVER submit a reel shorter than 20 seconds or longer than 30 seconds.
- Reels must NOT overlap each other.
- Only use timestamps that exist in the provided transcript.

EXAMPLE OF SELF-CORRECTION:
  Draft reel: start=166.4, end=184.8 → duration=18.4s ← TOO SHORT, must fix!
  Fix: extend end to next segment boundary → end=186.5 → duration=20.1s ✅ Submit this.

ALWAYS return exactly 2 or 3 reels. Never return an empty list.

{format_instructions}
"""),
        ("user", "Transcript with timestamps (seconds):\n\n{transcript}")
    ])
    
    chain = prompt | llm | parser
    
    logger.info("Sending prompt to LLM (this might take a few moments)...")
    try:
        result = await chain.ainvoke({
            "transcript": formatted_transcript,
            "format_instructions": parser.get_format_instructions()
        })
        
        # Post-processing: enforce 20-30s duration hard limits in code
        raw_reels = result.get("reels", [])
        logger.info(f"AI returned {len(raw_reels)} raw reel(s): " +
                    str([f"{r.get('start_time')}s-{r.get('end_time')}s ({round(r.get('end_time',0)-r.get('start_time',0),1)}s)" for r in raw_reels]))
        
        MIN_DURATION = 20.0
        MAX_DURATION = 30.0
        DROP_BELOW   = 10.0  
        
        def enforce_duration(r):
            """Clamp reel end_time to guarantee 20-30s duration."""
            start = r.get("start_time", 0)
            r["end_time"] = max(start + 20.0, min(r.get("end_time", 0), start + 30.0))
            return r

        # Apply: drop reels < 10s, clamp rest to 20-30s range
        fixed_reels = [enforce_duration(r) for r in raw_reels
                       if (r.get("end_time", 0) - r.get("start_time", 0)) >= 10.0]

        result["reels"] = fixed_reels
        logger.info(f"After enforcement: {len(fixed_reels)} reel(s): ")
        
        # Save analysis to temp dir
        analysis_path = ROOT_DIR / "data" / "temp" / "ai_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)
            
        logger.info(f"AI analysis complete. {len(fixed_reels)} valid reels saved to {analysis_path}")
        return result
        
    except Exception as e:
        logger.error(f"Error during LLM analysis: {e}")
        raise
