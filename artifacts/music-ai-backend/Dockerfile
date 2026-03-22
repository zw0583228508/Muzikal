FROM python:3.11-slim

# System dependencies required for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    libsox-fmt-all \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create storage directories
RUN mkdir -p /tmp/musicai_stems /tmp/musicai_exports /tmp/musicai_renders /tmp/muzikal_cache /app/storage

# Non-root user for security
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app /tmp/musicai_stems \
    /tmp/musicai_exports /tmp/musicai_renders /tmp/muzikal_cache /app/storage
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/python-api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
