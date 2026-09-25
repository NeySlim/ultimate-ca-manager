"""Database URLs as SQLAlchemy is given them."""

_POSTGRES_PREFIXES = ('postgresql://', 'postgres://')


def sqlalchemy_url(url: str) -> str:
    """Pin a PostgreSQL URL without a driver to psycopg2, the one UCM ships.

    SQLAlchemy 2.1 resolves a bare postgresql:// to psycopg 3. An explicit
    driver and non-PostgreSQL URLs are returned unchanged.
    """
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return 'postgresql+psycopg2://' + url[len(prefix):]
    return url


def is_postgres_url(url: str) -> bool:
    """True for every PostgreSQL spelling: postgres://, postgresql://, postgresql+driver://."""
    return sqlalchemy_url(url or '').startswith(('postgresql://', 'postgresql+'))
