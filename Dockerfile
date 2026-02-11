# Multi-stage Dockerfile for Ultimate CA Manager
# Optimized for production with security and minimal size

# Stage 1: Builder - Install dependencies and build environment
FROM python:3.13-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements first for better caching
COPY backend/requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.13-slim-bookworm

LABEL maintainer="NeySlim <https://github.com/NeySlim>" \
      description="Ultimate CA Manager - Certificate Authority Management System" \
      org.opencontainers.image.source="https://github.com/NeySlim/ultimate-ca-manager"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    openssl \
    softhsm2 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -r -u 1000 -s /bin/false -d /app ucm && \
    usermod -aG softhsm ucm

# Prepare SoftHSM token directory
RUN mkdir -p /var/lib/softhsm/tokens && \
    chown root:softhsm /var/lib/softhsm/tokens && \
    chmod 1770 /var/lib/softhsm/tokens

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Ensure /app is owned by ucm user
RUN chown ucm:ucm /app

# Copy application files
# Copy application files with proper ownership
COPY --chown=ucm:ucm VERSION /app/VERSION
COPY --chown=ucm:ucm backend/ /app/backend/
COPY --chown=ucm:ucm frontend/ /app/frontend/
COPY --chown=ucm:ucm wsgi.py /app/wsgi.py
COPY --chown=ucm:ucm .env.docker.example /app/.env.example

# Create data directory at unified path (same as DEB/RPM installs)
RUN mkdir -p /opt/ucm/data/{ca,certs,private,crl,scep,backups,sessions,logs,temp} && \
    chown -R ucm:ucm /opt/ucm

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UCM_DOCKER=1 \
    DATA_DIR=/opt/ucm/data

# Expose HTTPS port
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f -k https://127.0.0.1:8443/health || exit 1

# Copy Gunicorn configuration and entrypoint before switching user
COPY --chown=ucm:ucm gunicorn.conf.py /app/gunicorn.conf.py
COPY --chown=ucm:ucm docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER ucm

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command - Use Gunicorn for production
CMD ["sh", "-c", "UCM_BASE_PATH=/app gunicorn --config /app/gunicorn.conf.py wsgi:app"]
