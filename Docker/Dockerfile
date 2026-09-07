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

# Install CPU-only torch first (saves 2GB+ of unnecessary NVIDIA CUDA GPU downloads)
RUN pip install --no-cache-dir --timeout=120 --retries=5 --prefix=/install \
    torch==2.4.0+cpu torchaudio==2.4.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Make sure pip in the builder sees the pre-installed CPU torch in /install
ENV PYTHONPATH="/install/lib/python3.11/site-packages:${PYTHONPATH}"
ENV PATH="/install/bin:${PATH}"

# Copy and install Python requirements (with CPU index fallback to prevent NVIDIA GPU packages)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=120 --retries=5 --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ========================================================
# Stage 2: Pre-download Whisper model during build
# (So the container never needs internet at runtime)
# Reuses the packages installed in Stage 1 — NO extra downloads!
# ========================================================
FROM python:3.11-slim AS model-downloader

# Copy packages from builder stage so whisper is already available
COPY --from=builder /install /usr/local

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

# Ensure Python logs are flushed immediately to CloudWatch without buffering
ENV PYTHONUNBUFFERED=1

# Run the AI Video Processing Worker (Fargate worker entry point)
CMD ["python", "-u", "src/worker.py"]
