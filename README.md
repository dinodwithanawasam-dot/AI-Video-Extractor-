# 🎬 Autonomous Video Extraction & Summarization AI

**Developed by**: Dinod Imanjith | Associate AI Engineer

An autonomous AI agent designed to process long-form interview videos and automatically generate text summaries, highlight compilations, and highly engaging short-form reels (TikTok/Shorts format) using Semantic AI Analysis.

## ✨ Features
- **FastAPI High-Performance Backend**: Fully asynchronous API with zero-latency Whisper model pre-loading for rapid inference.
- **URL & Local File Support**: Directly download from YouTube or process local MP4 files.
- **Accurate Transcription**: Powered by OpenAI Whisper for precise timestamped text extraction.
- **LLM-Driven Semantic Algorithm**: Uses **Google Gemini** (via LangChain) to semantically analyze the transcript and find the most engaging 20-30 second moments.
- **Automated Video Editing**: Automatically cuts and merges the selected timestamps into final MP4 deliverables.

## 🚀 End-to-End Setup & Run Guide

Follow these exact steps to set up and run the project locally.

### 1. Prerequisites
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system PATH.

### 2. Clone and Install Dependencies
Open your terminal, navigate to the project directory, and run the following commands:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# (On Windows)
.venv\Scripts\activate
# (On Mac/Linux, use: source .venv/bin/activate)

# Install all required packages
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory of the project and add your Google Gemini API Key:
```env
GEMINI_API_KEY="your-gemini-api-key-here"
```

*(Optional)* You can tweak the Gemini model name (e.g., `gemini-1.5-flash`), reel duration, and download resolutions inside the `config/params.yaml` file.

### 4. Starting the Server
The core application runs as a high-performance **FastAPI** server. Start the server using Uvicorn:

```bash
uvicorn api:app --reload
```

*Note: During startup, the FastAPI lifespan event will automatically load the OpenAI Whisper model into memory. This might take a few seconds initially, but ensures zero-latency transcriptions for all subsequent requests!*

### 5. Testing the Video Pipeline
Once the server is running, you can easily test the end-to-end pipeline using the built-in Swagger UI:

1. Open your browser and go to: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
2. Click on the `POST /process` endpoint to expand it.
3. Click the **"Try it out"** button.
4. In the Request body, enter a YouTube URL or local file path:
   ```json
   {
     "url": "https://www.youtube.com/watch?v=YOUR_VIDEO_LINK"
   }
   ```
5. Click **"Execute"**. 
6. The server will run the ingestion, transcription, Gemini analysis, and video editing concurrently. Once finished, you will receive a JSON response containing the AI summary and the file paths to your generated highlight MP4s and Reels!

## 🧠 How the Algorithmic Logic Works
The system avoids traditional audio-peak detection and instead uses **Semantic Analysis**. The Whisper transcript is fed into the Google Gemini LLM with a strict system prompt. The AI reads the context and selects segments that are:
1. Emotionally engaging or highly informative.
2. Strictly between 20 and 30 seconds.
3. Logically complete (no cutting mid-sentence).
