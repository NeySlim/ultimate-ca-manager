# Redis

Redis is reserved for a future high-availability mode and has no use on a single UCM instance, which is the only supported deployment today: sessions are kept on disk and survive restarts, and real-time events stay within the process.

When `REDIS_URL` (or `UCM_REDIS_URL`) is set and the `redis` Python package is installed, UCM keeps its sessions in Redis and relays its WebSocket events through it, one database number per installation. UCM packages and the Docker image do not ship that package; without it, UCM logs a warning and ignores the variable.
