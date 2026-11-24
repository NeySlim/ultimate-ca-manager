"""Teardown of an application a test built: every pool it opened is closed."""


def dispose_app(application):
    """The request engine, then the SQL session store's own pool: left to garbage collection,
    the store's connections pile up on a shared PostgreSQL until max_connections."""
    from models import db
    with application.app_context():
        db.session.remove()
        db.engine.dispose()
    dispose = getattr(application.session_interface, 'dispose', None)
    if dispose is not None:
        dispose()
