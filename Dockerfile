# @decision DEC-DOCKER-002
# @title python:3.12-slim over alpine (musl libc breaks OpenCV/librosa)
# @status accepted
# @rationale Ada depends on opencv-python-headless and librosa for multimodal
#     analysis. Both link against glibc C extensions that fail to build under
#     musl libc (Alpine). Debian-based slim image adds ~40MB but guarantees
#     compatibility with prebuilt wheels on PyPI.

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package definition first so pip can resolve dependencies.
# We also need the ada package itself for hatchling to build it.
COPY pyproject.toml ./
COPY ada/ ./ada/

# Install the package and all runtime dependencies into a prefix
# so we can copy just the installed artifacts to the runtime stage.
RUN pip install --no-cache-dir --prefix=/install .

# --- Stage 2: Runtime ---
# @decision DEC-DOCKER-001
# @title Single-process uvicorn (SQLite write-contention constraint)
# @status accepted
# @rationale SQLite allows only one writer at a time. Running multiple uvicorn
#     workers would cause SQLITE_BUSY errors under concurrent write load.
#     Single-process is sufficient for the target deployment scale
#     (self-hosted, small clinic). Revisit if write throughput becomes a
#     bottleneck — migration to PostgreSQL would be the next step, not more
#     workers.
FROM python:3.12-slim AS runtime

# Runtime system libraries:
#   libgomp1   — OpenMP, required by librosa's numpy-based routines
#   libsndfile1 — audio file I/O used by librosa
#   libglib2.0-0 — GLib, indirect dep of opencv-python-headless
#   curl       — used by Docker HEALTHCHECK
# Note: opencv-python-headless does NOT require libgl1 (unlike full opencv-python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libsndfile1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY --from=builder /app/ada ./ada

# Copy TOML config layers
COPY config/ ./config/

# Copy entrypoint script
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create data directory for SQLite persistence.
# In production this will be mounted as a named volume.
RUN mkdir -p /app/data

# ADA_ENV controls which config/production.toml layer is loaded.
# ADA_LOGGING__FORMAT=json emits structured JSON logs for log aggregators.
ENV ADA_ENV=production
ENV ADA_LOGGING__FORMAT=json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
