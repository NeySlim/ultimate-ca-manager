"""GET /api/v2/dashboard/queue: what needs acting on, critical first, with the
total per kind counted in SQL rather than from the truncated list."""
import json
import secrets
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from api.v2.dashboard import DASHBOARD_MAX_ROWS
from models import CA, Certificate, SystemConfig, db
from models.acme_models import AcmeAccount, AcmeClientOrder, AcmeOrder
from models.crl import CRLMetadata
from models.hsm import HsmKey, HsmProvider
from models.key_recovery import KeyRecoveryRequest
from models.policy import ApprovalRequest
from models.scep import SCEPRequest
from tests.conftest import get_json
from tests.dashboard_pem import self_signed
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/queue'
_PEM = [self_signed(ec.generate_private_key(ec.SECP256R1()))]
SETTINGS = ('auto_renewal_enabled', 'auto_renewal_sources')
ACME_SWITCH = 'acme.client.renewal_enabled'
OCSP_SWITCH = 'ocsp_responder_auto_renew'


def _ca(name, **kw):
    ca = CA(refid=str(uuid.uuid4()), descr=name, crt='placeholder', **kw)
    db.session.add(ca)
    db.session.flush()
    return ca


def _crl(ca, next_update, **kw):
    now = utc_now()
    number = kw.pop('crl_number', 1)
    db.session.add(CRLMetadata(ca_id=ca.id, crl_number=number, this_update=now, next_update=next_update,
                               crl_pem='-', crl_der=b'-', **kw))


def _cert(name, valid_to, **kw):
    kw.setdefault('source', 'manual')
    kw.setdefault('subject_cn', name)
    row = Certificate(refid=str(uuid.uuid4()), descr=name, crt=_PEM[0],
                      valid_from=utc_now() - timedelta(days=300), valid_to=valid_to, **kw)
    db.session.add(row)
    db.session.flush()
    return row


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


@pytest.fixture(scope='module')
def seeded(app):
    now = utc_now()
    ids = {}
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in SETTINGS}
        _set('auto_renewal_enabled', 'true')
        _set('auto_renewal_sources', '["manual"]')
        account = AcmeAccount(jwk='{}', jwk_thumbprint=secrets.token_hex(16))
        db.session.add(account)
        db.session.flush()
        failed = AcmeOrder(account_id=account.account_id, status='invalid', identifiers='[{"type": "dns", '
                           '"value": "queue-failed.test"}]', created_at=now - timedelta(days=1))
        old = AcmeOrder(account_id=account.account_id, status='invalid', identifiers='[]',
                        created_at=now - timedelta(days=8))
        client = AcmeClientOrder(domains='["queue-client.test"]', renewal_failures=2, last_error_at=now)
        healthy = AcmeClientOrder(domains='["queue-ok.test"]', renewal_failures=0)
        renewing = AcmeClientOrder(domains='["queue-acme-client.test"]', status='issued', renewal_enabled=True)
        not_renewing = AcmeClientOrder(domains='["queue-acme-off.test"]', status='issued', renewal_enabled=False)
        urgent = ApprovalRequest(request_type='certificate', status='pending', expires_at=now + timedelta(hours=2))
        calm = ApprovalRequest(request_type='renewal', status='pending')
        done = ApprovalRequest(request_type='renewal', status='approved')
        scep = SCEPRequest(transaction_id='queue-txn', csr='-', status='pending', subject='CN=queue-scep')
        recovery = KeyRecoveryRequest(cert_id=1, reason='lost', requested_by='admin', cert_cn='queue-kr')
        db.session.add_all([failed, old, client, healthy, renewing, not_renewing, urgent, calm, done, scep, recovery])
        crl_soon = _ca('queue-crl-soon', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_soon, now + timedelta(days=7), crl_number=1, created_at=now - timedelta(days=1))
        _crl(crl_soon, now + timedelta(hours=12), crl_number=2)
        _crl(crl_soon, now + timedelta(days=9), crl_number=3, is_delta=True)  # a delta does not count
        # validity 1 day, just regenerated: half its life is still ahead
        crl_daily = _ca('queue-crl-daily', cdp_enabled=True, crl_validity_days=1, valid_to=now + timedelta(days=3650))
        _crl(crl_daily, now + timedelta(hours=24))
        crl_stale = _ca('queue-crl-stale', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_stale, now - timedelta(hours=1))
        crl_6h = _ca('queue-crl-6h', cdp_enabled=True, crl_validity_days=7, valid_to=now + timedelta(days=3650))
        _crl(crl_6h, now + timedelta(hours=6))
        crl_fresh = _ca('queue-crl-fresh', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_fresh, now + timedelta(days=7))
        crl_renewed = _ca('queue-crl-renewed', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_renewed, now + timedelta(hours=12), crl_number=1)  # superseded by number 2
        _crl(crl_renewed, now + timedelta(days=7), crl_number=2)
        crl_none = _ca('queue-crl-none', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        # Offline CAs publish uploaded CRLs; the CDP serves the newest full one by number, uploads included
        crl_offline = _ca('queue-crl-offline', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_offline, now + timedelta(hours=12), crl_number=1)
        _crl(crl_offline, now + timedelta(days=30), crl_number=5, is_external=True)
        crl_upload = _ca('queue-crl-upload', cdp_enabled=True, valid_to=now + timedelta(days=3650))
        _crl(crl_upload, now + timedelta(days=30), crl_number=5, is_external=True)
        no_cdp = _ca('queue-no-cdp', cdp_enabled=False, valid_to=now + timedelta(days=3650))
        ca_soon = _ca('queue-ca-60d', valid_to=now + timedelta(days=60))
        ca_later = _ca('queue-ca-200d', valid_to=now + timedelta(days=200))
        ca_revoked = _ca('queue-ca-revoked', valid_to=now + timedelta(days=60), revoked=True)
        # auto-renewal fails on every pass under a CA that cannot sign
        ca_offline = _ca('queue-ca-offline', offline=True, prv='k', valid_to=now + timedelta(days=3650))
        ca_revoked_far = _ca('queue-ca-revoked-far', revoked=True, prv='k', valid_to=now + timedelta(days=3650))
        ca_lapsed = _ca('queue-ca-lapsed', prv='k', valid_to=now - timedelta(days=1))
        ca_keyless = _ca('queue-ca-keyless', valid_to=now + timedelta(days=3650))
        provider = HsmProvider(name=f'queue-hsm-{uuid.uuid4()}', type='openbao', config='{}')
        db.session.add(provider)
        db.session.flush()
        hsm_key = HsmKey(provider_id=provider.id, key_identifier='queue-hsm-key', label='queue-hsm-key',
                         algorithm='EC-P256', key_type='EC', purpose='ca-signing')
        db.session.add(hsm_key)
        db.session.flush()
        ca_hsm = _ca('queue-ca-hsm', hsm_key_id=hsm_key.id, valid_to=now + timedelta(days=3650))
        ca_signing = _ca('queue-ca-signing', prv='k', valid_to=now + timedelta(days=3650))
        certs = {
            'blocked_offline': _cert('queue-blocked-offline', now + timedelta(days=10), prv='k', caref=ca_offline.refid),
            'blocked_revoked': _cert('queue-blocked-revoked', now + timedelta(days=10), prv='k',
                                     caref=ca_revoked_far.refid),
            'blocked_lapsed_ca': _cert('queue-blocked-lapsed', now + timedelta(days=10), prv='k',
                                       caref=ca_lapsed.refid),
            'blocked_keyless': _cert('queue-blocked-keyless', now + timedelta(days=10), prv='k', caref=ca_keyless.refid),
            'under_hsm': _cert('queue-under-hsm', now + timedelta(days=10), prv='k', caref=ca_hsm.refid),
            'under_signing': _cert('queue-under-signing', now + timedelta(days=10), prv='k', caref=ca_signing.refid),
            'declined': _cert('queue-declined', now + timedelta(days=10), prv='k', caref=ca_offline.refid),
            'declined_last_cycle': _cert('queue-declined-old', now + timedelta(days=10), prv='k',
                                         caref=ca_signing.refid),
            # a delegated OCSP responder is renewed by its own task, which needs the key
            'ocsp_responder': _cert('queue-ocsp', now + timedelta(days=10), prv='k', source='import',
                                    caref=ca_signing.refid),
            'ocsp_responder_nokey': _cert('queue-ocsp-nokey', now + timedelta(days=10), caref=ca_keyless.refid),
            'no_key_12h': _cert('queue-nokey-12h', now + timedelta(hours=12)),
            'no_key_10d': _cert('queue-nokey-10d', now + timedelta(days=10)),
            'null_source_10d': _cert('queue-null-source', now + timedelta(days=10), source=None),
            'excluded_source': _cert('queue-scep', now + timedelta(days=10), prv='k', source='scep'),
            'auto': _cert('queue-auto', now + timedelta(days=10), prv='k'),
            'revoked': _cert('queue-revoked', now + timedelta(days=10), revoked=True),
            'archived': _cert('queue-archived', now + timedelta(days=10), archived=True),
            'far': _cert('queue-far', now + timedelta(days=90)),
            'expired': _cert('queue-expired', now - timedelta(days=1)),
            # the client holds the key and renews through its protocol, or UCM's ACME client renews it
            'acme_nokey': _cert('queue-acme', now + timedelta(days=20), source='acme'),
            'wstep_nokey': _cert('queue-wstep', now + timedelta(days=20), source='wstep'),
            # a client that has not renewed a week before expiry is overdue
            'scep_nokey_5d': _cert('queue-scep-5d', now + timedelta(days=5), source='scep'),
            'scep_nokey_20d': _cert('queue-scep-20d', now + timedelta(days=20), source='scep'),
            'acme_client': _cert('queue-acme-client', now + timedelta(days=10), prv='k', source='acme_client'),
            # UCM's ACME client renews only through an issued order with renewal on
            'acme_client_off': _cert('queue-acme-off', now + timedelta(days=10), prv='k', source='acme_client'),
            'acme_client_orphan': _cert('queue-acme-orphan', now + timedelta(days=10), prv='k',
                                        source='acme_client'),
            'superseded': _cert('queue-superseded', now + timedelta(days=10), caref=crl_fresh.refid),
            'successor': _cert('queue-successor', now + timedelta(days=300), caref=crl_fresh.refid,
                               subject_cn='queue-superseded'),
            # same CN but another host: neither renews the other
            'homonym_10d': _cert('queue-homonym', now + timedelta(days=10), caref=crl_fresh.refid,
                                 san_dns='["a.queue.test"]'),
            'homonym_300d': _cert('queue-homonym', now + timedelta(days=300), caref=crl_fresh.refid,
                                  san_dns='["b.queue.test"]'),
            'other_ip_10d': _cert('queue-other-ip', now + timedelta(days=10), caref=crl_fresh.refid,
                                  san_ip='["192.0.2.1"]'),
            'other_ip_300d': _cert('queue-other-ip', now + timedelta(days=300), caref=crl_fresh.refid,
                                   san_ip='["192.0.2.2"]'),
            'other_dn_10d': _cert('queue-other-dn', now + timedelta(days=10), caref=crl_fresh.refid,
                                  subject='CN=queue-other-dn,O=A'),
            'other_dn_300d': _cert('queue-other-dn', now + timedelta(days=300), caref=crl_fresh.refid,
                                   subject='CN=queue-other-dn,O=B'),
            'blank_cn_10d': _cert('queue-blank-10d', now + timedelta(days=10), caref=crl_fresh.refid, subject_cn=''),
            'blank_cn_300d': _cert('queue-blank-300d', now + timedelta(days=300), caref=crl_fresh.refid, subject_cn=''),
            # a successor that expires inside the window still needs renewing, so it hides nothing
            'twin_10d': _cert('queue-twin', now + timedelta(days=10), caref=crl_fresh.refid),
            'twin_20d': _cert('queue-twin', now + timedelta(days=20), caref=crl_fresh.refid),
            'revoked_successor_of': _cert('queue-revoked-succ', now + timedelta(days=10), caref=crl_fresh.refid),
            'revoked_successor': _cert('queue-revoked-succ-new', now + timedelta(days=300), caref=crl_fresh.refid,
                                       subject_cn='queue-revoked-succ', revoked=True),
        }
        renewing.certificate_id = certs['acme_client'].id
        rejected = ApprovalRequest(request_type='renewal', status='rejected', created_at=now - timedelta(days=1),
                                   request_data=json.dumps({'certificate_id': certs['declined'].id, 'ca_id': None, 'trigger': 'auto'}))
        # rejected before the certificate was last renewed: a decision on the previous cycle
        rejected_old = ApprovalRequest(
            request_type='renewal', status='rejected', created_at=now - timedelta(days=400),
            request_data=json.dumps({'certificate_id': certs['declined_last_cycle'].id, 'ca_id': None}))
        db.session.add_all([rejected, rejected_old])
        bindings = [SystemConfig(key=f'ocsp_responder_cert_{ca_signing.id}', value=str(certs['ocsp_responder'].id)),
                    SystemConfig(key=f'ocsp_responder_cert_{ca_keyless.id}',
                                 value=str(certs['ocsp_responder_nokey'].id))]
        db.session.add_all(bindings)
        not_renewing.certificate_id = certs['acme_client_off'].id
        db.session.commit()
        ids.update(hsm_provider=provider.id, hsm_key=hsm_key.id, rejected=rejected.id, rejected_old=rejected_old.id, ca_offline=ca_offline.id,
                   ca_revoked_far=ca_revoked_far.id, ca_keyless=ca_keyless.id, ca_lapsed=ca_lapsed.id, ca_hsm=ca_hsm.id,
                   ca_signing=ca_signing.id, renewing=renewing.id, not_renewing=not_renewing.id, failed=failed.id, old=old.id, client=client.id, healthy=healthy.id, urgent=urgent.id,
                   calm=calm.id, done=done.id, scep=scep.id, recovery=recovery.id,
                   crl_daily=crl_daily.id, crl_stale=crl_stale.id, crl_6h=crl_6h.id,
                   crl_soon=crl_soon.id, crl_fresh=crl_fresh.id, crl_renewed=crl_renewed.id, crl_none=crl_none.id,
                   crl_offline=crl_offline.id, crl_upload=crl_upload.id, no_cdp=no_cdp.id,
                   ca_soon=ca_soon.id, ca_later=ca_later.id, ca_revoked=ca_revoked.id,
                   **{k: v.id for k, v in certs.items()}, account=account.id)
    yield ids
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(
            [f"ocsp_responder_cert_{ids[k]}" for k in ('ca_signing', 'ca_keyless')])).delete(synchronize_session=False)
        for model, keys in ((AcmeClientOrder, ('client', 'healthy', 'renewing', 'not_renewing')),
                            (Certificate, certs), (AcmeOrder, ('failed', 'old')), (ApprovalRequest, ('urgent', 'calm', 'done', 'rejected', 'rejected_old')),
                            (SCEPRequest, ('scep',)), (KeyRecoveryRequest, ('recovery',))):
            for key in keys:
                row = db.session.get(model, ids[key])
                if row is not None:
                    db.session.delete(row)
        cas = [ids[k] for k in ('crl_daily', 'crl_stale', 'crl_6h', 'crl_soon', 'crl_fresh', 'crl_renewed', 'crl_none', 'crl_offline', 'crl_upload', 'no_cdp', 'ca_soon', 'ca_later', 'ca_revoked',
                                'ca_offline', 'ca_revoked_far', 'ca_keyless', 'ca_lapsed', 'ca_hsm', 'ca_signing')]
        CRLMetadata.query.filter(CRLMetadata.ca_id.in_(cas)).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(cas)).delete(synchronize_session=False)
        HsmKey.query.filter_by(id=ids['hsm_key']).delete(synchronize_session=False)
        HsmProvider.query.filter_by(id=ids['hsm_provider']).delete(synchronize_session=False)
        db.session.delete(db.session.get(AcmeAccount, ids['account']))
        for key, value in saved.items():
            _set(key, value)
        db.session.commit()


def _queue(client, *kinds):
    """The whole queue, or the items of *kinds* only: other files' leftovers on the same
    worker (CAs without a CRL, pending requests) would otherwise fill the capped listing."""
    r = client.get(URL, query_string=[('kind', k) for k in kinds])
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def _item(client, kind, item_id):
    return _find(_queue(client, kind), kind, item_id)


def _find(data, kind, item_id):
    return next((i for i in data['items'] if i['kind'] == kind and i['id'] == item_id), None)


@pytest.mark.parametrize('kind, key, tier', [
    ('acme_order_failed', 'failed', 'critical'),
    ('acme_client_renewal_failed', 'client', 'critical'),
    ('approval_pending', 'urgent', 'critical'),
    ('approval_pending', 'calm', 'warning'),
    ('scep_request_pending', 'scep', 'warning'),
    ('key_recovery_pending', 'recovery', 'warning'),
    ('crl_due', 'crl_soon', 'warning'),
    ('crl_due', 'crl_6h', 'warning'),
    ('crl_due', 'crl_stale', 'critical'),
    ('crl_missing', 'crl_none', 'critical'),
    ('manual_renewal_due', 'no_key_12h', 'critical'),
    ('manual_renewal_due', 'no_key_10d', 'warning'),
    ('manual_renewal_due', 'null_source_10d', 'warning'),
    ('manual_renewal_due', 'excluded_source', 'warning'),
    ('manual_renewal_due', 'revoked_successor_of', 'warning'),
    ('manual_renewal_due', 'acme_client_off', 'warning'),
    ('manual_renewal_due', 'homonym_10d', 'warning'),
    ('manual_renewal_due', 'other_ip_10d', 'warning'),
    ('manual_renewal_due', 'other_dn_10d', 'warning'),
    ('manual_renewal_due', 'blank_cn_10d', 'warning'),
    ('manual_renewal_due', 'twin_10d', 'warning'),
    ('manual_renewal_due', 'twin_20d', 'warning'),
    ('manual_renewal_due', 'acme_client_orphan', 'warning'),
    ('ca_expiring', 'ca_soon', 'critical'),
    ('ca_expiring', 'ca_later', 'warning'),
    ('client_renewal_overdue', 'scep_nokey_5d', 'warning'),
    ('auto_renewal_blocked', 'blocked_offline', 'critical'),
    ('auto_renewal_blocked', 'blocked_revoked', 'critical'),
    ('auto_renewal_blocked', 'blocked_keyless', 'critical'),
    ('auto_renewal_blocked', 'blocked_lapsed_ca', 'critical'),
    ('manual_renewal_due', 'ocsp_responder_nokey', 'warning'),
    ('renewal_declined', 'declined', 'warning'),
])
def test_each_kind_with_its_tier_and_due_date(app, auth_client, seeded, kind, key, tier):
    item = _item(auth_client, kind, seeded[key])
    assert item is not None, (kind, key)
    assert item['tier'] == tier
    assert item['due_at'] and item['href_hint'] and item['label']


def test_crl_due_date_is_the_latest_full_crl(auth_client, seeded):
    item = _item(auth_client, 'crl_due', seeded['crl_soon'])
    due = item['due_at']
    assert due < (utc_now() + timedelta(hours=13)).isoformat()


@pytest.mark.parametrize('kind, key', [
    ('acme_order_failed', 'old'), ('acme_client_renewal_failed', 'healthy'),
    ('approval_pending', 'done'), ('crl_due', 'crl_fresh'), ('crl_missing', 'crl_fresh'),
    ('crl_due', 'crl_renewed'), ('crl_due', 'crl_daily'), ('crl_missing', 'crl_daily'),
    ('crl_due', 'crl_offline'), ('crl_missing', 'crl_offline'),
    ('crl_due', 'crl_upload'), ('crl_missing', 'crl_upload'),
    ('manual_renewal_due', 'acme_nokey'), ('manual_renewal_due', 'wstep_nokey'),
    ('manual_renewal_due', 'scep_nokey_5d'), ('client_renewal_overdue', 'scep_nokey_20d'),
    ('client_renewal_overdue', 'acme_nokey'), ('client_renewal_overdue', 'no_key_12h'),
    ('auto_renewal_blocked', 'under_hsm'), ('auto_renewal_blocked', 'under_signing'),
    ('auto_renewal_blocked', 'auto'), ('auto_renewal_blocked', 'no_key_10d'),
    ('manual_renewal_due', 'blocked_offline'), ('manual_renewal_due', 'under_signing'),
    ('auto_renewal_blocked', 'declined'), ('manual_renewal_due', 'declined'),
    ('renewal_declined', 'declined_last_cycle'), ('renewal_declined', 'under_signing'),
    ('manual_renewal_due', 'ocsp_responder'),
    ('manual_renewal_due', 'acme_client'), ('manual_renewal_due', 'superseded'),
    ('crl_missing', 'no_cdp'), ('ca_expiring', 'ca_revoked'),
    ('manual_renewal_due', 'auto'), ('manual_renewal_due', 'revoked'),
    ('manual_renewal_due', 'archived'), ('manual_renewal_due', 'far'), ('manual_renewal_due', 'expired'),
])
def test_left_out(auth_client, seeded, kind, key):
    assert _item(auth_client, kind, seeded[key]) is None


def test_auto_renewal_off_makes_every_renewal_manual(app, auth_client, seeded):
    with app.app_context():
        _set('auto_renewal_enabled', 'false')
        db.session.commit()
    try:
        assert _item(auth_client, 'manual_renewal_due', seeded['auto']) is not None
    finally:
        with app.app_context():
            _set('auto_renewal_enabled', 'true')
            db.session.commit()


def test_acme_client_renewal_switched_off_makes_it_manual(app, auth_client, seeded):
    with app.app_context():
        saved = getattr(SystemConfig.query.filter_by(key=ACME_SWITCH).first(), 'value', None)
        _set(ACME_SWITCH, 'false')
        db.session.commit()
    try:
        assert _item(auth_client, 'manual_renewal_due', seeded['acme_client']) is not None
        with app.app_context():
            _set(ACME_SWITCH, 'true')
            db.session.commit()
        assert _item(auth_client, 'manual_renewal_due', seeded['acme_client']) is None
    finally:
        with app.app_context():
            _set(ACME_SWITCH, saved)
            db.session.commit()


def test_ocsp_responder_renewal_switched_off_makes_it_manual(app, auth_client, seeded):
    with app.app_context():
        saved = getattr(SystemConfig.query.filter_by(key=OCSP_SWITCH).first(), 'value', None)
        _set(OCSP_SWITCH, 'false')
        db.session.commit()
    try:
        assert _item(auth_client, 'manual_renewal_due', seeded['ocsp_responder']) is not None
    finally:
        with app.app_context():
            _set(OCSP_SWITCH, saved)
            db.session.commit()


def test_sorted_critical_first_then_by_due_date(auth_client, seeded):
    items = _queue(auth_client)['items']
    keys = [(0 if i['tier'] == 'critical' else 1, i['due_at']) for i in items]
    assert keys == sorted(keys)


def test_counts_are_exact_when_the_list_is_truncated(app, auth_client, seeded):
    before = _queue(auth_client)['counts']
    extra = DASHBOARD_MAX_ROWS + 5
    with app.app_context():
        rows = [SCEPRequest(transaction_id=f'queue-bulk-{i}', csr='-', status='pending') for i in range(extra)]
        db.session.add_all(rows)
        db.session.commit()
        bulk = [r.id for r in rows]
    try:
        data = _queue(auth_client)
        assert len(data['items']) == DASHBOARD_MAX_ROWS
        assert data['counts']['scep_request_pending'] == before['scep_request_pending'] + extra
        assert data['total'] == sum(data['counts'].values()) > DASHBOARD_MAX_ROWS
        assert len(get_json(auth_client.get(f'{URL}?limit=3'))['data']['items']) == 3
    finally:
        with app.app_context():
            SCEPRequest.query.filter(SCEPRequest.id.in_(bulk)).delete(synchronize_session=False)
            db.session.commit()


def test_kind_restricts_the_items_but_not_the_counts(auth_client, seeded):
    whole = _queue(auth_client)
    r = auth_client.get(URL, query_string=[('kind', 'crl_due'), ('kind', 'crl_missing')])
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert {i['kind'] for i in data['items']} == {'crl_due', 'crl_missing'}
    wanted = whole['counts']['crl_due'] + whole['counts']['crl_missing']
    assert len(data['items']) == min(wanted, DASHBOARD_MAX_ROWS)
    assert data['counts'] == whole['counts']
    r = auth_client.get(f'{URL}?kind=crl_due&kind=nonsense')
    assert r.status_code == 400
    assert 'nonsense' in get_json(r)['message']
    r = auth_client.get(f'{URL}?kind=&kind=crl_missing')  # an empty value is no kind
    assert r.status_code == 200, r.data
    assert {i['kind'] for i in get_json(r)['data']['items']} == {'crl_missing'}


def test_a_key_without_read_dashboard_is_refused(app, auth_client):
    """Every built-in role holds read:dashboard, so the refusal is shown with a scoped API key."""
    r = auth_client.post('/api/v2/account/apikeys',
                         json={'name': 'queue-no-dashboard', 'permissions': ['read:certificates']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        assert app.test_client().get(URL, headers={'X-API-Key': key['key']}).status_code == 403
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


@pytest.fixture
def viewer(app, auth_client, request):
    """The shared viewer client, its account removed again when this file created it."""
    from models import User
    with app.app_context():
        existed = User.query.filter_by(username='viewer_test').first() is not None
    yield request.getfixturevalue('viewer_client')
    if not existed:
        with app.app_context():
            user = User.query.filter_by(username='viewer_test').first()
            user_id = user.id if user else None
        if user_id is not None:
            r = auth_client.delete(f'/api/v2/users/{user_id}')
            assert r.status_code in (200, 204), r.data


def test_the_viewer_role_reads_it(viewer):
    assert viewer.get(URL).status_code == 200


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
