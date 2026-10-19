"""The ACME client's global renewal settings drive the scheduled renewal.

`acme.client.renewal_enabled` (the Let's Encrypt tab switch) and
`acme.client.renewal_days` were saved and never read: the task renewed every
order flagged per order, always 30 days before expiry.
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from models import db, SystemConfig
from models.acme_models import AcmeClientOrder
from services import acme_renewal_service as renew_mod
from utils.datetime_utils import utc_now


@pytest.fixture
def settings(app):
    keys = ('acme.client.renewal_enabled', 'acme.client.renewal_days')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}

    def apply(**values):
        with app.app_context():
            for k, v in values.items():
                key = f'acme.client.{k}'
                row = SystemConfig.query.filter_by(key=key).first()
                if row is None:
                    row = SystemConfig(key=key)
                    db.session.add(row)
                row.value = v
            db.session.commit()

    yield apply
    with app.app_context():
        for k, v in saved.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None:
                if row:
                    db.session.delete(row)
            else:
                row.value = v
        db.session.commit()


@pytest.fixture
def make_order(app):
    created = []

    def _make(expires_in_days):
        with app.app_context():
            o = AcmeClientOrder(domains=json.dumps([f'{uuid.uuid4().hex[:8]}.example.com']),
                                environment='staging', challenge_type='dns-01', status='issued',
                                order_url=f'https://ca.example/order/{uuid.uuid4().hex[:8]}',
                                renewal_enabled=True,
                                expires_at=utc_now() + timedelta(days=expires_in_days))
            db.session.add(o)
            db.session.commit()
            created.append(o.id)
            return o.id
    yield _make
    with app.app_context():
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(created)).delete(synchronize_session=False)
        db.session.commit()


def _renewed(app, oid):
    renewed = []
    with app.app_context():
        # No certificate: the fixed threshold decides, not ARI.
        with patch.object(renew_mod, 'renew_certificate', side_effect=lambda o: renewed.append(o.id)):
            renew_mod.scheduled_acme_renewal()
    return oid in renewed


def test_global_switch_off_renews_nothing(app, settings, make_order):
    settings(renewal_enabled='false')
    assert not _renewed(app, make_order(10))


def test_global_switch_on_renews(app, settings, make_order):
    settings(renewal_enabled='true')
    assert _renewed(app, make_order(10))
