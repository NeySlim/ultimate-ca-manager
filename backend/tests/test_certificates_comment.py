"""Issue #454: a plain-text comment on a certificate, edited apart from its display name.

PATCH /api/v2/certificates/<id> takes `descr`, `comment` or both; an invalid field refuses the
whole request. The comment is searched by the list and the global search, sorted on, audited
by its length only, and carried by the backup archive.
"""
import pytest

from models import AuditLog, Certificate, db

BASE = '/api/v2/certificates'
MAX = 4000


@pytest.fixture
def commented_cert(app, create_cert):
    cert_id = create_cert()['id']
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        cert.descr = 'Comment test'
        cert.comment = 'Before'
        db.session.commit()
    return cert_id


def _stored(app, cert_id):
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        return cert.descr, cert.comment


def test_comment_round_trip_and_search(auth_client, commented_cert):
    comment = f'Zuständig: Müller\n\tTicket {commented_cert}-100%_done <script>alert(1)</script>'
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': comment})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == comment
    assert response.get_json()['data']['descr'] == 'Comment test'
    assert auth_client.get(f'{BASE}/{commented_cert}').get_json()['data']['comment'] == comment
    rows = auth_client.get(BASE, query_string={'search': f'{commented_cert}-100%_done', 'per_page': 100}).get_json()['data']
    assert [row['id'] for row in rows] == [commented_cert]
    assert rows[0]['comment'] == comment


def test_the_list_search_takes_like_wildcards_literally(auth_client, commented_cert):
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': 'abc'})
    rows = auth_client.get(BASE, query_string={'search': 'a_c', 'per_page': 100}).get_json()['data']
    assert commented_cert not in [row['id'] for row in rows]


@pytest.mark.parametrize('value', ['', None])
def test_clearing_the_comment_stores_nothing(app, auth_client, commented_cert, value):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': value})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == ''
    assert _stored(app, commented_cert) == ('Comment test', None)


def test_the_longest_comment_is_kept_whole(auth_client, commented_cert):
    # Characters, not bytes: 4,000 two-byte letters are accepted
    value = 'é' * MAX
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': value})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == value


@pytest.mark.parametrize('body', [
    {'comment': 1}, {'comment': False}, {'comment': []}, {'comment': {}},
    {'comment': 'x' * (MAX + 1)},
    {'comment': 'nul\x00'}, {'comment': 'bell\x07'}, {'comment': 'cr\r\nlf'}, {'comment': 'del\x7f'},
    {'comment': 'nel\x85'}, {'comment': 'esc\x1b[31m'},
    [], ['comment'], 'comment', {}, {'other': 'x'},
    {'descr': 'Changed', 'comment': 1}, {'descr': '', 'comment': 'Changed'},
    {'descr': None, 'comment': 'Changed'}, {'descr': 'Changed', 'comment': 'x' * (MAX + 1)},
])
def test_an_invalid_patch_changes_nothing(app, auth_client, commented_cert, body):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json=body)
    assert response.status_code == 400, response.data
    assert _stored(app, commented_cert) == ('Comment test', 'Before')


def test_rename_keeps_the_comment_and_both_change_together(auth_client, commented_cert):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'descr': 'Renamed'})
    assert response.get_json()['data']['comment'] == 'Before'
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'descr': 'Both', 'comment': 'After'})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['descr'] == 'Both'
    assert response.get_json()['data']['comment'] == 'After'


def test_a_comment_needs_the_write_permission(app, client, viewer_client, commented_cert):
    assert client.patch(f'{BASE}/{commented_cert}', json={'comment': 'No'}).status_code == 401
    assert viewer_client.patch(f'{BASE}/{commented_cert}', json={'comment': 'No'}).status_code == 403
    assert _stored(app, commented_cert) == ('Comment test', 'Before')
    response = viewer_client.get(f'{BASE}/{commented_cert}')
    assert response.status_code == 200
    assert response.get_json()['data']['comment'] == 'Before'


def test_a_missing_certificate_is_404(auth_client):
    assert auth_client.patch(f'{BASE}/99999999', json={'comment': 'No'}).status_code == 404


def _comment_audits(app, cert_id):
    with app.app_context():
        return [(row.action, row.details) for row in AuditLog.query.filter_by(
            resource_type='certificate', resource_id=str(cert_id)).order_by(AuditLog.id)
            if row.action == 'certificate_comment_updated']


def test_the_audit_gives_the_lengths_never_the_text(app, auth_client, commented_cert):
    secret = 'Ticket INC-4242 owner jane'
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': secret})
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': secret})     # unchanged: no entry
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': None})
    audits = _comment_audits(app, commented_cert)
    assert [details for _action, details in audits] == [
        f'Comment changed: 6 -> {len(secret)} characters', f'Comment cleared: {len(secret)} -> 0 characters']
    assert not any('INC-4242' in details or 'Before' in details for _action, details in audits)


def test_a_rename_alone_writes_no_comment_audit(app, auth_client, commented_cert):
    auth_client.patch(f'{BASE}/{commented_cert}', json={'descr': 'Renamed only'})
    assert _comment_audits(app, commented_cert) == []


def test_the_list_sorts_on_the_comment(app, auth_client, create_cert):
    ids = [create_cert(cn=f'sort454-{n}.example.com')['id'] for n in range(3)]
    with app.app_context():
        for cert_id, comment in zip(ids, ['zz-454-b', None, 'zz-454-a']):
            db.session.get(Certificate, cert_id).comment = comment
        db.session.commit()

    def order(direction):
        rows = auth_client.get(BASE, query_string={'sort_by': 'comment', 'sort_order': direction,
                                                   'search': 'sort454-', 'per_page': 100}).get_json()['data']
        return [row['id'] for row in rows]
    # No comment comes last in both directions, on both backends, as in every sorted list
    assert order('asc') == [ids[2], ids[0], ids[1]]
    assert order('desc') == [ids[0], ids[2], ids[1]]


def test_the_global_search_finds_a_comment(auth_client, commented_cert):
    token = f'owner-454-{commented_cert}x'
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': f'rack B12 {token}'})
    found = auth_client.get('/api/v2/search', query_string={'q': token}).get_json()['data']
    assert [row['id'] for row in found['certificates']] == [commented_cert]


def test_the_global_search_reads_no_comment_without_the_read_permission(app, auth_client, commented_cert,
                                                                       monkeypatch):
    import api.v2.search as search
    token = f'owner-454-{commented_cert}x'
    auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': f'rack B12 {token}'})
    real = search.has_permission
    monkeypatch.setattr(search, 'has_permission',
                        lambda permission, granted: permission != 'read:certificates' and real(permission, granted))
    found = auth_client.get('/api/v2/search', query_string={'q': token}).get_json()['data']
    assert found['certificates'] == []


def _raw_patch(auth_client, cert_id, body):
    """A JSON body written by hand: json.dumps cannot spell a lone surrogate escape for us."""
    return auth_client.patch(f'{BASE}/{cert_id}', data=body, content_type='application/json')


@pytest.mark.parametrize('body', [
    '{"comment": "half \\ud800 a pair"}', '{"comment": "\\udfff"}', '{"descr": "half \\ud800"}',
    '{"descr": "Renamed", "comment": "\\ud83d"}',
])
def test_a_lone_surrogate_is_refused_with_400(app, auth_client, commented_cert, body):
    response = _raw_patch(auth_client, commented_cert, body)
    assert response.status_code == 400, response.data
    assert _stored(app, commented_cert) == ('Comment test', 'Before')


def test_a_surrogate_pair_is_one_character_and_kept(auth_client, commented_cert):
    response = _raw_patch(auth_client, commented_cert, '{"comment": "rack \\ud83d\\udd12 B12"}')
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == 'rack \U0001F512 B12'


@pytest.mark.parametrize('mark', ['\u202e', '\u202a', '\u202b', '\u202c', '\u202d', '\u2066',
                                  '\u2067', '\u2068', '\u2069', '\u200e', '\u200f', '\u061c'])
def test_a_direction_control_is_refused_with_400(app, auth_client, commented_cert, mark):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': f'invoice{mark}fdp.exe'})
    assert response.status_code == 400, response.data
    assert _stored(app, commented_cert) == ('Comment test', 'Before')


def test_a_joiner_is_no_direction_control(auth_client, commented_cert):
    # ZWJ inside an emoji sequence, ZWNJ in Persian: format characters a comment keeps
    value = 'team \U0001F469‍\U0001F4BB می‌خواهم'
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': value})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == value


@pytest.mark.parametrize('value', [' ', '   \n\t  ', ' 　'])
def test_a_comment_of_blanks_only_is_cleared(app, auth_client, commented_cert, value):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': value})
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['comment'] == ''
    assert _stored(app, commented_cert) == ('Comment test', None)
    assert [details for _a, details in _comment_audits(app, commented_cert)] == [
        'Comment cleared: 6 -> 0 characters']


def test_a_comment_with_text_keeps_its_blanks(auth_client, commented_cert):
    response = auth_client.patch(f'{BASE}/{commented_cert}', json={'comment': '  indented\n'})
    assert response.get_json()['data']['comment'] == '  indented\n'


@pytest.fixture
def revoked_by_record(app, commented_cert):
    """The certificate's CA holds a revocation of its serial that the row does not carry."""
    from datetime import timedelta
    from models.revoked_serial import RevokedSerial
    from utils.datetime_utils import utc_now
    with app.app_context():
        cert = db.session.get(Certificate, commented_cert)
        assert not cert.revoked
        record = RevokedSerial(caref=cert.caref, serial_number=cert.serial_number, revoked_at=utc_now(),
                               revoke_reason='keyCompromise', valid_to=utc_now() + timedelta(days=30),
                               certificate_id=cert.id)
        db.session.add(record)
        db.session.commit()
        record_id = record.id
    yield commented_cert
    with app.app_context():
        db.session.delete(db.session.get(RevokedSerial, record_id))
        db.session.commit()


def test_the_patch_answers_what_the_get_answers(auth_client, revoked_by_record):
    response = auth_client.patch(f'{BASE}/{revoked_by_record}', json={'comment': 'After'})
    assert response.status_code == 200, response.data
    patched = response.get_json()['data']
    shown = auth_client.get(f'{BASE}/{revoked_by_record}').get_json()['data']
    assert shown['revoked'] is True and shown['revoke_reason'] == 'keyCompromise'
    assert patched == shown
