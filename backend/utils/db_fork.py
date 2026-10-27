"""Database connections across gunicorn's fork."""


def forget_inherited_connections(engine):
    """Drop, without closing, the pooled connections a forked worker inherited.

    With preload_app the master opens connections before forking and keeps
    using them (scheduler); a worker reusing one shares its PostgreSQL socket,
    and the replies of both processes interleave.
    """
    engine.dispose(close=False)
