"""Database connections across gunicorn's fork."""


def forget_inherited_connections(engines):
    """Drop, without closing, the pooled connections a forked worker inherited.

    With preload_app the master opens connections before forking; a worker
    reusing one shares its PostgreSQL socket, and the replies of both
    processes interleave. Every bind's engine is covered, not only the default.
    """
    for engine in engines:
        engine.dispose(close=False)
