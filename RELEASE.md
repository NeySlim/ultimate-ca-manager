# UCM Release & Deployment Guide

> **This document has been consolidated.** Please refer to:
> - **[README.md](README.md)** — Quick start & installation
> - **[CHANGELOG.md](CHANGELOG.md)** — Release history
> - **[Installation Guide](docs/installation/README.md)** — Detailed installation instructions
> - **[Docker Guide](docs/installation/docker.md)** — Docker-specific deployment

## Package Locations

After installation, all platforms use the same layout:

| Location | Path |
|----------|------|
| Application | `/opt/ucm/` |
| Data | `/opt/ucm/data/` |
| Config | `/etc/ucm/ucm.env` |
| Logs | `/var/log/ucm/` |
| Service | `systemctl status ucm` |
