# ========================================================
# Stage 1: Builder — Install Python dependencies
# ========================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies needed for some Python packages (e.g. openai-whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ========================================================
# Stage 2: Pre-download Whisper model during build
# (So the container never needs internet at runtime)
# ========================================================
FROM python:3.11-slim AS model-downloader

WORKDIR /models

# Need whisper installed to download
# Use CPU-only torch to avoid downloading the 2GB+ GPU version unnecessarily
# --timeout=120 and --retries=5 to handle slow network connections during build
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
    torch==2.4.0+cpu torchaudio==2.4.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --timeout=120 --retries=5 openai-whisper

# Download the Whisper 'base' model weights — cached into /root/.cache/whisper
# This runs ONCE at docker build time, not at every container start!
RUN python -c "import whisper; whisper.load_model('base')"

# ========================================================
# Stage 3: Runtime — Final lean image
# ========================================================
FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg (the core engine of this project) and other system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy the pre-downloaded Whisper model weights from model-downloader stage
# Whisper caches models in /root/.cache/whisper by default
COPY --from=model-downloader /root/.cache/whisper /root/.cache/whisper

# Copy the entire project source code
COPY . .

# Create necessary data directories so they exist inside the container
RUN mkdir -p data/input data/output data/temp logs

# Expose the FastAPI port
EXPOSE 8000

# Healthcheck — Docker will ping this to know if the service is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the FastAPI server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
