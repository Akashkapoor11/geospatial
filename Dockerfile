FROM python:3.12-slim-bookworm

LABEL maintainer="Geospatial API" \
      description="Geospatial File Measurement API" \
      version="1.0.0"

# Prevent .pyc files and enable unbuffered stdout/stderr for clean Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install GDAL and related geospatial system libraries
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gdal-bin \
       libgdal-dev \
       libgeos-dev \
       libproj-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source so Docker layer cache
# is invalidated only when requirements.txt changes, not every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create the storage directory and a non-root user for security
RUN mkdir -p /app/storage/uploads \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Run Alembic migrations then start Uvicorn
# Using bash -lc ensures PATH is set correctly for the non-root user
CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
