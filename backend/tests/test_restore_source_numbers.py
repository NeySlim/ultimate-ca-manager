"""A source row number is never taken for someone else's row.

Sections identified by what they point at carry the source's numbers. The
restore looked them up first, so a membership of another user, a binding of
another target, a pin of another template could be the row an archived one
was applied over. A number now counts only for an archive of this database,
and only when it still names the row the archive identifies.
"""
import pytest

from models import db
from services.backup import installation
from services.backup.export_generic import REFERENCE_SUFFIX as REF
from services.backup.restore.plan import RestorePlan
from services.backup.restore.replace import rows_to_remove
from tests.test_backup_cross_installation import (
    Keys, _authority, _installation, _stored_certificate, _stored_key,
)


@pytest.fixture
def here(app, tmp_path):
    with _installation(app, f"sqlite:///{tmp_path / 'here.db'}", Keys(tmp_path, 'numbers')), \
            app.app_context():
        yield
        db.session.rollback()


def _add(row):
    db.session.add(row)
    db.session.flush()
    return row


def _authority_row(refid):
    from models import CA
    key, certificate = _authority(refid)
    return _add(CA(refid=refid, descr=refid, crt=_stored_certificate(certificate),
                   prv=_stored_key(key)))


def _target(name):
    from models.deploy import DeployTarget
    return _add(DeployTarget(name=name, host='deploy.example.test', port=22,
                             username='deploy', private_key='k'))


def _scenario(section_name):
    """(the row here, its identity references, the other row an archived one names)."""
    from models import Certificate, User
    from models.ca_template_pin import CATemplatePin
    from models.certificate_template import CertificateTemplate
    from models.deploy import CRLDeployBinding, DeployBinding
    from models.group import Group, GroupMember
    from models.rbac import CustomRole, RolePermission

    if section_name == 'group_members':
        group = _add(Group(name='numbers-group'))
        alice = _add(User(username='numbers-alice', email='a@example.test',
                          password_hash='x' * 32, role='viewer'))
        _add(User(username='numbers-bob', email='b@example.test',
                  password_hash='x' * 32, role='viewer'))
        row = _add(GroupMember(group_id=group.id, user_id=alice.id))
        return row, {'group_id': (group.id, {'name': 'numbers-group'}),
                     'user_id': (alice.id, {'username': 'numbers-alice'})}, \
            ('user_id', {'username': 'numbers-bob'})
    if section_name == 'deploy_bindings':
        mine, _theirs = _target('numbers-mine'), _target('numbers-theirs')
        certificate = _add(Certificate(refid='numbers-cert', descr='numbers-cert'))
        row = _add(DeployBinding(target_id=mine.id, certificate_id=certificate.id))
        return row, {'target_id': (mine.id, {'name': 'numbers-mine'}),
                     'certificate_id': (certificate.id, {'refid': 'numbers-cert'})}, \
            ('target_id', {'name': 'numbers-theirs'})
    if section_name == 'crl_deploy_bindings':
        mine, _theirs = _target('numbers-mine'), _target('numbers-theirs')
        ca = _authority_row('numbers-ca')
        row = _add(CRLDeployBinding(target_id=mine.id, ca_id=ca.id, crl_path='/crl.pem'))
        return row, {'target_id': (mine.id, {'name': 'numbers-mine'}),
                     'ca_id': (ca.id, {'refid': 'numbers-ca'})}, \
            ('target_id', {'name': 'numbers-theirs'})
    if section_name == 'ca_template_pins':
        ca = _authority_row('numbers-ca')
        mine = _add(CertificateTemplate(name='numbers-mine', template_type='custom',
                                        extensions_template='{}'))
        _add(CertificateTemplate(name='numbers-theirs', template_type='custom',
                                 extensions_template='{}'))
        row = _add(CATemplatePin(ca_id=ca.id, template_id=mine.id))
        return row, {'ca_id': (ca.id, {'refid': 'numbers-ca'}),
                     'template_id': (mine.id, {'name': 'numbers-mine'})}, \
            ('template_id', {'name': 'numbers-theirs'})
    if section_name == 'role_permissions':
        mine = _add(CustomRole(name='numbers-mine'))
        _add(CustomRole(name='numbers-theirs'))
        row = _add(RolePermission(role_id=mine.id, permission='read:certificates'))
        return row, {'role_id': (mine.id, {'name': 'numbers-mine'}),
                     'permission': ('read:certificates', None)}, \
            ('role_id', {'name': 'numbers-theirs'})
    raise AssertionError(section_name)


def _archived(fields, swap=None):
    """An archived row with this installation's numbers; `swap` names another row."""
    row = {}
    for name, (value, identity) in fields.items():
        row[name] = value
        if identity is not None:
            row[f'{name}{REF}'] = identity
    if swap is not None:
        row[f'{swap[0]}{REF}'] = swap[1]
    return row


def _plan(section_name, row, same_installation):
    metadata = {}
    if same_installation:
        metadata[installation.METADATA_KEY] = installation.installation_id(create=True)
    plan = RestorePlan.build({'metadata': metadata, section_name: [row]})
    assert plan.same_installation is same_installation
    return plan


SECTIONS = ['group_members', 'deploy_bindings', 'crl_deploy_bindings',
            'ca_template_pins', 'role_permissions']


@pytest.mark.parametrize('same_installation', [False, True])
@pytest.mark.parametrize('section_name', SECTIONS)
def test_a_number_naming_another_row_is_not_that_row(here, section_name, same_installation):
    row_here, fields, other = _scenario(section_name)
    db.session.commit()
    archived = _archived(fields, swap=other)

    plan = _plan(section_name, archived, same_installation)

    assert plan.existing_id(section_name, archived) is None
    assert row_here.id in rows_to_remove(section_name, [archived], plan)


@pytest.mark.parametrize('section_name', SECTIONS)
def test_the_same_row_is_still_found_by_what_it_names(here, section_name):
    row_here, fields, _other = _scenario(section_name)
    db.session.commit()
    archived = _archived(fields)
    # Numbers of another database, which mean nothing here
    for name in list(archived):
        if isinstance(archived[name], int):
            archived[name] += 1000

    plan = _plan(section_name, archived, False)

    assert plan.existing_id(section_name, archived) == row_here.id
    assert row_here.id not in rows_to_remove(section_name, [archived], plan)


def test_an_archive_says_which_database_it_comes_from(here):
    from services.backup_service import BackupService
    from tests.test_backup_cross_installation import PASSWORD
    from models import User

    _add(User(username='numbers-admin', email='n@example.test', password_hash='x' * 32,
              role='admin'))
    db.session.commit()
    service = BackupService()
    _key, data = service._decrypt_framed(service.create_backup(PASSWORD), PASSWORD)

    assert data['metadata'][installation.METADATA_KEY] == installation.installation_id()
    assert installation.CONFIG_KEY not in data['configuration']['settings']
    assert installation.same_installation(data)
    data['metadata'][installation.METADATA_KEY] = 'another-database'
    assert not installation.same_installation(data)
