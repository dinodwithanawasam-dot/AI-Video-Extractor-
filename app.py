import streamlit as st
import os
import sys
import asyncio
from pathlib import Path

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from src.ingestion import process_video_input
from src.transcription import transcribe_audio
from src.ai_logic import analyze_transcript
from src.video_editor import cut_and_save_reels, create_highlights_video

st.set_page_config(page_title="AI Video Extraction", page_icon="🎬", layout="wide")

st.title("🎬 Autonomous Video Extraction & Summarization AI")
st.markdown("Enter a YouTube URL or upload an MP4 file to automatically generate a summary, highlights, and reels.")

# Detect if running on Streamlit Cloud (no local ffmpeg write access)
IS_CLOUD = os.environ.get("HOME", "") == "/home/appuser"

if IS_CLOUD:
    st.info("☁️ **Running on Cloud:** YouTube direct download is not supported in cloud deployments due to IP restrictions. Please upload an MP4 file directly.", icon="ℹ️")
    source_type = "Upload Local File"
else:
    source_type = st.radio("Select Video Source:", ("YouTube URL", "Upload Local File"))

video_source = None
if source_type == "YouTube URL":
    video_source = st.text_input("YouTube URL (e.g., https://www.youtube.com/watch?v=...)")
else:
    uploaded_file = st.file_uploader("Upload MP4 File", type=["mp4"])
    if uploaded_file is not None:
        # Save uploaded file to input dir
        input_dir = ROOT_DIR / "data" / "input"
        os.makedirs(input_dir, exist_ok=True)
        video_source = str(input_dir / uploaded_file.name)
        with open(video_source, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"File uploaded successfully: {uploaded_file.name}")

if st.button("Start Processing"):
    if not video_source:
        st.error("Please provide a valid video source first.")
    elif not os.getenv("GEMINI_API_KEY") and not st.secrets.get("GEMINI_API_KEY", ""):
        st.error("GEMINI_API_KEY is not set. Please make sure your .env file has the API key.")
    else:
        try:
            with st.status("Pipeline Execution in Progress...", expanded=True) as status:
                st.write("⏳ Step 1/4: Ingesting Video & Extracting Audio...")
                video_path, audio_path = process_video_input(video_source)
                st.write(f"✔️ Video loaded: `{Path(video_path).name}`")
                
                st.write("⏳ Step 2/4: Transcribing Audio with Whisper (This may take a while)...")
                transcript_segments = transcribe_audio(audio_path)
                st.write("✔️ Transcription complete!")
                
                st.write("⏳ Step 3/4: Analyzing Transcript with LLM...")
                ai_analysis = asyncio.run(analyze_transcript(transcript_segments))
                st.write("✔️ AI Analysis complete!")
                
                st.write("⏳ Step 4/4: Cutting Reels and Highlights...")
                reels_data = ai_analysis.get('reels', [])
                hl_data = ai_analysis.get('highlight_segments', [])
                
                saved_reels = []
                if reels_data:
                    saved_reels = cut_and_save_reels(video_path, reels_data)
                    
                hl_path = ""
                if hl_data:
                    hl_path = create_highlights_video(video_path, hl_data)
                
                status.update(label="Processing Complete! 🎉", state="complete", expanded=False)
                
            # Display Results in the UI
            st.divider()
            
            # Main title from AI
            main_title = ai_analysis.get('main_title', 'Video Summary')
            st.header(f"🎬 {main_title}")
            
            st.subheader("📋 Summary")
            st.info(ai_analysis.get('summary', 'No summary generated.'))
            
            st.divider()
            st.header("🔥 Generated Highlights")
            if hl_path and os.path.exists(hl_path):
                st.video(hl_path)
                # MP3 download for highlights
                hl_mp3 = hl_path.replace('.mp4', '.mp3')
                col1, col2 = st.columns(2)
                with col1:
                    with open(hl_path, 'rb') as f:
                        st.download_button("⬇️ Download Highlights (MP4)", f, file_name=Path(hl_path).name, mime="video/mp4")
                with col2:
                    if os.path.exists(hl_mp3):
                        with open(hl_mp3, 'rb') as f:
                            st.download_button("🎵 Download Audio (MP3)", f, file_name=Path(hl_mp3).name, mime="audio/mpeg")
            else:
                st.warning("No highlights were generated.")
                
            st.divider()
            st.header("📱 Generated Reels")
            if saved_reels:
                cols = st.columns(len(saved_reels))
                for idx, (col, reel) in enumerate(zip(cols, saved_reels)):
                    reel_mp4 = reel.get("mp4", "")
                    reel_mp3 = reel.get("mp3", "")
                    reel_meta = reels_data[idx] if idx < len(reels_data) else {}
                    
                    if reel_mp4 and os.path.exists(reel_mp4):
                        with col:
                            # Title
                            reel_title = reel_meta.get('title', f'Reel {idx+1}')
                            st.subheader(f"🎞️ {reel_title}")
                            st.video(reel_mp4)
                            
                            # Caption
                            caption = reel_meta.get('caption', '')
                            if caption:
                                st.caption(caption)
                            
                            # Why engaging
                            reason = reel_meta.get('reason', '')
                            if reason:
                                with st.expander("💡 Why this was selected"):
                                    st.write(reason)
                            
                            # Download buttons
                            dl_col1, dl_col2 = st.columns(2)
                            with dl_col1:
                                with open(reel_mp4, 'rb') as f:
                                    st.download_button(
                                        "⬇️ MP4", f,
                                        file_name=Path(reel_mp4).name,
                                        mime="video/mp4",
                                        key=f"mp4_{idx}"
                                    )
                            with dl_col2:
                                if reel_mp3 and os.path.exists(reel_mp3):
                                    with open(reel_mp3, 'rb') as f:
                                        st.download_button(
                                            "🎵 MP3", f,
                                            file_name=Path(reel_mp3).name,
                                            mime="audio/mpeg",
                                            key=f"mp3_{idx}"
                                        )
            else:
                st.warning("No reels were generated.")
                
        except Exception as e:
            st.error(f"An error occurred during processing: {e}")

