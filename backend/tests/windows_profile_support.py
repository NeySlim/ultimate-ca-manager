"""Tests written against the 2.x settings, on the default Windows enrollment profile.

``set_config``/``get_config`` take the 2.x keys: those the profile replaced
(``services.windows_profiles.legacy.MIGRATED_KEYS``) read and write the default profile,
created when missing; every other key is a SystemConfig row. Callers hold an app context.
"""
from contextlib import contextmanager

import pytest
from sqlalchemy import delete, insert, select, update

from models import ADConnectorConfig, SystemConfig, WindowsEnrollmentProfile, WindowsProfileTemplate, db

FIELDS = {
    'xcep_ca_refid': 'policy_ca_refid', 'xcep_username': 'xcep_username',
    'xcep_password': 'xcep_password', 'wstep_ca_refid': 'issuing_ca_refid',
    'wstep_username': 'wstep_username', 'wstep_password': 'wstep_password',
    'wstep_validity_days': 'validity_days', 'windows_realm': 'realm',
}


def default_profile(create=False):
    profile = WindowsEnrollmentProfile.query.filter_by(is_default=True).first()
    if profile is None and create:
        profile = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True)
        db.session.add(profile)
    return profile


def _stored(field, value):
    if field == 'validity_days':
        return int(value) if value not in (None, '') else 365
    return value or None


def set_config(key, value, commit=True):
    if key in FIELDS:
        setattr(default_profile(create=True), FIELDS[key], _stored(FIELDS[key], value))
    else:
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None:
            db.session.add(SystemConfig(key=key, value=value))
        else:
            row.value = value
    if commit:
        db.session.commit()


def get_config(key):
    if key in FIELDS:
        profile = default_profile()
        value = getattr(profile, FIELDS[key]) if profile is not None else None
        return str(value) if value is not None else None
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row is not None else None


def delete_config(key, commit=True):
    if key in FIELDS:
        profile = default_profile()
        if profile is not None:
            setattr(profile, FIELDS[key], 365 if key == 'wstep_validity_days' else None)
    else:
        SystemConfig.query.filter_by(key=key).delete()
    if commit:
        db.session.commit()


@contextmanager
def default_realm(app, realm):
    """The default profile serves Kerberos principals of *realm* for the duration, then gets
    its realm back: a principal is served by the profile of its realm only."""
    with app.app_context():
        saved = snapshot(('windows_realm',))
        set_config('windows_realm', realm)
    try:
        yield
    finally:
        with app.app_context():
            restore(saved)


def snapshot(keys):
    return {key: get_config(key) for key in keys}


def restore(saved):
    """Put back what ``snapshot`` read: a value, or no value at all."""
    for key, value in saved.items():
        if value is None:
            delete_config(key, commit=False)
        else:
            set_config(key, value, commit=False)
    db.session.commit()


def default_profile_id(client):
    """The id of the default profile, made when missing."""
    with client.application.app_context():
        from services import windows_profiles
        profile_id = windows_profiles.default_for_write('test', fill=False).id
        db.session.commit()
    return profile_id


def put_default_profile(client, **fields):
    """PUT *fields* on the default profile, made when missing."""
    profile_id = default_profile_id(client)
    return client.put(f'/api/v2/windows-profiles/{profile_id}', json=fields)


def upload_keytab(client, data, profile_id=None, filename='ucm.keytab', **form):
    """POST *data* as the keytab of a profile; the default one, made when missing, if none is named."""
    import io
    if profile_id is None:
        profile_id = default_profile_id(client)
    body = {'file': (io.BytesIO(data), filename), **form}
    return client.post(f'/api/v2/windows-profiles/{profile_id}/keytab', data=body,
                       content_type='multipart/form-data')


@contextmanager
def connectors_kept(app):
    """The AD connector rows, and the profiles' links to them and realms, put back as they
    were: a connector left enabled, or the realm a saved one gave a profile, would reach the
    next file's Kerberos tests."""
    connectors, profiles = ADConnectorConfig.__table__, WindowsEnrollmentProfile.__table__
    with app.app_context():
        rows = [dict(r._mapping) for r in db.session.execute(select(connectors))]
        links = {i: (c, realm) for i, c, realm in db.session.execute(
            select(profiles.c.id, profiles.c.connector_id, profiles.c.realm))}
        db.session.commit()
    try:
        yield
    finally:
        with app.app_context():
            db.session.execute(update(profiles).values(connector_id=None))
            db.session.execute(delete(connectors))
            if rows:
                db.session.execute(insert(connectors), rows)
            for profile_id, (connector_id, realm) in links.items():
                db.session.execute(update(profiles).where(profiles.c.id == profile_id)
                                   .values(connector_id=connector_id, realm=realm))
            db.session.commit()


@contextmanager
def profiles_kept(app):
    """Every Windows profile row and its template links put back as they were, the default
    one included: a default profile left, or its keytab and realm, reaches the next file."""
    profiles, links = WindowsEnrollmentProfile.__table__, WindowsProfileTemplate.__table__
    with app.app_context():
        saved = [dict(r._mapping) for r in db.session.execute(select(profiles).order_by(profiles.c.id))]
        saved_links = [dict(r._mapping) for r in db.session.execute(select(links))]
        db.session.commit()
    try:
        yield
    finally:
        with app.app_context():
            from models import CertificateTemplate
            # A connector or template the file deleted is not linked back (foreign keys on PostgreSQL)
            connectors = set(db.session.execute(select(ADConnectorConfig.__table__.c.id)).scalars())
            templates = set(db.session.execute(select(CertificateTemplate.__table__.c.id)).scalars())
            db.session.execute(delete(links))
            db.session.execute(delete(profiles))
            if saved:
                db.session.execute(insert(profiles), [
                    {**row, 'connector_id': row['connector_id'] if row['connector_id'] in connectors else None}
                    for row in saved])
            kept_links = [row for row in saved_links if row['template_id'] in templates]
            if kept_links:
                db.session.execute(insert(links), kept_links)
            db.session.commit()


@pytest.fixture(autouse=True, scope='module')
def windows_profiles_restored(app):
    """Imported by a test file that changes the Windows profiles: puts them back after it."""
    with profiles_kept(app):
        yield
