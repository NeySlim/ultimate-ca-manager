"""Tests written against the 2.x settings, on the default Windows enrollment profile.

``set_config``/``get_config`` take the 2.x keys: those the profile replaced
(``services.windows_profiles.legacy.MIGRATED_KEYS``) read and write the default profile,
created when missing; every other key is a SystemConfig row. Callers hold an app context.
"""
from models import SystemConfig, WindowsEnrollmentProfile, db

FIELDS = {
    'xcep_ca_refid': 'policy_ca_refid', 'xcep_username': 'xcep_username',
    'xcep_password': 'xcep_password', 'wstep_ca_refid': 'issuing_ca_refid',
    'wstep_username': 'wstep_username', 'wstep_password': 'wstep_password',
    'wstep_validity_days': 'validity_days',
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
