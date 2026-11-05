"""Settings that name a row by its number follow that row through a restore.

`scep_ca_id`, `acme.issuing_ca_id`, `acme_public_tls_cert_id` and the others
kept the source's number, so SCEP or ACME could sign with whichever authority
held it on the target.
"""
import uuid

import pytest

from models import db
from tests.test_backup_cross_installation import PASSWORD, _service
from tests.test_backup_hostile_corpus import _reseal
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _restore, _snapshot, _user, target,
)


def _setting(key, value=None):
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        return row.value if row is not None else None
    if row is None:
        row = SystemConfig(key=key)
        db.session.add(row)
    row.value = value
    return value


def _settings(prefix):
    from models import SystemConfig
    return {row.key: row.value for row in SystemConfig.query.all() if row.key.startswith(prefix)}


def _account(label, directory='https://ca.example.test/directory'):
    from models.acme_client_account import AcmeClientAccount
    row = AcmeClientAccount(label=label, email=f'{uuid.uuid4().hex[:6]}@example.test',
                            directory_url=directory)
    db.session.add(row)
    db.session.flush()
    return row


def _cross(ca, fingerprint):
    from models.ca_cross_certificate import CACrossCertificate
    row = CACrossCertificate(ca_id=ca.id, crt='x', fingerprint_sha256=fingerprint)
    db.session.add(row)
    db.session.flush()
    return row


def _scene():
    """Two of everything a setting names; every setting names the second."""
    _user('settings-admin')
    first = _authority_row('settings-ca-a')
    second = _authority_row('settings-ca-b')
    ca = second[0]
    _certificate_row('settings-cert-a', first)
    cert = _certificate_row('settings-cert-b', first)
    _account('settings-acct-a')
    account = _account('settings-acct-b')
    _cross(ca, 'a' * 64)
    cross = _cross(ca, 'b' * 64)
    for key, value in {
            'scep_ca_id': str(ca.id),
            'acme.issuing_ca_id': str(ca.id),
            'acme_public_tls_cert_id': str(cert.id),
            'acme.proxy.acme_account_id': str(account.id),
            f'ocsp_responder_cert_{ca.id}': str(cert.id),
            f'scep_challenge_{ca.id}': 'settings-challenge',
            f'scep_challenge_{ca.id}_generated_at': '2026-11-05T00:00:00',
            f'cert_scts_{cert.id}': '[{"log": "settings"}]',
            f'ca_url_cross_{ca.refid}': str(cross.id)}.items():
        _setting(key, value)
    db.session.commit()


def _renumber():
    """Remove the scene and hand its numbers to rows the archive does not name."""
    from models import CA, Certificate, SystemConfig
    from models.acme_client_account import AcmeClientAccount
    from models.ca_cross_certificate import CACrossCertificate

    for model in (CACrossCertificate, Certificate, AcmeClientAccount, CA):
        db.session.query(model).delete()
    for row in SystemConfig.query.all():
        if any(row.key.startswith(p) for p in ('scep_', 'acme', 'ocsp_responder_cert_',
                                               'cert_scts_', 'ca_url_cross_')):
            db.session.delete(row)
    db.session.flush()
    filler_a, filler_b = _authority_row('settings-filler-a'), _authority_row('settings-filler-b')
    for name in ('settings-filler-1', 'settings-filler-2', 'settings-filler-3'):
        _certificate_row(name, filler_a)
    _account('settings-filler-acct-1')
    _account('settings-filler-acct-2')
    _cross(filler_b[0], 'c' * 64)
    _cross(filler_b[0], 'd' * 64)
    db.session.commit()


def _here():
    from models import CA, Certificate
    from models.acme_client_account import AcmeClientAccount
    from models.ca_cross_certificate import CACrossCertificate
    return (CA.query.filter_by(refid='settings-ca-b').one(),
            Certificate.query.filter_by(refid='settings-cert-b').one(),
            AcmeClientAccount.query.filter_by(label='settings-acct-b').one(),
            CACrossCertificate.query.filter_by(fingerprint_sha256='b' * 64).one())


def _edited(blob, edit):
    data = _service()._decrypt_framed(blob, PASSWORD)[1]
    edit(data)
    return _reseal(blob, data)


def test_every_numbered_setting_follows_its_row(target):
    _scene()
    blob = _snapshot()
    _renumber()

    results = _restore(blob, mode='merge')

    ca, cert, account, cross = _here()
    assert {key: _setting(key) for key in (
        'scep_ca_id', 'acme.issuing_ca_id', 'acme_public_tls_cert_id',
        'acme.proxy.acme_account_id', f'ca_url_cross_{ca.refid}')} == {
        'scep_ca_id': str(ca.id), 'acme.issuing_ca_id': str(ca.id),
        'acme_public_tls_cert_id': str(cert.id), 'acme.proxy.acme_account_id': str(account.id),
        f'ca_url_cross_{ca.refid}': str(cross.id)}
    assert _settings('ocsp_responder_cert_') == {f'ocsp_responder_cert_{ca.id}': str(cert.id)}
    assert set(_settings('scep_challenge_')) == {
        f'scep_challenge_{ca.id}', f'scep_challenge_{ca.id}_generated_at'}
    assert _settings('cert_scts_') == {f'cert_scts_{cert.id}': '[{"log": "settings"}]'}
    assert not [w for w in results['warnings'] if w.startswith('setting ')]


def test_a_row_this_installation_lacks_empties_the_setting_and_says_so(target):
    from services.backup.restore_report import with_restore_warnings

    _scene()

    def elsewhere(data):
        for entry in data['configuration']['settings_refs']:
            if entry['table'] == 'certificate_authorities':
                entry['identity'] = {'refid': 'settings-not-here'}
    blob = _edited(_snapshot(), elsewhere)

    results = _restore(blob, mode='merge')

    ca, cert, _account_row, _cross_row = _here()
    assert _setting('scep_ca_id') == '' and _setting('acme.issuing_ca_id') == ''
    assert _setting('acme_public_tls_cert_id') == str(cert.id)
    message = with_restore_warnings('Restored', results)
    assert 'setting scep_ca_id was emptied' in message
    assert f'setting scep_challenge_{ca.id} was left out' in message
    # Left out: nothing written under another number, the row here keeps its own
    assert set(_settings('scep_challenge_')) == {
        f'scep_challenge_{ca.id}', f'scep_challenge_{ca.id}_generated_at'}
    assert set(_settings('ocsp_responder_cert_')) == {f'ocsp_responder_cert_{ca.id}'}


def _older(data, installation=None):
    data['configuration'].pop('settings_refs')
    if installation is not None:
        data['metadata']['installation_id'] = installation


def test_an_older_archive_from_elsewhere_applies_no_number(target):
    _scene()
    _setting('acme.issuing_ca_id', 'settings-ca-b')    # a refid reads the same anywhere
    blob = _edited(_snapshot(), lambda data: _older(data, 'another-installation'))
    _renumber()

    results = _restore(blob, mode='merge')

    assert _setting('scep_ca_id') == '' and _setting('acme_public_tls_cert_id') == ''
    assert _setting('acme.issuing_ca_id') == 'settings-ca-b'
    assert _settings('ocsp_responder_cert_') == {} and _settings('cert_scts_') == {}
    assert sum(w.startswith('setting ') for w in results['warnings']) >= 6


def test_an_older_archive_of_this_database_keeps_a_number_still_there(target):
    _scene()
    ca, _cert, _account_row, _cross_row = _here()
    _setting('acme_public_tls_cert_id', '987654')     # a certificate since deleted
    db.session.commit()
    blob = _edited(_snapshot(), _older)

    results = _restore(blob, mode='merge')

    assert _setting('scep_ca_id') == str(ca.id)
    assert _setting(f'scep_challenge_{ca.id}') == 'settings-challenge'
    assert _setting('acme_public_tls_cert_id') == ''
    assert any('acme_public_tls_cert_id was emptied' in w for w in results['warnings'])


def test_a_renamed_account_keeps_the_proxy_setting(target):
    """Lot 3 restores a homonym under another name: the setting follows the archived row."""
    from models.acme_client_account import AcmeClientAccount

    _user('settings-admin')
    archived = _account('settings-acct', 'https://archived.example.test/directory')
    _setting('acme.proxy.acme_account_id', str(archived.id))
    blob = _snapshot()
    db.session.delete(archived)
    db.session.flush()
    _account('settings-acct', 'https://here.example.test/directory')
    db.session.commit()

    _restore(blob, mode='merge')

    named = db.session.get(AcmeClientAccount, int(_setting('acme.proxy.acme_account_id')))
    assert (named.label, named.directory_url) == (
        'settings-acct (2)', 'https://archived.example.test/directory')


@pytest.mark.parametrize('key, matches', [
    ('scep_ca_id', True), ('scep_challenge_12_generated_at', True), ('scep_challenge_validity', False),
    ('ocsp_responder_cert_3', True), ('ocsp_responder_renew_days', False),
    ('est_ca_refid', False), ('ca_url_alias_7', False),
])
def test_the_declaration_names_the_numbered_keys_only(key, matches):
    from services.backup.restore.setting_refs import reference_of
    assert (reference_of(key) is not None) is matches


def test_a_replacement_drops_the_settings_of_the_rows_it_removes(target):
    """A CA made after the archive leaves its challenge and responder, and holds SCEP."""
    from models import CA

    _user('settings-admin')
    archived, _key, _cert = _authority_row('settings-archived')
    archived_number = archived.id
    blob = _snapshot()
    db.session.delete(archived)
    db.session.flush()
    later = _authority_row('settings-later')
    leaf = _certificate_row('settings-later-leaf', later)
    number = later[0].id
    for key, value in {f'scep_challenge_{number}': 'later-challenge',
                       f'ocsp_responder_cert_{number}': str(leaf.id),
                       f'cert_scts_{leaf.id}': '[]',
                       'scep_ca_id': str(number), 'acme.issuing_ca_id': 'settings-later'}.items():
        _setting(key, value)
    db.session.commit()
    if target == 'sqlite':
        assert number == archived_number    # the archived CA takes that number back

    _restore(blob)

    assert CA.query.filter_by(refid='settings-archived').one()
    assert _settings('scep_challenge_') == {} and _settings('ocsp_responder_cert_') == {}
    assert _settings('cert_scts_') == {}
    assert _setting('scep_ca_id') in ('', None) and _setting('acme.issuing_ca_id') in ('', None)


def test_an_older_archive_of_this_database_takes_no_number_another_row_holds(target):
    from models import CA

    _user('settings-admin')
    archived, _key, _cert = _authority_row('settings-ca-a')
    _setting('scep_ca_id', str(archived.id))
    number = archived.id
    blob = _edited(_snapshot(), _older)
    db.session.delete(archived)
    db.session.flush()
    intruder = _authority_row('settings-intruder')[0]
    db.session.commit()
    if target == 'sqlite':
        assert intruder.id == number

    results = _restore(blob, mode='merge')

    assert CA.query.filter_by(refid='settings-ca-a').one().id != number or target != 'sqlite'
    assert _setting('scep_ca_id') == ''
    assert any('scep_ca_id was emptied' in w for w in results['warnings'])
