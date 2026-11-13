"""Connector rows for tests: one row, linked to the default Windows profile when one exists.

Callers hold an app context. ``connector_row`` is the lowest-id row, what a 2.x install has alone.
"""
from models import ADConnectorConfig, WindowsEnrollmentProfile, db


def connector_row():
    return ADConnectorConfig.query.order_by(ADConnectorConfig.id).limit(1).one_or_none()


def add_connector(name='default', password='irrelevant', link=False, **values):
    """Add a row beside the others; *link* points the default profile at it."""
    config = ADConnectorConfig(name=name, **values)
    if password is not None:
        config.bind_password = password
    db.session.add(config)
    db.session.flush()
    if link:
        profile = WindowsEnrollmentProfile.query.filter_by(is_default=True).one_or_none()
        if profile is not None:
            profile.connector_id = config.id
    db.session.commit()
    return config


def mount_connector(**values):
    """Replace every row with one built from *values* and link the default profile to it."""
    profiles = WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.connector_id.isnot(None))
    profiles.update({'connector_id': None})
    ADConnectorConfig.query.delete()
    db.session.commit()
    return add_connector(link=True, **values)


def clear_connectors():
    """No connector row, and no profile pointing at one."""
    WindowsEnrollmentProfile.query.update({'connector_id': None})
    ADConnectorConfig.query.delete()
    db.session.commit()
