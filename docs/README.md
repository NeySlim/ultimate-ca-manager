# UCM Documentation

Technical documentation for Ultimate Certificate Manager.

## Guides

- **[USER_GUIDE.md](./USER_GUIDE.md)** — Getting started
- **[ADMIN_GUIDE.md](./ADMIN_GUIDE.md)** — Server configuration & administration
- **[ADVANCED-FEATURES.md](./ADVANCED-FEATURES.md)** — Advanced features overview
- **[SECURITY.md](./SECURITY.md)** — Security documentation

## Installation

- **[installation/README.md](./installation/README.md)** — All installation methods (DEB, RPM, Docker)
- **[installation/docker.md](./installation/docker.md)** — Docker & docker-compose deployment

## API

- **[API_REFERENCE.md](./API_REFERENCE.md)** — Complete API reference (347+ endpoints)

## Operations

- **[HSM_DOCKER.md](./HSM_DOCKER.md)** — HSM integration in Docker
- **[LOG_ROTATION.md](./LOG_ROTATION.md)** — Log rotation configuration
- **[REDIS.md](./REDIS.md)** — Optional Redis integration
- **[TESTING.md](./TESTING.md)** — Testing & linting guide (unit + E2E + ESLint + Ruff)

### ACME testing notes

- **[testing/PUBLIC-ENDPOINTS.md](./testing/PUBLIC-ENDPOINTS.md)** — Admin/protocol/ACME URLs, DNS preflight, env vars, pitfalls
- **[testing/ACME-PUBLIC-VHOST.md](./testing/ACME-PUBLIC-VHOST.md)** — Public ACME vhost, wildcard TLS, test plan
- **[testing/ACME-PROXY-MULTI-CA.md](./testing/ACME-PROXY-MULTI-CA.md)** — Multi-CA proxy endpoints
- **[testing/ACME-DNS-PROPAGATION.md](./testing/ACME-DNS-PROPAGATION.md)** — DNS-01 propagation checks

## Architecture

| Component | Stack |
|-----------|-------|
| Backend | Flask + SQLAlchemy |
| API | REST v2 (`/api/v2`) |
| Auth | Session-based |
| Database | SQLite (default) or PostgreSQL 13+ |
| Frontend | React 18 + Radix UI + Vite |

## Links

- **[GitHub](https://github.com/NeySlim/ultimate-ca-manager)**
- **[Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)**
- **[Docker Hub](https://hub.docker.com/r/neyslim/ultimate-ca-manager)**
- **[Changelog](../CHANGELOG.md)**
