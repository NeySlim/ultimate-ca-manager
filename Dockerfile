# Multi-stage Dockerfile for Ultimate CA Manager
# Optimized for production with security and minimal size
# Paths aligned with DEB/RPM packages: /opt/ucm/{backend,frontend,data}
#
# --build-arg UCM_FIPS_BUILD=1 builds the -fips variant: OpenSSL FIPS provider
# plus crypto libraries compiled against the system libcrypto. Default 0 = standard.
ARG UCM_FIPS_BUILD=0
ARG FIPS_PROVIDER_VERSION=3.1.2
ARG FIPS_PROVIDER_SHA256=a0ce69b8b97ea6a35b96875235aa453b966ba3cba8af2de23657d8b6767d6539

# Stage 1: Builder - Install dependencies and build environment
FROM python:3.13-slim-trixie AS builder-0

# Install build dependencies (fallback for packages without prebuilt wheels)
# Note: pyjks is installed separately with --no-deps to skip `twofish`
# (sdist-only C ext, only used for BKS UBER format which UCM does not export).
# This means build-essential is no longer strictly required, but kept as a
# safety net for future deps that may need to compile.
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
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir --no-deps pyjks==20.0.0

# FIPS variant builder: same requirements, psycopg2-binary swapped for psycopg2,
# and every library that links OpenSSL or libxml2 compiled from source.
FROM python:3.13-slim-trixie AS builder-1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libffi-dev \
    libkrb5-dev \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libxmlsec1-dev \
    zlib1g-dev \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/ucm/venv
ENV PATH="/opt/ucm/venv/bin:$PATH"
COPY backend/requirements.txt /tmp/requirements.txt
RUN set -eu; \
    test "$(grep -c '^psycopg2-binary' /tmp/requirements.txt)" = 1; \
    sed 's/^psycopg2-binary/psycopg2/' /tmp/requirements.txt > /tmp/requirements-fips.txt; \
    ! grep -q 'psycopg2-binary' /tmp/requirements-fips.txt; \
    test "$(diff /tmp/requirements.txt /tmp/requirements-fips.txt | grep -c '^[<>]')" = 2
RUN --mount=type=cache,target=/root/.cargo/registry \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --no-binary cryptography,psycopg2,lxml,xmlsec \
        -r /tmp/requirements-fips.txt && \
    pip install --no-cache-dir --no-deps pyjks==20.0.0
# Fails the build if any of them still carries its own OpenSSL or libxml2
RUN set -eu; \
    pip check | grep -v '^pyjks [0-9.]* requires twofish, which is not installed\.$' | { ! grep .; }; \
    ! pip show psycopg2-binary >/dev/null 2>&1; \
    python -c "import ssl; from cryptography.hazmat.backends.openssl.backend import backend as b; \
assert b.openssl_version_text() == ssl.OPENSSL_VERSION, (b.openssl_version_text(), ssl.OPENSSL_VERSION)"; \
    site=$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'); \
    ldd "$site"/cryptography/hazmat/bindings/_rust.abi3.so | grep -q 'libcrypto\.so\.3 => /lib/'; \
    ldd "$site"/psycopg2/_psycopg*.so | grep -q 'libpq\.so\.5 => /lib/'; \
    ldd "$site"/xmlsec*.so | grep -q 'libxmlsec1-openssl\.so\.1 => /lib/'; \
    ldd "$site"/lxml/etree*.so | grep -q 'libxml2\.so\.2 => /lib/'; \
    test -z "$(find /opt/ucm/venv \( -name 'libssl*' -o -name 'libcrypto*' -o -name 'libxml2*' -o -name 'libpq*' \) -print)"

FROM builder-${UCM_FIPS_BUILD} AS builder

# FIPS provider: only fips.so is kept, the system libcrypto loads it
FROM python:3.13-slim-trixie AS fips-provider-1
ARG FIPS_PROVIDER_VERSION
ARG FIPS_PROVIDER_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential perl curl ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN set -eu; \
    curl -fsSLo openssl.tar.gz \
      "https://github.com/openssl/openssl/releases/download/openssl-${FIPS_PROVIDER_VERSION}/openssl-${FIPS_PROVIDER_VERSION}.tar.gz"; \
    echo "${FIPS_PROVIDER_SHA256}  openssl.tar.gz" | sha256sum -c -; \
    tar xzf openssl.tar.gz
# Build commands of the module's security policy: ./Configure enable-fips, make
RUN set -eu; cd "openssl-${FIPS_PROVIDER_VERSION}"; \
    ./Configure enable-fips; \
    make -j"$(nproc)"; \
    mkdir -p /out; cp providers/fips.so /out/fips.so; \
    openssl fipsinstall -module /out/fips.so -provider_name fips -out /dev/null

FROM scratch AS fips-provider-0
FROM fips-provider-${UCM_FIPS_BUILD} AS fips-provider

# Stage 2: Runtime - Minimal production image
FROM python:3.13-slim-trixie
ARG UCM_FIPS_BUILD
ARG TARGETARCH

LABEL maintainer="NeySlim <https://github.com/NeySlim>" \
      description="Ultimate CA Manager - Certificate Authority Management System" \
      org.opencontainers.image.source="https://github.com/NeySlim/ultimate-ca-manager" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    openssl \
    openssh-client \
    softhsm2 \
    libkrb5-3 \
    postgresql-client \
    $([ "$UCM_FIPS_BUILD" = 1 ] && echo libpq5 libxml2 libxslt1.1 libxmlsec1t64-openssl) \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -r -u 1000 -s /bin/false -d /opt/ucm ucm && \
    usermod -aG softhsm ucm

# FIPS variant: fips.so in the module directory of this platform's libcrypto,
# and /run/ucm where the entrypoint writes the module configuration at start
RUN --mount=type=bind,from=fips-provider,target=/tmp/fips-provider \
    if [ "$UCM_FIPS_BUILD" = 1 ]; then \
        set -eu; \
        arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
        case "$arch" in amd64) triplet=x86_64-linux-gnu ;; arm64) triplet=aarch64-linux-gnu ;; \
            *) echo "unsupported architecture for the FIPS variant: $arch"; exit 1 ;; esac; \
        moddir="$(openssl version -m | sed -E 's/^MODULESDIR: "(.*)"$/\1/')"; \
        test "$moddir" = "/usr/lib/$triplet/ossl-modules"; \
        install -m 0644 /tmp/fips-provider/out/fips.so "$moddir/fips.so"; \
        openssl fipsinstall -module "$moddir/fips.so" -provider_name fips -out /dev/null; \
        install -d -o ucm -g ucm -m 0700 /run/ucm; \
    fi

# SoftHSM tokens live in the data volume, so a recreated container keeps its keys
RUN sed -i 's#^directories.tokendir.*#directories.tokendir = /opt/ucm/data/softhsm/tokens/#' /etc/softhsm/softhsm2.conf && \
    grep -q '^directories.tokendir = /opt/ucm/data/softhsm/tokens/$' /etc/softhsm/softhsm2.conf

# Copy virtual environment from builder
COPY --from=builder /opt/ucm/venv /opt/ucm/venv

# Set working directory (same as DEB/RPM)
WORKDIR /opt/ucm

# Copy application files with proper ownership (same layout as packages)
COPY --chown=ucm:ucm VERSION /opt/ucm/VERSION
COPY --chown=ucm:ucm LICENSE NOTICE /opt/ucm/
COPY --chown=ucm:ucm backend/ /opt/ucm/backend/
# Only the built interface: the server serves frontend/dist, while frontend/
# as a whole carries the sources and node_modules, several hundred megabytes
# of build-time dependencies that have no place in a runtime image
COPY --chown=ucm:ucm frontend/dist/ /opt/ucm/frontend/dist/
COPY --chown=ucm:ucm wsgi.py /opt/ucm/wsgi.py
COPY --chown=ucm:ucm .env.docker.example /opt/ucm/.env.example

# Create data + log directories
# Listed one by one: this runs under /bin/sh, which does not expand braces on
# a Debian base image, and a single directory named after the whole list
# would be created instead of the nine wanted here
RUN for d in ca certs private crl scep backups sessions logs temp; do \
        mkdir -p "/opt/ucm/data/$d"; \
    done && \
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

# Expose HTTPS port (and optional HTTP protocol port for CDP/OCSP)
EXPOSE 8443
EXPOSE 8080

# Declare persistent volumes.
# /etc/ucm holds master.key — the symmetric key that decrypts every private
# key in the database. If the container is recreated without this volume
# bind-mounted, master.key is destroyed and ALL encrypted CAs / certs / ACME
# / SSH-CA private keys in the DB become unrecoverable. ALWAYS bind-mount
# /etc/ucm to a host path or named volume before enabling encryption.
# /opt/ucm/data holds the SQLite DB, CA files, sessions, backups.
VOLUME ["/etc/ucm", "/opt/ucm/data"]

# Health check, on the port UCM listens on (UCM_HTTPS_PORT, 8443 by default)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f -k "https://127.0.0.1:${UCM_HTTPS_PORT:-8443}/health" || exit 1

# Copy entrypoint before switching user
COPY --chown=ucm:ucm docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER ucm

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command - Gunicorn from /opt/ucm/backend (same as packages)
CMD ["sh", "-c", "cd /opt/ucm/backend && gunicorn -c gunicorn_config.py wsgi:app"]
