# UCM Documentation

Technical documentation for Ultimate CA Manager.

## Guides

- **[USER_GUIDE.md](./USER_GUIDE.md)** — Getting started
- **[ADMIN_GUIDE.md](./ADMIN_GUIDE.md)** — Server configuration & administration
- **[ADVANCED-FEATURES.md](./ADVANCED-FEATURES.md)** — Advanced features overview
- **[SECURITY.md](./SECURITY.md)** — Security documentation

## Installation

- **[installation/README.md](./installation/README.md)** — All installation methods (DEB, RPM, Docker)
- **[installation/docker.md](./installation/docker.md)** — Docker & docker-compose deployment

## API

- **[API_REFERENCE.md](./API_REFERENCE.md)** — Complete API reference (155+ endpoints)

## Operations

- **[LOG_ROTATION.md](./LOG_ROTATION.md)** — Log rotation configuration
- **[REDIS.md](./REDIS.md)** — Optional Redis integration
- **[TESTING.md](./TESTING.md)** — Testing guide (unit + E2E)

## Architecture

| Component | Stack |
|-----------|-------|
| Backend | Flask + SQLAlchemy |
| API | REST v2 (`/api/v2`) |
| Auth | Session-based |
| Database | SQLite |
| Frontend | React 18 + Radix UI + Vite |

## Links

- **[GitHub](https://github.com/NeySlim/ultimate-ca-manager)**
- **[Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)**
- **[Docker Hub](https://hub.docker.com/r/neyslim/ultimate-ca-manager)**
- **[Changelog](../CHANGELOG.md)**
