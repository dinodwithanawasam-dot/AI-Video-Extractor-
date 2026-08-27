# 🎬 Autonomous Video Extraction & Summarization AI

**Developed by**: Dinod Imanjith | Associate AI Engineer

An autonomous AI agent designed to process long-form interview videos and automatically generate text summaries, highlight compilations, and highly engaging short-form reels (TikTok/Shorts format) using Semantic AI Analysis.

## ✨ Features
- **URL & Local File Support**: Directly download from YouTube or upload local MP4 files via the UI.
- **Accurate Transcription**: Powered by OpenAI Whisper for precise timestamped text extraction.
- **LLM-Driven Semantic Algorithm**: Uses GPT-4o-mini (via LangChain) to semantically analyze the transcript and find the most engaging 20-30 second moments.
- **Automated Video Editing**: Automatically cuts and merges the selected timestamps into final MP4 deliverables.
- **Beautiful Web UI**: Fully interactive frontend built with Streamlit.

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system PATH.

### 2. Installation
Clone the repository, create a virtual environment, and install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory and add your OpenAI API Key:
```env
OPENAI_API_KEY="sk-your-openai-api-key-here"
```
*(Optional)* You can tweak model parameters, reel duration, and download resolutions in `config/params.yaml`.

### 4. Running the App
Launch the interactive Streamlit Web UI (Executable Demo):
```bash
streamlit run app.py
```

Or run the pipeline headlessly via CLI:
```bash
python main.py "https://www.youtube.com/watch?v=YOUR_LINK"
```

## 🧠 How the Algorithmic Logic Works
The system avoids traditional audio-peak detection and instead uses **Semantic Analysis**. The Whisper transcript is fed into an LLM with a strict system prompt. The AI reads the context and selects segments that are:
1. Emotionally engaging or highly informative.
2. Strictly between 20 and 30 seconds.
3. Logically complete (no cutting mid-sentence).
