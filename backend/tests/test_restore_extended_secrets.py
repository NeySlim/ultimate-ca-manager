"""What a restore puts back for the sections restore_extended and
restore_policies own.

Both files used to apply a list of columns somebody chose once, and only to
rows they were creating. Three things came of that, and each has a test here:

* an SSH authority, a Microsoft connector, a scan profile, an HSM key, a
  policy or an ACME domain this installation already held was counted as
  restored and left exactly as it was, so a restore produced an instance
  matching neither the archive nor its own previous state;
* `microsoft_cas.winrm_password` was on no list at all -- the credential of
  the administration channel was lost at every restore -- and the other two
  secrets of these sections have to come back where the application reads
  them *and* encrypted in the column, since a restore must not be a way to
  strip at-rest protection;
* the foreign keys were written with the source's own numbers, which name
  nothing here: the link was left for `relink_references` to repair at the
  very end of the restore, which is in time on SQLite (it enforces no foreign
  key) and far too late on PostgreSQL. The references are falsified here,
  beside the identity the archive carries, so a restore that copied the
  number rather than resolving the identity is visible on SQLite too.

The ACME client account keys are the fourth: they are written with the
key-encryption key and were exported through the database-key layer, so the
export decrypted nothing and the archive carried the source's ciphertext. That
one needs two installations with different keys to say anything at all, and
uses the round trip `tests/test_backup_cross_installation.py` already owns.

Everything else runs against the suite's own database, which is shared and has
no rollback between tests: the payloads carry only the rows this file wrote
(`_archived`), the restorers are called the way a restore calls them -- one
plan, one transaction -- and the module puts back what it created, in an order
that leaves nothing pointing at a row that is gone.
"""
import base64
import json
from collections import defaultdict
from datetime import datetime

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.types import Boolean, Date, DateTime, Integer, LargeBinary, Numeric

from models import db
from services.backup import manifest
from services.backup.export_generic import (
    REFERENCE_SUFFIX, IdentityIndex, export_section, load_model)
from services.backup.restore import RestorePlan, single_transaction
from services.backup.restore.plan import RestoreValidationError
# One round trip needs a second installation: its database, and the two keys
# it reads it with. That machinery belongs to the cross-installation file,
# which is where it is exercised for every section.
from tests.test_backup_cross_installation import (
    PASSWORD, Keys, _installation, _only)

MARK = 'restore-ext'

# A primary key no installation here ever hands out: a reference written with
# it is a reference nobody resolved.
SOURCE_ID = 900_001

SEEDED_AT = datetime(2026, 3, 4, 5, 6, 7)
DRIFTED_AT = datetime(2001, 2, 3, 4, 5, 6)

# The sections the two files restore. `acme_local_domains` carries no
# reference and no secret; it is here because its restorer moved too.
SECTIONS_HERE = (
    'acme_client_orders',
    'acme_domains',
    'acme_local_domains',
    'approval_requests',
    'certificate_policies',
    'dns_providers',
    'hsm_keys',
    'microsoft_cas',
    'scan_profiles',
    'ssh_cas',
    'ssh_certificates',
)

# Every secret these sections declare, with the value written on the row.
SECRET_VALUES = {
    ('microsoft_cas', 'password'): f'{MARK}-msca-password',
    ('microsoft_cas', 'winrm_password'): f'{MARK}-winrm-password',
    ('dns_providers', 'credentials'): json.dumps({'api_token': f'{MARK}-dns-token'}),
}


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _section(section_name):
    return manifest.SECTIONS[section_name]


def _model(section_name):
    return load_model(_section(section_name))


def _attribute_of(model, column):
    for prop in sa_inspect(model).column_attrs:
        for stored in prop.columns:
            if stored.key == column:
                return prop.key
    return column


def _has_property(model, column):
    return isinstance(getattr(model, column, None), property)


# ---------------------------------------------------------------------------
# The rows this file writes, and the rows they point at
# ---------------------------------------------------------------------------

# Two of everything a reference points at, and every seeded row points at the
# second: a reference that landed on the first, or on whatever the number
# happened to name, is a reference nobody resolved.
IDENTITIES = {
    'ssh_cas': {'refid': f'{MARK}-sshca-b'},
    'ssh_certificates': {'serial': 4242},
    'microsoft_cas': {'name': f'{MARK}-msca'},
    'scan_profiles': {'name': f'{MARK}-scan'},
    'hsm_keys': {'key_identifier': f'{MARK}-hsm-key'},
    'approval_requests': {'created_at': SEEDED_AT},
    'acme_client_orders': {'order_url': f'https://acme.example.test/{MARK}/order'},
    'certificate_policies': {'name': f'{MARK}-policy'},
    'dns_providers': {'name': f'{MARK}-dns-b'},
    'acme_domains': {'domain': f'{MARK}-domain.example.test'},
    'acme_local_domains': {'domain': f'{MARK}-local.example.test'},
}


def _ssh_key_material():
    """Key material an export can actually decrypt.

    Every SSH authority in this database is read by any backup another file
    of this worker takes, and one whose private key is not usable key
    material aborts that backup rather than this file's test.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from utils.key_codec import store_pem_bytes

    key = ed25519.Ed25519PrivateKey.generate()
    return store_pem_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))


def _seed():
    """One row in every section of the two files, and what they point at."""
    from models import CA, Certificate, User
    from models.acme_client_account import AcmeClientAccount
    from models.acme_models import (
        AcmeClientOrder, AcmeDomain, AcmeLocalDomain, DnsProvider)
    from models.certificate_template import CertificateTemplate
    from models.discovered_certificate import ScanProfile
    from models.group import Group
    from models.hsm import HsmKey, HsmProvider
    from models.msca import MicrosoftCA
    from models.policy import ApprovalRequest, CertificatePolicy
    from models.ssh import SSHCertificate, SSHCertificateAuthority

    def pair(build):
        rows = [build(suffix) for suffix in 'ab']
        for row in rows:
            db.session.add(row)
        db.session.flush()
        return rows

    groups = pair(lambda s: Group(name=f'{MARK}-group-{s}'))
    templates = pair(lambda s: CertificateTemplate(
        name=f'{MARK}-template-{s}', template_type='server',
        extensions_template='{}'))
    users = pair(lambda s: User(
        username=f'{MARK}-user-{s}', email=f'{MARK}-{s}@example.test',
        password_hash='x' * 32, role='operator', active=True))
    authorities = pair(lambda s: CA(
        refid=f'{MARK}-ca-{s}', descr=f'{MARK} CA {s}', crt=''))
    certificates = pair(lambda s: Certificate(
        refid=f'{MARK}-cert-{s}', descr=f'{MARK} certificate {s}',
        caref=f'{MARK}-ca-b'))
    hsm_providers = pair(lambda s: HsmProvider(
        name=f'{MARK}-hsm-{s}', type='openbao', config='{}'))
    dns_providers = pair(lambda s: DnsProvider(
        name=f'{MARK}-dns-{s}', provider_type='cloudflare'))
    ssh_authorities = pair(lambda s: SSHCertificateAuthority(
        refid=f'{MARK}-sshca-{s}', descr=f'{MARK} SSH CA {s}', ca_type='user',
        public_key=f'ssh-ed25519 AAAA {MARK}', private_key=_ssh_key_material(),
        key_type='ed25519', fingerprint=f'SHA256:{MARK}{s}', serial_counter=3))

    dns_providers[1].credentials = SECRET_VALUES[('dns_providers', 'credentials')]

    connector = MicrosoftCA(
        name=IDENTITIES['microsoft_cas']['name'], server='ca.example.test',
        ca_name='Example-CA', auth_method='ntlm', username='ucm',
        winrm_enabled=True, winrm_host='ca.example.test',
        winrm_username='ucm-admin', winrm_transport='ntlm')
    connector.password = SECRET_VALUES[('microsoft_cas', 'password')]
    connector.winrm_password = SECRET_VALUES[('microsoft_cas', 'winrm_password')]
    connector.client_key_pem = f'{MARK}-client-key-pem'
    db.session.add(connector)

    db.session.add(ScanProfile(
        name=IDENTITIES['scan_profiles']['name'], description=f'{MARK} scan',
        targets='["10.0.0.0/30"]', ports='[443, 8443]', timeout=9,
        max_workers=3, resolve_dns=True))

    db.session.add(HsmKey(
        provider_id=hsm_providers[1].id,
        key_identifier=IDENTITIES['hsm_keys']['key_identifier'],
        label=f'{MARK} key', algorithm='rsa', key_type='rsa', purpose='sign',
        public_key_pem=f'{MARK}-public-key', extra_data='{}'))

    db.session.add(CertificatePolicy(
        name=IDENTITIES['certificate_policies']['name'],
        description=f'{MARK} policy', policy_type='issuance',
        ca_id=authorities[1].id, template_id=templates[1].id,
        approval_group_id=groups[1].id, rules='{"max_days": 90}',
        requires_approval=True, min_approvers=2, priority=42))

    db.session.flush()          # the approval below points at the policy
    policy = CertificatePolicy.query.filter_by(
        name=IDENTITIES['certificate_policies']['name']).one()
    db.session.add(ApprovalRequest(
        request_type='certificate', certificate_id=certificates[1].id,
        policy_id=policy.id, requester_id=users[1].id,
        requester_comment=f'{MARK} please', status='pending',
        required_approvals=2, created_at=SEEDED_AT))

    db.session.add(AcmeDomain(
        domain=IDENTITIES['acme_domains']['domain'],
        dns_provider_id=dns_providers[1].id, issuing_ca_id=authorities[1].id,
        is_wildcard_allowed=False, auto_approve=True, created_by=f'{MARK}-user-b'))

    db.session.add(AcmeLocalDomain(
        domain=IDENTITIES['acme_local_domains']['domain'],
        issuing_ca_id=authorities[1].id, auto_approve=True,
        created_by=f'{MARK}-user-b'))

    # The account at the external authority the order was placed with. The
    # order's link to it is a number, so it only proves anything once there is
    # an account here whose own number is not the one the archive carries.
    client_account = AcmeClientAccount(
        directory_url=f'https://acme.example.test/{MARK}/directory',
        label=f'{MARK} client account', email=f'{MARK}-client@example.test',
        account_key_algorithm='ES256')
    db.session.add(client_account)
    db.session.flush()

    db.session.add(AcmeClientOrder(
        order_url=IDENTITIES['acme_client_orders']['order_url'],
        domains=f'["{MARK}-order.example.test"]', challenge_type='dns-01',
        environment='production', key_source='generate', status='valid',
        account_id=f'{MARK}-acme-account', dns_provider_id=dns_providers[1].id,
        acme_client_account_id=client_account.id,
        certificate_id=certificates[1].id,
        source_certificate_id=certificates[0].id,
        finalize_url=f'https://acme.example.test/{MARK}/finalize',
        renewal_enabled=True))

    db.session.add(SSHCertificate(
        refid=f'{MARK}-sshcert', descr=f'{MARK} SSH certificate',
        ssh_ca_id=ssh_authorities[1].id, owner_group_id=groups[1].id,
        cert_type='user', key_id=f'{MARK}-key',
        public_key=f'ssh-ed25519 AAAA {MARK}',
        certificate='ssh-ed25519-cert-v01@openssh.com AAAA',
        principals='["ucm"]', serial=IDENTITIES['ssh_certificates']['serial'],
        valid_from=SEEDED_AT, valid_to=datetime(2027, 3, 4, 5, 6, 7),
        key_type='ed25519', fingerprint=f'SHA256:{MARK}cert', source='web'))

    ssh_authorities[1].owner_group_id = groups[1].id
    db.session.commit()

    return {'groups': groups, 'templates': templates, 'users': users,
            'certificate_authorities': authorities,
            'certificates': certificates, 'hsm_providers': hsm_providers,
            'dns_providers': dns_providers, 'ssh_cas': ssh_authorities}


def _unseed():
    """Take back every row, child first: nothing may be left pointing at a
    row that is gone, on a database the whole worker goes on using."""
    from models import CA, Certificate, User
    from models.acme_client_account import AcmeClientAccount
    from models.acme_models import (
        AcmeClientOrder, AcmeDomain, AcmeLocalDomain, DnsProvider)
    from models.certificate_template import CertificateTemplate
    from models.discovered_certificate import ScanProfile
    from models.group import Group
    from models.hsm import HsmKey, HsmProvider
    from models.msca import MicrosoftCA
    from models.policy import ApprovalRequest, CertificatePolicy
    from models.ssh import SSHCertificate, SSHCertificateAuthority

    SSHCertificate.query.filter(
        SSHCertificate.refid.like(f'{MARK}%')).delete(synchronize_session=False)
    SSHCertificateAuthority.query.filter(
        SSHCertificateAuthority.refid.like(f'{MARK}%')).delete(
            synchronize_session=False)
    # The order and the account carry the marker inside a URL rather than at
    # the front of one, so a `{MARK}%` pattern matched neither: both survived
    # the module, and the order went on pointing at an ACME account that is
    # not there. A whole-database foreign key check three files later is
    # where that surfaced.
    AcmeClientOrder.query.filter(
        AcmeClientOrder.order_url.like(f'%{MARK}%')).delete(
            synchronize_session=False)
    AcmeClientAccount.query.filter(
        AcmeClientAccount.label.like(f'{MARK}%')).delete(
            synchronize_session=False)
    for model, column in (
            (ApprovalRequest, ApprovalRequest.requester_comment),
            (AcmeDomain, AcmeDomain.domain),
            (AcmeLocalDomain, AcmeLocalDomain.domain),
            (HsmKey, HsmKey.key_identifier),
            # The provider comes after its keys, and it was not on this list
            # at all: two HSM providers stayed behind on the worker's database
            # for every file that ran after this one.
            (HsmProvider, HsmProvider.name),
            (CertificatePolicy, CertificatePolicy.name),
            (DnsProvider, DnsProvider.name),
            (MicrosoftCA, MicrosoftCA.name),
            (ScanProfile, ScanProfile.name),
            (Certificate, Certificate.refid),
            (CA, CA.refid),
            (CertificateTemplate, CertificateTemplate.name),
            (Group, Group.name),
            (User, User.username)):
        model.query.filter(column.like(f'{MARK}%')).delete(
            synchronize_session=False)
    db.session.commit()


@pytest.fixture(scope='module')
def seeded(app):
    with app.app_context():
        _unseed()
        made = _seed()
        yield {'ids': {name: [row.id for row in rows]
                       for name, rows in made.items()}}
        _unseed()


# ---------------------------------------------------------------------------
# The archive, and applying it the way a restore does
# ---------------------------------------------------------------------------


def _archived(section_name):
    """The rows an archive carries for this section, this file's only.

    Read through the exporter a backup uses and round-tripped through JSON,
    which is what a restore is handed: a datetime is an ISO string there, and
    a column that only survives as a `datetime` object would pass a test it
    should not.
    """
    identity = IDENTITIES[section_name]
    rows = [row for row in export_section(section_name, IdentityIndex())
            if all(row.get(field) == _serialised(value)
                   for field, value in identity.items())]
    assert len(rows) == 1, (
        f"this file writes exactly one {section_name} row and the archive "
        f"carries {len(rows)}")
    return json.loads(json.dumps(rows, default=str))


def _serialised(value):
    """An identity value as the archive spells it: a date is text there."""
    return value.isoformat() if isinstance(value, datetime) else value


def _restore(payload, *section_names):
    """Apply a payload as a restore does: one plan, one transaction."""
    service = _service()
    plan = RestorePlan.build(payload)
    results = defaultdict(int)
    calls = {
        'ssh_cas': lambda: service._restore_ssh_cas(payload, results, b'', plan),
        'ssh_certificates': lambda: service._restore_ssh_certificates(
            payload, results, plan),
        'microsoft_cas': lambda: service._restore_microsoft_cas(
            payload, results, plan),
        'scan_profiles': lambda: service._restore_scan_profiles(
            payload, results, plan),
        'hsm_keys': lambda: service._restore_hsm_keys(payload, results, plan),
        'approval_requests': lambda: service._restore_approval_requests(
            payload, results, plan),
        'acme_client_orders': lambda: service._restore_acme_client_orders(
            payload, results, plan),
        'certificate_policies': lambda: service._restore_policies(
            payload, results, plan),
        'dns_providers': lambda: service._restore_dns_providers(
            payload, results, plan),
        'acme_domains': lambda: service._restore_acme_domains(
            payload, results, plan),
        'acme_local_domains': lambda: service._restore_acme_local_domains(
            payload, results, plan),
    }
    with single_transaction():
        for name in section_names:
            calls[name]()
    db.session.commit()
    return results


def _row(section_name):
    """The row this file wrote, as the database holds it now."""
    model = _model(section_name)
    identity = IDENTITIES[section_name]
    found = model.query.filter_by(**identity).all()
    assert len(found) == 1, (
        f"{section_name} {identity} matches {len(found)} rows here: the "
        "restore wrote a second one instead of the one it was given")
    return found[0]


def _as_column_value(model, column, value):
    """An archived value, back in the shape its column holds it."""
    stored = sa_inspect(model).columns.get(column)
    if stored is None or value is None:
        return value
    kind = stored.type
    if isinstance(kind, LargeBinary) and isinstance(value, str):
        return base64.b64decode(value)
    if isinstance(kind, (DateTime, Date)) and isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed if isinstance(kind, DateTime) else parsed.date()
    if isinstance(kind, Boolean) and not isinstance(value, bool):
        return bool(value)
    if isinstance(kind, (Integer, Numeric)) and isinstance(value, str):
        return int(value) if isinstance(kind, Integer) else float(value)
    return value


def _value_here(row, section, column):
    """What this installation reads for that column.

    A secret is read where the application reads it -- through the property
    that decrypts, when the model has one -- and everything else through the
    column itself.
    """
    model = type(row)
    if column in section.secrets and _has_property(model, column):
        return getattr(row, column)
    return getattr(row, _attribute_of(model, column))


def _carried_columns(section_name):
    """The columns of the section a restore is answerable for."""
    section = _section(section_name)
    return [column.key for column in sa_inspect(_model(section_name)).columns
            if column.key != 'id'
            and column.key not in section.exclude
            and column.key not in section.handled]


def _drift(section_name):
    """Change every column of the row that is not what identifies it.

    The drift is what a restore is for: an operator, or an incident, moved
    the instance away from the archive between the backup and the restore.
    The identity is left alone so the restore still has a row to recognise --
    what it does with the rest is the question being asked.
    """
    section = _section(section_name)
    row = _row(section_name)
    model = type(row)
    for column in sa_inspect(model).columns:
        name = column.key
        if (column.primary_key or name in section.identity
                or name in section.handled or name in section.exclude):
            continue
        attribute = _attribute_of(model, name)
        setattr(row, attribute, _drifted(column, getattr(row, attribute)))
    db.session.commit()


def _drifted(column, current):
    kind = column.type
    if isinstance(kind, Boolean):
        return not bool(current)
    if isinstance(kind, (DateTime, Date)):
        return DRIFTED_AT.date() if isinstance(kind, Date) and not isinstance(kind, DateTime) else DRIFTED_AT
    if isinstance(kind, Integer):
        return (current or 0) + 7
    if isinstance(kind, Numeric):
        return float(current or 0) + 7
    if isinstance(kind, LargeBinary):
        return b'drifted'
    return f'drifted-{column.key}'


# ---------------------------------------------------------------------------
# Every column the archive carries
# ---------------------------------------------------------------------------


class TestARowAlreadyHereGoesBackToTheArchive:
    """The restorers wrote a hand-picked list of columns onto rows they were
    creating, and nothing at all onto a row they found: the section was
    counted as restored and left as it was."""

    @pytest.mark.parametrize('section_name', SECTIONS_HERE)
    def test_every_column_the_manifest_carries_is_restored(
            self, app, seeded, section_name):
        with app.app_context():
            archived = _archived(section_name)[0]
            _drift(section_name)
            _restore({section_name: [archived]}, section_name)

            section = _section(section_name)
            row = _row(section_name)
            model = type(row)
            wrong = []
            for column in _carried_columns(section_name):
                expected = archived[column]
                if column not in section.secrets:
                    expected = _as_column_value(model, column, expected)
                found = _value_here(row, section, column)
                if found != expected:
                    wrong.append(f'{column}: {found!r} instead of {expected!r}')
            assert not wrong, (
                f"'{section_name}' did not come back as the archive holds "
                "it:\n  " + '\n  '.join(wrong))

    @pytest.mark.parametrize('section_name', SECTIONS_HERE)
    def test_the_row_keeps_its_own_primary_key(self, app, seeded, section_name):
        """The one column a restore must not carry over: everything else on
        this installation already points at it.

        The archive does not carry `id` -- every section excludes it -- so the
        row handed to the restore is given one the target never issued, which
        is what an archive written by a version that did carry the column
        looks like, and what a hand-written restorer copying the payload
        wholesale would write.
        """
        with app.app_context():
            archived = dict(_archived(section_name)[0], id=SOURCE_ID)
            before = _row(section_name).id
            assert before != SOURCE_ID, 'the test would prove nothing'
            _restore({section_name: [archived]}, section_name)

            row = _row(section_name)
            assert row.id == before, (
                f'{section_name} was renumbered to {row.id}: everything on '
                'this installation that points at it now points at nothing')


class TestTheSecretsOfTheseSectionsComeBackWhereTheyAreRead:
    """`winrm_password` was restored by nobody, and a secret written to the
    column underneath the property comes back readable in the database."""

    @pytest.mark.parametrize('section_name, column', sorted(SECRET_VALUES))
    def test_the_value_is_the_archive_s_and_not_the_one_that_was_here(
            self, app, seeded, section_name, column):
        with app.app_context():
            archived = _archived(section_name)[0]
            assert archived[column] == SECRET_VALUES[(section_name, column)], (
                'the archive must carry the secret in the clear: that is what '
                'makes it readable on an installation with another key')

            _drift(section_name)
            row = _row(section_name)
            assert _value_here(row, _section(section_name), column) != \
                SECRET_VALUES[(section_name, column)], 'the drift did nothing'

            _restore({section_name: [archived]}, section_name)
            row = _row(section_name)
            assert _value_here(row, _section(section_name), column) == \
                SECRET_VALUES[(section_name, column)]

    @pytest.mark.parametrize('section_name, column', sorted(SECRET_VALUES))
    def test_the_column_underneath_holds_it_encrypted(
            self, app, seeded, section_name, column):
        """A restore must not be a way to strip at-rest encryption: where the
        model has a property that encrypts, the column may not hold the
        secret in the clear once the restore has been through it."""
        from utils.encryption import is_encrypted

        with app.app_context():
            model = _model(section_name)
            assert _has_property(model, column), (
                f'{section_name}.{column} is expected to encrypt on assignment')

            archived = _archived(section_name)[0]
            _drift(section_name)
            _restore({section_name: [archived]}, section_name)

            stored = getattr(_row(section_name), _attribute_of(model, column))
            assert stored != SECRET_VALUES[(section_name, column)], \
                'the secret came back readable in the column'
            assert is_encrypted(stored), \
                'the secret is in the column but not under this database key'


class TestAConnectorKeepsTheCredentialOfItsAdministrationChannel:
    def test_the_winrm_password_survives_a_restore_that_replaces_the_row(
            self, app, seeded):
        """It was on no list: the connector came back, the WinRM channel it
        answers on did not, and nothing said so until someone used it."""
        from models.msca import MicrosoftCA

        with app.app_context():
            archived = _archived('microsoft_cas')[0]
            MicrosoftCA.query.filter_by(name=archived['name']).delete()
            db.session.commit()

            _restore({'microsoft_cas': [archived]}, 'microsoft_cas')

            back = _row('microsoft_cas')
            assert back.winrm_password == \
                SECRET_VALUES[('microsoft_cas', 'winrm_password')]
            assert back.winrm_username == 'ucm-admin'
            assert back.winrm_transport == 'ntlm'

    def test_a_client_key_that_travelled_in_the_clear_is_encrypted_here(
            self, app, seeded):
        """`client_key_pem` is the third column of this model behind an
        encrypting property, and the manifest declares it a secret, so the
        archive carries it in the clear like the two passwords beside it: an
        archive is readable on a server whose key is not the source's, which
        is the point of decrypting on the way out. What must not happen is the
        value staying that way here, on an installation that does encrypt.
        """
        from utils.encryption import is_encrypted

        plain = ('-----BEGIN PRIVATE KEY-----\n'
                 f'{MARK}-client-key-in-the-clear\n'
                 '-----END PRIVATE KEY-----\n')
        with app.app_context():
            archived = dict(_archived('microsoft_cas')[0], client_key_pem=plain)
            _restore({'microsoft_cas': [archived]}, 'microsoft_cas')

            back = _row('microsoft_cas')
            assert back.client_key_pem == plain, \
                'the key the archive carries is not what the connector reads'
            assert is_encrypted(back._client_key_pem), \
                'the private key was restored readable in the column'


# ---------------------------------------------------------------------------
# The references, on the backend that never complains about them
# ---------------------------------------------------------------------------

REFERENCES_HERE = sorted(
    (name, column) for name in SECTIONS_HERE
    for column in _section(name).references)


class TestAReferenceLandsOnTheRowTheArchiveNames:
    """The number in the archive is the source's. SQLite takes it without a
    word and `relink_references` repairs it at the end of the restore, so the
    only way to see it here is to falsify the number and watch where the row
    ends up -- which is what PostgreSQL refuses outright, mid-restore."""

    @pytest.mark.parametrize('section_name, column', REFERENCES_HERE)
    def test_the_source_s_number_is_not_what_is_written(
            self, app, seeded, section_name, column):
        with app.app_context():
            archived = _archived(section_name)[0]
            here = archived[column]
            assert here is not None, (
                f'the seeded {section_name} row must carry {column}')
            assert archived.get(f'{column}{REFERENCE_SUFFIX}'), (
                'the export must write the identity of the row beside the '
                'number, or nothing can be resolved')

            # The same row, as an installation that numbered it differently
            # would have written it.
            archived[column] = SOURCE_ID
            _restore({section_name: [archived]}, section_name)

            row = _row(section_name)
            landed = getattr(row, _attribute_of(type(row), column))
            assert landed != SOURCE_ID, (
                f'{section_name}.{column} kept the number the archive carried')
            assert landed == here, (
                f'{section_name}.{column} points at {landed!r}; the row the '
                f'archive names is {here!r} here')


class TestAReferenceThisInstallationCannotPlace:
    """What must not happen when the row a link names is not here.

    Writing the number the archive carries is the defect this whole lot
    closes: it is the source's, and it names whatever row holds it here. The
    link is dropped instead, and the column keeps nothing rather than
    something wrong. Where the column cannot be empty the archive is refused
    outright, before anything is written, which the sibling below checks.
    """

    def test_a_link_that_finds_nothing_is_dropped_and_not_guessed(
            self, app, seeded):
        from models.acme_models import AcmeClientOrder

        with app.app_context():
            archived = _archived('acme_client_orders')[0]
            assert archived['certificate_id'] is not None
            archived['certificate_id'] = SOURCE_ID
            archived[f'certificate_id{REFERENCE_SUFFIX}'] = {
                'refid': f'{MARK}-a-certificate-that-is-not-here'}

            _restore({'acme_client_orders': [archived]}, 'acme_client_orders')

            order = AcmeClientOrder.query.filter_by(
                order_url=IDENTITIES['acme_client_orders']['order_url']).one()
            assert order.certificate_id is None, (
                'the order was attached to whatever certificate holds '
                f'{order.certificate_id!r} here, which the archive never named')

    def test_a_link_the_row_cannot_be_written_without_refuses_the_archive(
            self, app, seeded):
        from models.acme_models import AcmeLocalDomain

        with app.app_context():
            archived = _archived('acme_local_domains')[0]
            archived['issuing_ca_id'] = SOURCE_ID
            archived[f'issuing_ca_id{REFERENCE_SUFFIX}'] = {
                'refid': f'{MARK}-an-authority-that-is-not-here'}

            before = AcmeLocalDomain.query.filter_by(
                domain=IDENTITIES['acme_local_domains']['domain']).one()
            previous = before.issuing_ca_id

            with pytest.raises(RestoreValidationError) as refusal:
                _restore({'acme_local_domains': [archived]},
                         'acme_local_domains')
            assert 'issuing_ca_id' in str(refusal.value)
            assert 'certificate_authorities' in str(refusal.value)

            db.session.rollback()
            still = AcmeLocalDomain.query.filter_by(
                domain=IDENTITIES['acme_local_domains']['domain']).one()
            assert still.issuing_ca_id == previous, (
                'the refusal left the zone pointing somewhere else')


class TestARowTheRestoreCreatesFindsWhatTheSameRestoreCreated:
    def test_an_ssh_certificate_finds_an_authority_restored_beside_it(
            self, app, seeded):
        """The plan indexes the installation as it was before the first
        write. An SSH certificate points at an authority the same restore is
        putting back, so the first pass resolved nothing: the restore wrote
        the source's number into a NOT NULL foreign key and left the repair to
        the end -- and on PostgreSQL there was no end to get to."""
        from models.ssh import SSHCertificate, SSHCertificateAuthority

        with app.app_context():
            payload = {'ssh_cas': _archived('ssh_cas'),
                       'ssh_certificates': _archived('ssh_certificates')}
            payload['ssh_certificates'][0]['ssh_ca_id'] = SOURCE_ID

            refid = payload['ssh_cas'][0]['refid']
            serial = payload['ssh_certificates'][0]['serial']
            SSHCertificate.query.filter_by(serial=serial).delete()
            SSHCertificateAuthority.query.filter_by(refid=refid).delete()
            db.session.commit()

            _restore(payload, 'ssh_cas', 'ssh_certificates')

            authority = SSHCertificateAuthority.query.filter_by(refid=refid).one()
            certificate = SSHCertificate.query.filter_by(serial=serial).one()
            assert certificate.ssh_ca_id == authority.id, (
                'the certificate was attached to whatever held the number the '
                'archive carried')


class TestAnOlderArchiveKeepsItsSshPrincipalPolicy:
    """Before allow_any_principal, an SSH CA without a list signed for anyone:
    an archive from then restores that as the explicit setting."""

    @pytest.mark.parametrize('principals,carried,expected', [
        (None, None, True),
        ('["deploy"]', None, False),
        (None, False, False),
    ])
    def test_the_setting_follows_the_archive_s_age(
            self, app, seeded, principals, carried, expected):
        with app.app_context():
            payload = {'ssh_cas': _archived('ssh_cas')}
            row = payload['ssh_cas'][0]
            row['allowed_principals'] = principals
            row.pop('allow_any_principal', None)
            if carried is not None:
                row['allow_any_principal'] = carried
            _restore(payload, 'ssh_cas')
            assert _row('ssh_cas').allow_any_principal is expected


# ---------------------------------------------------------------------------
# The ACME client account keys, on an installation with other keys
# ---------------------------------------------------------------------------


class TestAnAcmeClientAccountTravelsToAnotherInstallation:
    """Both secrets of an ACME client account are written with the
    key-encryption key (`security.encryption.encrypt_text`) and were exported
    through the database-key layer, which does not recognise them: the export
    decrypted nothing, the archive carried the source's own ciphertext, and
    the target restored an account key and an EAB secret that only the machine
    the backup came from could open.
    """

    ACCOUNT_KEY = ('-----BEGIN PRIVATE KEY-----\n'
                   f'{MARK}-acme-account-key\n'
                   '-----END PRIVATE KEY-----\n')
    EAB_KEY = f'{MARK}-eab-hmac-key'
    EMAIL = f'{MARK}-acme@example.test'
    DIRECTORY = 'https://acme.example.test/directory'

    def _archive_taken_on_the_source(self, app, tmp_path, keys):
        from models.acme_client_account import AcmeClientAccount
        from security.encryption import encrypt_text

        with _installation(app, f"sqlite:///{tmp_path / 'acme-source.db'}",
                           keys), app.app_context():
            account = AcmeClientAccount(
                directory_url=self.DIRECTORY, label=f'{MARK} account',
                email=self.EMAIL, account_key=encrypt_text(self.ACCOUNT_KEY),
                account_key_algorithm='ES256', eab_kid=f'{MARK}-kid')
            account.eab_hmac_key = self.EAB_KEY
            db.session.add(account)
            db.session.commit()

            stored = (account.account_key, account._eab_hmac_key)
            assert stored[0] != self.ACCOUNT_KEY and stored[1] != self.EAB_KEY, \
                'the source is expected to hold both secrets encrypted'

            blob = _service().create_backup(
                PASSWORD, include=_only('acme_client_accounts'))
            _master, payload = _service()._decrypt_framed(blob, PASSWORD)
        return blob, payload, stored

    def test_the_archive_carries_the_keys_in_the_clear(self, app, tmp_path):
        keys = Keys(tmp_path, 'acme-source')
        _blob, payload, _stored = self._archive_taken_on_the_source(
            app, tmp_path, keys)

        row = next(row for row in payload['acme_client_accounts']
                   if row['email'] == self.EMAIL)
        assert row['account_key'] == self.ACCOUNT_KEY, (
            "the archive carries the source's ciphertext: nothing on another "
            'installation can open it')
        assert row['eab_hmac_key'] == self.EAB_KEY

    def test_the_target_reads_both_keys_with_a_key_the_source_never_had(
            self, app, tmp_path):
        from models.acme_client_account import AcmeClientAccount
        from security.encryption import decrypt_text

        source_keys = Keys(tmp_path, 'acme-source')
        blob, _payload, stored = self._archive_taken_on_the_source(
            app, tmp_path, source_keys)

        target_keys = Keys(tmp_path, 'acme-target')
        with _installation(app, f"sqlite:///{tmp_path / 'acme-target.db'}",
                           target_keys), app.app_context():
            _service().restore_backup(blob, PASSWORD)

            back = AcmeClientAccount.query.filter_by(email=self.EMAIL).one()
            # `account_key` is read straight from the column, through a
            # `decrypt_text` that passes plaintext through; `eab_hmac_key` is
            # read through the property, which decrypts with this
            # installation's key.
            assert decrypt_text(back.account_key) == self.ACCOUNT_KEY
            assert back.eab_hmac_key == self.EAB_KEY
            assert (back.account_key, back._eab_hmac_key) != stored, (
                "the target holds the bytes the source stored: they open with "
                "no key this installation has")
