# Multi-stage Dockerfile for Ultimate CA Manager
# Optimized for production with security and minimal size
# Paths aligned with DEB/RPM packages: /opt/ucm/{backend,frontend,data}

# Stage 1: Builder - Install dependencies and build environment
FROM python:3.13-slim-bookworm AS builder

# Install build dependencies (fallback for packages without prebuilt wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment (same path as DEB/RPM)
RUN python -m venv /opt/ucm/venv
ENV PATH="/opt/ucm/venv/bin:$PATH"

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
    libkrb5-3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -r -u 1000 -s /bin/false -d /opt/ucm ucm && \
    usermod -aG softhsm ucm

# Prepare SoftHSM token directory
RUN mkdir -p /var/lib/softhsm/tokens && \
    chown root:softhsm /var/lib/softhsm/tokens && \
    chmod 1770 /var/lib/softhsm/tokens

# Copy virtual environment from builder
COPY --from=builder /opt/ucm/venv /opt/ucm/venv

# Set working directory (same as DEB/RPM)
WORKDIR /opt/ucm

# Copy application files with proper ownership (same layout as packages)
COPY --chown=ucm:ucm VERSION /opt/ucm/VERSION
COPY --chown=ucm:ucm backend/ /opt/ucm/backend/
COPY --chown=ucm:ucm frontend/ /opt/ucm/frontend/
COPY --chown=ucm:ucm wsgi.py /opt/ucm/wsgi.py
COPY --chown=ucm:ucm .env.docker.example /opt/ucm/.env.example

# Create data + log directories
RUN mkdir -p /opt/ucm/data/{ca,certs,private,crl,scep,backups,sessions,logs,temp} && \
    mkdir -p /var/log/ucm && \
    mkdir -p /etc/ucm && \
    chown -R ucm:ucm /opt/ucm /var/log/ucm /etc/ucm

# Set environment variables
ENV PATH="/opt/ucm/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UCM_DOCKER=1 \
    UCM_BASE_PATH=/opt/ucm \
    DATA_DIR=/opt/ucm/data

# Expose HTTPS port
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f -k https://127.0.0.1:8443/health || exit 1

# Copy entrypoint before switching user
COPY --chown=ucm:ucm docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER ucm

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command - Gunicorn from /opt/ucm/backend (same as packages)
CMD ["sh", "-c", "cd /opt/ucm/backend && gunicorn -c gunicorn_config.py wsgi:app"]
