# Redis

Redis is reserved for a future high-availability mode and has no use on a single UCM instance, which is the only supported deployment today: sessions survive restarts, and real-time events stay within the process.

Without Redis, sessions are kept on disk, except on PostgreSQL, where they are kept in the database and shared between nodes.

When `REDIS_URL` (or `UCM_REDIS_URL`) is set, UCM keeps its sessions in Redis and relays its WebSocket events through it, one database number per installation. The DEB and RPM packages and the Docker image ship the `redis` Python package; an installation from source without it logs a warning and ignores the variable.

The scheduled tasks run in a process of their own, to which no browser is connected. Without Redis, that process writes each WebSocket event it emits (a certificate issued or renewed by an automatic renewal, for instance) to the `websocket_relay` table, and every web worker reads the rows newer than its own cursor every 2 seconds and sends them to its clients, once each and in emission order. A worker that starts reads only what is emitted after it; rows are purged after 10 minutes, and an unreachable database delays the events (at most 1000 are kept in memory) without blocking the scheduler or the workers. If the connection drops during the commit of a batch that the server did accept, the batch is written again and clients receive its events, and the notifications they raise, twice; this is accepted because it needs the connection to drop at that exact instant and each event only reports a change already made. With Redis the events go through Redis and the table stays empty.
