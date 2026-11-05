"""Hostile archives, past the framing: what a chosen file does to the reader.

`tests/test_backup_container.py` stops at the container — the framing, the KDF
profile, the compression bomb, the schema an archive announces about itself.
This file picks up where the container is well-formed and the payload is not:
a file that stops in the middle, a section that is not the shape it claims to
be, a row nothing can identify, an archive that carries nothing at all, and a
field holding a value no column can take.

Three things are asked of every case here, and they are the reason the file
exists rather than the individual inputs:

* the refusal is explicit and names what it is about, so an administrator can
  act on it instead of retyping the password;
* nothing reaches the caller that it should not — no traceback, no driver
  error, no internal path;
* the instance is exactly as it was, which is checked by counting rows before
  and after rather than by trusting the refusal.

The archives are built from this installation (`_forged`, as in
test_backup_restore_failfast), carrying one section: the suite's database is
shared by every file of a worker, so an archive of everything would rewrite
rows other files are watching.
"""
import base64
import gzip
import hashlib
import io
import json
import struct
from contextlib import contextmanager

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from models import db
from services.backup import container, manifest
from services.backup.restore import RestorePlan, RestoreValidationError

PASSWORD = 'Correct-Horse-Battery-9'

RESTORE_URL = '/api/v2/system/restore'

# The section every forged archive is built around: nothing points at a
# deployment target, so a row that did land could be taken back out without
# leaving a foreign key pointing at nothing.
SECTION = 'deploy_targets'

HOSTILE_PREFIX = 'hostile-corpus-'

TARGET = {
    'name': HOSTILE_PREFIX + 'target',
    'host': 'deploy.example.test',
    'port': 22,
    'username': 'ucm',
    'private_key': 'not-a-real-key',
    'enabled': True,
}

# What must never come back to the caller, whatever it is refusing.
LEAKED_INTERNALS = ('Traceback', 'File "', 'sqlite3', 'sqlalchemy',
                    'psycopg2', '/root/', 'site-packages')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _header_of(blob):
    metadata_len = struct.unpack('>H', blob[8:10])[0]
    return blob[:10 + metadata_len]


def _key_of(header):
    """The master key of an archive, derived the way its own header says."""
    metadata = json.loads(header[10:].decode())
    salt = base64.b64decode(metadata['salt_b64'])
    svc = _service()
    kdf = metadata['kdf']
    if kdf['type'] == 'argon2id':
        return svc._derive_argon2id(
            PASSWORD, salt, time_cost=kdf['time_cost'],
            memory_cost=kdf['memory_cost'], parallelism=kdf['parallelism'],
            hash_len=kdf['hash_len'])
    return svc._derive_pbkdf2(PASSWORD, salt, kdf['iterations'])


def _seal(header, plaintext: bytes) -> bytes:
    """Frame arbitrary bytes as the payload of a valid, authenticated v3 container."""
    metadata = json.loads(header[10:].decode())
    nonce = base64.b64decode(metadata['nonce_b64'])
    return header + AESGCM(_key_of(header)).encrypt(
        nonce, gzip.compress(plaintext), header)


def _reseal(original_blob, data, finalise=None):
    """Rewrite an archive's payload, keeping its container and password.

    Counts and per-section digests are recomputed from the payload being
    written: the reader checks both before the first write, so a forged
    payload would otherwise be refused as a corrupted archive rather than by
    the check under test. `finalise` edits what the archive says about itself
    once those are in place, and is still covered by the checksum.
    """
    svc = _service()
    header = _header_of(original_blob)
    data.pop('checksum', None)
    payload_metadata = data.setdefault('metadata', {})
    payload_metadata['sections'] = {
        name: len(value) for name, value in data.items()
        if name != 'metadata' and isinstance(value, (list, dict))}
    payload_metadata['section_digests'] = svc._section_digests(data)
    if finalise is not None:
        finalise(data)

    digest = hashlib.sha256(
        json.dumps(data, indent=2, sort_keys=True).encode()).hexdigest()
    data['checksum'] = {'algorithm': 'SHA256', 'value': digest}
    return _seal(header, json.dumps(data, indent=2, sort_keys=True).encode())


def _forged(sections, mutate=None, finalise=None, **rows):
    """A real archive of `sections`, with rows added and the payload edited.

    Must be called inside an application context: the sections are exported
    from the database, so what is fed back is a file this server wrote.
    """
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only(*sections))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    for name, extra in rows.items():
        data.setdefault(name, []).extend(extra)
    if mutate is not None:
        mutate(data)
    return _reseal(blob, data, finalise=finalise)


def _census():
    """Row counts an unwanted write would move. Needs an application context."""
    from models import CA, Certificate, SystemConfig, User
    from models.deploy import DeployTarget
    from models.group import Group

    return {
        'users': User.query.count(),
        'cas': CA.query.count(),
        'certificates': Certificate.query.count(),
        'groups': Group.query.count(),
        'settings': SystemConfig.query.count(),
        'deploy_targets': DeployTarget.query.count(),
    }


def _drop_forged_targets():
    """Take back anything a case did manage to write. Needs a context."""
    from models.deploy import DeployTarget

    db.session.rollback()
    DeployTarget.query.filter(
        DeployTarget.name.like(HOSTILE_PREFIX + '%')).delete(
            synchronize_session=False)
    db.session.commit()


def _restore(auth_client, blob, filename='hostile.ucmbkp', password=PASSWORD):
    return auth_client.post(
        RESTORE_URL,
        data={'password': password, 'file': (io.BytesIO(blob), filename)},
        content_type='multipart/form-data')


def _message(response) -> str:
    body = response.get_json(silent=True) or {}
    return str(body.get('message') or body.get('error') or '')


def _assert_refused_cleanly(response, before, after):
    """The shape every refusal in this file has to have."""
    assert response.status_code != 200, (
        f'a hostile archive was accepted: {response.data[:300]}')
    body = response.data.decode(errors='replace')
    for internal in LEAKED_INTERNALS:
        assert internal not in body, f'the refusal leaked {internal!r}: {body[:300]}'
    assert after == before, f'the instance moved: {before} -> {after}'


@pytest.fixture(scope='module')
def archive(app):
    """A real archive of one section of this instance."""
    with app.app_context():
        return _service().create_backup(PASSWORD, include=_only(SECTION))


@pytest.fixture(autouse=True)
def no_forged_rows_left(app):
    """Whatever a case wrote, the next file must not find it."""
    yield
    with app.app_context():
        _drop_forged_targets()


# ---------------------------------------------------------------------------
# A file that stops in the middle
# ---------------------------------------------------------------------------

class TestATruncatedArchiveIsNotAWrongPassword:
    """Damage the reader can prove is reported as damage.

    An archive that arrives short — a download that stopped, a copy off a
    full disk — used to be indistinguishable from a typing mistake, and an
    administrator told "wrong password" retypes the password instead of
    fetching the file again. Everything the framing can check is checked
    before a key is derived, and says so.
    """

    @pytest.mark.parametrize('where, cut', [
        ('inside the magic and the framing bytes', lambda blob, header: blob[:6]),
        ('inside the header metadata', lambda blob, header: blob[:len(header) - 20]),
        ('at the end of the header, before any ciphertext',
         lambda blob, header: header),
        ('one byte short of the GCM tag',
         lambda blob, header: header + b'\x00' * (container.GCM_TAG_SIZE - 1)),
    ])
    def test_a_truncation_the_framing_can_see_is_named(
            self, app, archive, auth_client, where, cut):
        blob = cut(archive, _header_of(archive))
        with app.app_context():
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)

        assert response.status_code == 400, response.data
        message = _message(response)
        assert 'truncated' in message.lower(), (where, message)
        assert 'password' not in message.lower(), (
            f'a file truncated {where} was blamed on the password: {message}')

    @pytest.mark.parametrize('where, cut', [
        ('halfway through the ciphertext',
         lambda blob, header: header + blob[len(header):][:(len(blob) - len(header)) // 2]),
        ('just before the GCM tag', lambda blob, header: blob[:-container.GCM_TAG_SIZE]),
        ('one byte from the end', lambda blob, header: blob[:-1]),
    ])
    def test_a_truncation_only_the_tag_can_see_names_both_causes(
            self, app, archive, auth_client, where, cut):
        """Past the header, the two are the same event to AES-GCM.

        The tag fails identically for a wrong key and for bytes that were cut,
        and nothing else in the file can be trusted before it verifies. What
        the answer must therefore never do is pick one: it names both, so the
        administrator checks the file as well as the password.
        """
        blob = cut(archive, _header_of(archive))
        with app.app_context():
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)

        assert response.status_code == 400, response.data
        message = _message(response).lower()
        assert 'password' in message and (
            'not a valid backup' in message or 'corrupt' in message), (
            f'a file truncated {where} was refused with: {message}')

    def test_a_file_too_small_to_be_an_archive_is_refused(
            self, app, auth_client):
        """Zero bytes is a name with an extension and nothing behind it."""
        with app.app_context():
            before = _census()

        response = _restore(auth_client, b'')

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400, response.data


# ---------------------------------------------------------------------------
# A section that is not the shape it claims to be
# ---------------------------------------------------------------------------

def _as_object(data):
    data[SECTION] = {'hostile': dict(TARGET)}


def _null_section(data):
    data[SECTION] = None


def _null_row(data):
    data[SECTION] = [None]


def _string_row(data):
    data[SECTION] = ['a deployment target']


def _configuration_as_list(data):
    data['configuration'] = []


def _date_as_text(data):
    data[SECTION] = [dict(TARGET, created_at='yesterday')]


def _count_as_text(data):
    data['metadata']['sections'][SECTION] = 'three'


SHAPES = {
    'an object where a list of rows belongs': (_as_object, SECTION),
    'null where a list of rows belongs': (_null_section, SECTION),
    'null where a row belongs': (_null_row, SECTION),
    'a string where a row belongs': (_string_row, SECTION),
    'a list where the settings object belongs': (_configuration_as_list,
                                                 'configuration'),
    'text where a date belongs': (_date_as_text, SECTION),
}


@contextmanager
def _target_for(app, tmp_path, mode):
    """A replacing restore prunes: it runs on an installation no other test wrote to."""
    if mode != 'replace':
        with app.app_context():
            yield
        return
    from tests.test_backup_cross_installation import Keys, _installation
    with _installation(app, f"sqlite:///{tmp_path / 'hostile.db'}", Keys(tmp_path, 'hostile')), \
            app.app_context():
        yield
        db.session.rollback()


class TestASectionOfTheWrongTypeIsRefusedByName:
    """A payload is JSON a caller chose: every section is checked, not trusted.

    The reader used to reach into these structures as if the writer had made
    them — `for row in section` on a string, `row.get()` on a null — so a
    handcrafted archive decided whether the restore raised a TypeError halfway
    through, or applied part of itself. Each shape below is refused before the
    first write, and the refusal names the section it is about.
    """

    @pytest.mark.parametrize('mode', ['merge', 'replace'])
    @pytest.mark.parametrize('label', sorted(SHAPES))
    def test_the_service_names_the_section(self, app, tmp_path, label, mode):
        mutate, named = SHAPES[label]
        with _target_for(app, tmp_path, mode):
            blob = _forged([SECTION], mutate=mutate)
            before = _census()

            with pytest.raises(RestoreValidationError) as refusal:
                _service().restore_backup(blob, PASSWORD, mode=mode)
            db.session.rollback()

            assert named in str(refusal.value), (
                f"{label}: the refusal does not name the section: {refusal.value}")
            assert _census() == before, f'{label} moved the instance'

    @pytest.mark.parametrize('label', sorted(SHAPES))
    def test_the_route_refuses_without_a_traceback(self, app, auth_client, label):
        """Whatever the shape, the caller gets an answer and not an incident:
        no stack trace, no driver message, and an instance that did not move.
        """
        mutate, _named = SHAPES[label]
        with app.app_context():
            blob = _forged([SECTION], mutate=mutate)
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400, (label, response.data)

    def test_a_count_that_is_not_a_number_is_refused_by_name(
            self, app, auth_client):
        """The counts are a field of the archive too, and the reader trusts
        them enough to compare a section against them."""
        with app.app_context():
            blob = _forged([SECTION], finalise=_count_as_text)
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400
        message = _message(response)
        assert SECTION in message and 'not a number' in message, message

    def test_a_section_this_version_does_not_know_is_not_a_reason_to_refuse(
            self, app):
        """The shape check is about the sections we apply, not about being
        the newest reader: an archive from a neighbouring version carrying a
        section we know nothing about still restores what we do know."""
        def add_unknown(data):
            data['sections_from_the_future'] = [{'whatever': 1}]

        with app.app_context():
            blob = _forged([SECTION], mutate=add_unknown)
            svc = _service()
            _key, payload = svc._decrypt_framed(blob, PASSWORD)
            plan = RestorePlan.build(payload)
            assert 'sections_from_the_future' not in plan.rows


# ---------------------------------------------------------------------------
# A row nothing can identify
# ---------------------------------------------------------------------------

class TestARowWithoutAnIdentityIsNotAppliedSilently:
    """The manifest's `identity` is what makes a row the same row here.

    A row that carries none cannot be matched to anything on this
    installation, so it is not an update of something. Where the column
    allows a row without a value, the plan says so in a warning naming the
    section and the position, before anything is written. Where the column
    requires one, the row cannot be written at all: saying "it will be
    restored as a new row" was a promise the insert then broke, halfway
    through the transaction, with nothing naming the row that did it.
    """

    @pytest.mark.parametrize('label, row', [
        ('the identity column is absent',
         {key: value for key, value in TARGET.items() if key != 'name'}),
        ('the identity column is empty', dict(TARGET, name='')),
        ('the identity column is null', dict(TARGET, name=None)),
    ])
    def test_a_required_identity_is_refused_before_anything_is_written(
            self, app, label, row):
        with app.app_context():
            before = _census()
            blob = _forged([SECTION], **{SECTION: [row]})
            _key, payload = _service()._decrypt_framed(blob, PASSWORD)

            with pytest.raises(RestoreValidationError) as refused:
                RestorePlan.build(payload)

            position = len(payload[SECTION]) - 1
            message = str(refused.value)
            assert f"row {position} of section '{SECTION}'" in message, label
            assert 'name' in message, label
            assert _census() == before, 'building the plan wrote something'

    def test_a_nullable_identity_is_warned_about_rather_than_refused(self, app):
        """An installation carrying rows older than the column that
        identifies them has to stay restorable: where the column tolerates
        nothing, so does the plan, and it says so."""
        from services.backup.manifest import SECTIONS
        from services.backup.export_generic import load_model
        from sqlalchemy import inspect as sa_inspect

        tolerant = None
        for name, section in SECTIONS.items():
            if section.identity == ('id',):
                continue
            table = sa_inspect(load_model(section)).local_table
            columns = [table.columns.get(field) for field in section.identity]
            if columns and all(c is not None and c.nullable for c in columns):
                tolerant = (name, section)
                break

        if tolerant is None:
            pytest.skip('every identity column of this schema is required')

        name, section = tolerant
        with app.app_context():
            blank = {field: None for field in section.identity}
            blob = _forged([name], **{name: [blank]})
            _key, payload = _service()._decrypt_framed(blob, PASSWORD)

            plan = RestorePlan.build(payload)

        assert any(f"section '{name}'" in warning for warning in plan.warnings)

    def test_it_is_never_matched_onto_an_existing_row(self, app):
        """The other half: an identity nobody carries must not resolve to a
        row here, which would make the archive silently overwrite it."""
        from services.backup.restore.plan import RestorePlan as _Plan

        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [dict(TARGET, name='x')]})
            _key, payload = _service()._decrypt_framed(blob, PASSWORD)
            plan = _Plan.build(payload)

            # A row whose identity names nothing here is a new row, never an
            # update of one that happens to be there.
            assert plan.existing_id(SECTION, dict(TARGET, name='')) is None

    def test_such_an_archive_is_not_announced_as_a_success(
            self, app, auth_client):
        """The refusal reaches the caller as a refusal, naming the section,
        and the instance is untouched."""
        row = {key: value for key, value in TARGET.items() if key != 'name'}
        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [row]})
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert SECTION in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# An archive that carries nothing
# ---------------------------------------------------------------------------

class TestAnArchiveThatCarriesNothing:
    """Empty is a shape too, and it is the one that would empty the instance.

    A replacing restore removes what the archive omits, so "no rows" and "no
    section" must stay two different statements: the first replaces a section
    with nothing, the second says the archive knows nothing about it. An
    archive holding neither must not be read as the first.
    """

    @pytest.mark.parametrize('label, payload, expected', [
        ('no payload at all', b'', 'not valid JSON'),
        ('a list instead of an archive', b'[]', 'not an object'),
        ('null instead of an archive', b'null', 'not an object'),
        ('a number instead of an archive', b'42', 'not an object'),
    ])
    def test_an_empty_payload_is_refused_by_what_it_is(
            self, app, archive, auth_client, label, payload, expected):
        blob = _seal(_header_of(archive), payload)
        with app.app_context():
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400, (label, response.data)
        assert expected in _message(response), (label, _message(response))

    def test_an_archive_of_empty_sections_is_refused_before_it_empties_anything(
            self, app, auth_client):
        """Every section present and every one of them empty: applying it
        would remove every row of every section, the accounts included. The
        refusal names that, and happens inside the transaction that is rolled
        back."""
        svc_blob = None
        with app.app_context():
            svc = _service()
            full = svc.create_backup(PASSWORD)
            _key, payload = svc._decrypt_framed(full, PASSWORD)
            for name, value in list(payload.items()):
                if name in ('metadata', 'checksum'):
                    continue
                payload[name] = {} if isinstance(value, dict) else []
            svc_blob = _reseal(full, payload)
            before = _census()

        response = _restore(auth_client, svc_blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400, response.data
        message = _message(response).lower()
        assert 'no users' in message and 'nothing has been changed' in message, \
            message

    def test_an_archive_with_no_sections_removes_nothing(self, app, archive):
        """The other reading of "empty": a payload that carries metadata and
        no section at all. It describes no section, so it replaces none — the
        day that becomes "every section is empty", this instance is wiped by a
        file of two hundred bytes.
        """
        blob = _seal(_header_of(archive),
                     json.dumps({'metadata': {'version': '1.0'}}).encode())
        with app.app_context():
            before = _census()
            results = _service().restore_backup(blob, PASSWORD)

            assert not results.get('removed'), \
                f'an archive describing no section removed rows: {results}'
            assert _census() == before, 'an empty archive changed the instance'


# ---------------------------------------------------------------------------
# A field holding what no column can take
# ---------------------------------------------------------------------------

class TestExtremeValuesInAField:
    """The payload is bounded as a whole; a single field is the way around it.

    An archive is checked for its total size and for how far it expands, but
    all of that can sit in one column of one row. These pin what happens then:
    a refusal the caller can read, and an instance that did not move.
    """

    def test_a_field_of_several_megabytes_is_refused_by_the_ceiling(
            self, app, auth_client):
        """Four megabytes of one character is a few kilobytes on the wire:
        the ratio ceiling is what sees it, not the file size."""
        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [
                dict(TARGET, name=HOSTILE_PREFIX + 'A' * (4 * 1024 * 1024))]})
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400
        assert 'expands beyond' in _message(response), _message(response)

    def test_an_integer_no_column_can_hold_is_not_a_restore(
            self, app, auth_client):
        """A port of 2**80 is refused by the database rather than by the
        reader, so the answer is the generic one: what this pins is that it is
        an answer, that nothing of it reached the caller, and that the row
        never landed."""
        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [dict(TARGET, port=2 ** 80)]})
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)

    def test_bytes_that_are_not_text_in_a_name_are_refused(
            self, app, auth_client):
        """A name JSON accepts and UTF-8 does not: it cannot be written
        anywhere, and the reader must say so instead of failing while
        writing it."""
        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [
                dict(TARGET, name=HOSTILE_PREFIX + '\udcff\udcfe')]})
            before = _census()

        response = _restore(auth_client, blob)

        with app.app_context():
            after = _census()
        _assert_refused_cleanly(response, before, after)
        assert response.status_code == 400, response.data

    def test_control_characters_in_a_name_are_carried_verbatim(self, app):
        """A restore puts back what the archive holds; it does not clean it.

        The name lands exactly as it was written, bell and terminal escape
        sequence included — the check here is that the reader neither rewrites
        it nor stops on it, so what an administrator sees afterwards is what
        the archive actually carried, and a row is never half-applied because
        of what one of its fields looked like.
        """
        from models.deploy import DeployTarget

        hostile = HOSTILE_PREFIX + 'a\x07b\x1b[31mc\r\n'
        with app.app_context():
            blob = _forged([SECTION], **{SECTION: [dict(TARGET, name=hostile)]})
            before = _census()
            try:
                _service().restore_backup(blob, PASSWORD)

                restored = DeployTarget.query.filter_by(name=hostile).first()
                assert restored is not None, 'the row was dropped in silence'
                assert restored.name == hostile, 'the name was rewritten'
                after = _census()
                assert after['deploy_targets'] == before['deploy_targets'] + 1
                assert {key: value for key, value in after.items()
                        if key != 'deploy_targets'} == {
                    key: value for key, value in before.items()
                    if key != 'deploy_targets'}, 'the restore touched more than its section'
            finally:
                _drop_forged_targets()
