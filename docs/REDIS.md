# Redis

Redis is reserved for a future high-availability mode and has no use on a single UCM instance, which is the only supported deployment today: sessions survive restarts, and real-time events stay within the process.

Without Redis, sessions are kept on disk, except on PostgreSQL, where they are kept in the database and shared between nodes.

When `REDIS_URL` (or `UCM_REDIS_URL`) is set, UCM keeps its sessions in Redis and relays its WebSocket events through it, one database number per installation. The DEB and RPM packages and the Docker image ship the `redis` Python package; an installation from source without it logs a warning and ignores the variable.
