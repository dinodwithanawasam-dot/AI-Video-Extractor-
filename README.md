# 🎬 Autonomous Video Extraction & Summarization AI

**Developed by**: Dinod Imanjith | Associate AI Engineer

An autonomous AI agent designed to process long-form interview videos and automatically generate text summaries, highlight compilations, and highly engaging short-form reels (TikTok/Shorts format) using Semantic AI Analysis.

## ✨ Features
- **FastAPI High-Performance Backend**: Fully asynchronous API with zero-latency Whisper model pre-loading for rapid inference.
- **Lightning Fast Video Editing (FFmpeg)**: Replaced traditional Python libraries with raw FFmpeg commands running in a highly parallelized `ThreadPoolExecutor` for 6x faster video rendering.
- **Cloudinary CDN Integration**: All final outputs (Reels, Highlights, Audios, and Articles) are automatically uploaded to user-specific folders in Cloudinary.
- **Accurate Transcription**: Powered by OpenAI Whisper for precise timestamped text extraction.
- **LLM-Driven Semantic Algorithm**: Uses **OpenAI GPT-4o-mini** to semantically analyze the transcript and extract the most engaging 20-30 second viral moments.
- **Zero Local Footprint**: The server auto-cleans all input files, temporary files, and processed outputs immediately after a successful Cloudinary upload, saving disk space.

---

## 🚀 End-to-End Setup & Run Guide

Follow these exact steps to set up and run the project locally.

### 1. Prerequisites
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system PATH (Crucial for video processing).
- A Cloudinary account for CDN storage.
- An OpenAI API Key.

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
Create a `.env` file in the root directory of the project and add your API Keys:
```env
OPENAI_API_KEY="sk-your-openai-api-key-here"

CLOUDINARY_CLOUD_NAME="your_cloud_name"
CLOUDINARY_API_KEY="your_api_key"
CLOUDINARY_API_SECRET="your_api_secret"
```

### 4. Starting the Server
The core application runs as a high-performance **FastAPI** server. Start the server using Uvicorn:

```bash
uvicorn api:app --reload
```

*Note: During startup, the FastAPI lifespan event will automatically load the OpenAI Whisper model into memory. This ensures zero-latency transcriptions for all subsequent requests!*

### 5. Testing the Video Pipeline via Postman
The API accepts `multipart/form-data` to handle file uploads alongside user metadata.

**Endpoint:** `POST http://127.0.0.1:8000/process/short`

**Body (form-data):**
- `email`: (Text) e.g., `kasun@gmail.com`
- `file`: (File) Select your `.mp4` video file to upload.

Once the process is complete, you will receive a JSON response containing the AI-generated titles, summaries, and **direct Cloudinary CDN URLs** for all your generated media!

---

## 🧠 How the Algorithmic Logic Works
The system avoids traditional audio-peak detection and instead uses **Semantic Analysis**. The Whisper transcript is fed into the OpenAI LLM with a strict system prompt. The AI reads the context and selects segments that are:
1. Emotionally engaging or highly informative.
2. Strictly between 20 and 30 seconds.
3. Logically complete (no cutting mid-sentence).

Once the AI selects the timestamps, the backend spawns parallel FFmpeg threads to cut the video, apply denoising algorithms, overlay watermarks, and extract MP3s simultaneously.
