"""An archive written before a column existed implies the value its version
had, not today's default: deployment full chains carried the root before 089."""
from services.backup.restore.apply import legacy_defaults

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def test_a_binding_without_the_column_keeps_its_root():
    assert legacy_defaults('deploy_bindings', {'fullchain_path': '/etc/ssl/fc.pem'}) == {'include_root': True}


def test_a_binding_that_names_the_column_is_left_alone():
    assert legacy_defaults('deploy_bindings', {'include_root': False}) == {}


def test_other_sections_have_nothing_implied():
    assert legacy_defaults('users', {}) == {}


def test_a_pre_089_binding_comes_back_with_its_root(app, auth_client, create_cert):
    """A real archive of this server, with the column forgotten as an older version would."""
    from models import db, DeployBinding
    from models.deploy import DeployTarget
    from security.encryption import encrypt_text
    from tests.test_backup_hostile_corpus import _forged, _restore
    cert = create_cert()
    with app.app_context():
        target = DeployTarget(name='legacy-target', host='legacy.example.test',
                              username='deploy', private_key=encrypt_text('k'))
        db.session.add(target)
        db.session.flush()
        db.session.add(DeployBinding(target_id=target.id, certificate_id=cert['id'],
                                     fullchain_path='/etc/ssl/fc.pem', include_root=False))
        db.session.commit()

        def forget_the_column(data):
            for row in data['deploy_bindings']:
                del row['include_root']
        blob = _forged(('certificate_authorities', 'certificates', 'deploy_targets', 'deploy_bindings'),
                       mutate=forget_the_column)
    assert _restore(auth_client, blob).status_code == 200
    with app.app_context():
        assert DeployBinding.query.filter_by(certificate_id=cert['id']).one().include_root is True


def test_a_pre_091_binding_inherits_its_archived_target_reload_command(
        app, auth_client, create_cert):
    """Migration 091 cannot touch binding rows inserted later by restore."""
    from models import db, DeployBinding
    from models.deploy import DeployTarget
    from security.encryption import encrypt_text
    from tests.test_backup_hostile_corpus import _forged, _restore
    cert = create_cert()
    with app.app_context():
        target = DeployTarget(
            name='legacy-reload-target', host='legacy-reload.example.test',
            username='deploy', private_key=encrypt_text('k'),
            reload_command='systemctl reload nginx')
        db.session.add(target)
        db.session.flush()
        db.session.add(DeployBinding(
            target_id=target.id, certificate_id=cert['id'],
            cert_path='/etc/ssl/cert.pem', reload_command=None))
        db.session.commit()

        def forget_binding_command(data):
            for row in data['deploy_bindings']:
                del row['reload_command']

        blob = _forged(
            ('certificate_authorities', 'certificates', 'deploy_targets',
             'deploy_bindings'), mutate=forget_binding_command)
    assert _restore(auth_client, blob).status_code == 200
    with app.app_context():
        restored = DeployBinding.query.filter_by(certificate_id=cert['id']).one()
        assert restored.reload_command == 'systemctl reload nginx'


def test_a_pre_092_intune_profile_gets_a_shared_app_registration(app, auth_client, create_ca):
    """An archive from before 092 carries the Entra credentials on the profile."""
    from models import db
    from models.scep import IntuneApp, ScepProfile
    from services.backup.export_generic import REFERENCE_SUFFIX
    from tests.test_backup_hostile_corpus import _forged, _restore
    from utils.encryption import is_encrypted
    ca = create_ca(cn='Legacy Intune Archive CA')
    with app.app_context():
        registration = IntuneApp(name='legacy-092-app', tenant_id='restore092.onmicrosoft.com',
                                 client_id='restore092-client', client_secret='x')
        db.session.add(registration)
        db.session.flush()
        ca_refid = db.session.get(__import__('models').CA, ca['id']).refid
        profile = ScepProfile(name='legacy-092-profile', url_slug='legacy-092-profile',
                              ca_refid=ca_refid, auto_approve=True, intune_enabled=True,
                              intune_app_id=registration.id)
        db.session.add(profile)
        db.session.commit()

        def as_written_before_092(data):
            data.pop('intune_apps', None)
            for row in data['scep_profiles']:
                if row['name'] != 'legacy-092-profile':
                    continue
                row.pop('intune_app_id', None)
                row.pop(f'intune_app_id{REFERENCE_SUFFIX}', None)
                row.update(intune_tenant_id='restore092.onmicrosoft.com',
                           intune_client_id='restore092-client',
                           intune_client_secret='legacy-clear-secret')
        blob = _forged(('certificate_authorities', 'intune_apps', 'scep_profiles'),
                       mutate=as_written_before_092)
        ScepProfile.query.filter_by(name='legacy-092-profile').delete()
        IntuneApp.query.filter_by(name='legacy-092-app').delete()
        db.session.commit()

    r = _restore(auth_client, blob)
    assert r.status_code == 200, r.data
    with app.app_context():
        profile = ScepProfile.query.filter_by(name='legacy-092-profile').one()
        registration = profile.intune_app
        assert registration is not None
        assert (registration.tenant_id, registration.client_id) == ('restore092.onmicrosoft.com', 'restore092-client')
        assert is_encrypted(registration.client_secret)
        assert registration.decrypted_secret() == 'legacy-clear-secret'
        assert (profile.intune_tenant_id, profile.intune_client_id,
                profile.intune_client_secret) == (None, None, None)


def test_pre_092_profiles_on_different_secrets_get_separate_apps(app, auth_client, create_ca):
    """Two profiles of one tenant, one on the old secret and one on the new:
    both keep enrolling after the restore."""
    from models import db
    from models.scep import IntuneApp, ScepProfile
    from services.backup.export_generic import REFERENCE_SUFFIX
    from tests.test_backup_hostile_corpus import _forged, _restore
    ca = create_ca(cn='Legacy Intune Two Secrets CA')
    secrets = {'legacy-two-a': 'old-secret', 'legacy-two-b': 'new-secret'}
    with app.app_context():
        registration = IntuneApp(name='legacy-two-app', tenant_id='two.onmicrosoft.com',
                                 client_id='two-client', client_secret='x')
        db.session.add(registration)
        db.session.flush()
        ca_refid = db.session.get(__import__('models').CA, ca['id']).refid
        for name in secrets:
            db.session.add(ScepProfile(name=name, url_slug=name, ca_refid=ca_refid,
                                       auto_approve=True, intune_enabled=True,
                                       intune_app_id=registration.id))
        db.session.commit()

        def as_written_before_092(data):
            data.pop('intune_apps', None)
            for row in data['scep_profiles']:
                if row['name'] not in secrets:
                    continue
                row.pop('intune_app_id', None)
                row.pop(f'intune_app_id{REFERENCE_SUFFIX}', None)
                row.update(intune_tenant_id='two.onmicrosoft.com', intune_client_id='two-client',
                           intune_client_secret=secrets[row['name']])
        blob = _forged(('certificate_authorities', 'intune_apps', 'scep_profiles'),
                       mutate=as_written_before_092)
        ScepProfile.query.filter(ScepProfile.name.in_(list(secrets))).delete(synchronize_session=False)
        IntuneApp.query.filter_by(name='legacy-two-app').delete()
        db.session.commit()

    assert _restore(auth_client, blob).status_code == 200
    with app.app_context():
        seen = {}
        for name, secret in secrets.items():
            profile = ScepProfile.query.filter_by(name=name).one()
            assert profile.intune_app is not None
            assert profile.intune_app.decrypted_secret() == secret
            seen[name] = profile.intune_app.id
        assert seen['legacy-two-a'] != seen['legacy-two-b']
