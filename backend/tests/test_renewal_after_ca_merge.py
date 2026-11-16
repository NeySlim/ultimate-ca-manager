"""A renewal stored in the database is reported as done even when the SKI/AKI repair merges
the record of its CA into another one right after its commit: the outcome names the record
it was signed under, the effects after the commit follow the record the certificate names now."""
from sqlalchemy import text

from models import CA, Certificate, db
from tests.test_crl_number_monotonic import _authority, _ca_row


def _merged_after_the_commit(monkeypatch, dupe_id, keeper_id):
    """The renewal's commit, then the repair's merge of *dupe_id* into *keeper_id*, committed
    without touching the renewal's identity map (another transaction would not)."""
    from services.cert import renewal
    from services.ski_aki_backfill import _move_ca_dependents
    committed = renewal.commit_or_rollback

    def commit_then_merge(*args, **kwargs):
        if not committed(*args, **kwargs):
            return False
        dupe, keeper = db.session.get(CA, dupe_id), db.session.get(CA, keeper_id)
        _move_ca_dependents(db, dupe, keeper)
        db.session.execute(text('DELETE FROM certificate_authorities WHERE id = :id'), {'id': dupe_id})
        db.session.commit()
        return True
    monkeypatch.setattr(renewal, 'commit_or_rollback', commit_then_merge)


def test_a_renewal_whose_ca_record_is_merged_after_its_commit_succeeds(app, monkeypatch):
    from services.cert import renewal
    from services.cert_service import CertificateService
    from services.crl import CRLService
    import services.webhook_service as webhooks

    with app.app_context():
        key, cert = _authority()
        keeper, dupe = _ca_row(key, cert), _ca_row(key, cert)
        keeper_id, keeper_refid, dupe_id, dupe_refid = keeper.id, keeper.refid, dupe.id, dupe.refid
        row = CertificateService.create_certificate(
            descr='under the duplicate', caref=dupe_refid, dn={'CN': 'merged-after.example.test'},
            key_type='prime256v1', validity_days=30)
        cert_id, first_serial = row.id, row.serial_number
        db.session.commit()

        crls, hooks = [], []
        monkeypatch.setattr(CRLService, 'generate_crl',
                            staticmethod(lambda ca_id, **kw: crls.append(ca_id)))
        monkeypatch.setattr(webhooks, 'emit_cert_renewed',
                            lambda cert, ca_refid=None, actor=None: hooks.append(ca_refid))
        _merged_after_the_commit(monkeypatch, dupe_id, keeper_id)
        try:
            outcome = renewal.renew_certificate_in_place(
                db.session.get(Certificate, cert_id), db.session.get(CA, dupe_id))

            stored = db.session.get(Certificate, cert_id)
            assert stored.serial_number != first_serial and stored.caref == keeper_refid
            assert db.session.get(CA, dupe_id) is None
            # Signed under the duplicate; the CRL and the webhook follow the record that stays
            assert (outcome['ca_id'], outcome['ca_refid']) == (dupe_id, dupe_refid)
            assert outcome['new_serial'] == stored.serial_number
            assert crls == [keeper_id] and hooks == [keeper_refid]
        finally:
            db.session.rollback()
            db.session.execute(text('DELETE FROM revoked_serials WHERE certificate_id = :id'),
                               {'id': cert_id})
            db.session.execute(text('DELETE FROM certificates WHERE id = :id'), {'id': cert_id})
            db.session.execute(text('DELETE FROM certificate_authorities WHERE id IN (:a, :b)'),
                               {'a': keeper_id, 'b': dupe_id})
            db.session.commit()


def _leaf_under(caref, cn):
    from services.cert_service import CertificateService
    row = CertificateService.create_certificate(
        descr=cn, caref=caref, dn={'CN': cn}, key_type='prime256v1', validity_days=30)
    db.session.commit()
    return row.id


def _forget(cert_ids, ca_ids):
    db.session.rollback()
    for cert_id in cert_ids:
        db.session.execute(text('DELETE FROM revoked_serials WHERE certificate_id = :id'), {'id': cert_id})
        db.session.execute(text('DELETE FROM certificates WHERE id = :id'), {'id': cert_id})
    for ca_id in ca_ids:
        db.session.execute(text('DELETE FROM certificate_authorities WHERE id = :id'), {'id': ca_id})
    db.session.commit()


def test_an_issuer_that_cannot_be_read_after_the_commit_leaves_the_renewal_done(app, monkeypatch):
    """The read of the current issuer fails once the renewal is stored: the outcome comes
    back, no CRL is generated, the webhook names the record the certificate was signed under."""
    from sqlalchemy.exc import OperationalError
    from services.cert import renewal
    from services.crl import CRLService
    import services.webhook_service as webhooks

    with app.app_context():
        key, cert = _authority()
        ca = _ca_row(key, cert)
        ca_id, ca_refid = ca.id, ca.refid
        cert_id = _leaf_under(ca_refid, 'issuer-unread.example.test')
        first_serial = db.session.get(Certificate, cert_id).serial_number
        crls, hooks = [], []
        monkeypatch.setattr(CRLService, 'generate_crl',
                            staticmethod(lambda ca_id, **kw: crls.append(ca_id)))
        monkeypatch.setattr(webhooks, 'emit_cert_renewed',
                            lambda cert, ca_refid=None, actor=None: hooks.append(ca_refid))
        committed = renewal.commit_or_rollback

        def commit_then_break_the_read(*args, **kwargs):
            done = committed(*args, **kwargs)

            def down(*a, **k):
                raise OperationalError('SELECT', {}, Exception('database is down'))
            monkeypatch.setattr(renewal, 'select', down)
            return done
        monkeypatch.setattr(renewal, 'commit_or_rollback', commit_then_break_the_read)
        try:
            outcome = renewal.renew_certificate_in_place(
                db.session.get(Certificate, cert_id), db.session.get(CA, ca_id))
            monkeypatch.undo()
            assert outcome['new_serial'] != first_serial and outcome['ca_id'] == ca_id
            assert db.session.get(Certificate, cert_id).serial_number == outcome['new_serial']
            assert crls == [] and hooks == [ca_refid]
        finally:
            monkeypatch.undo()
            _forget([cert_id], [ca_id])


def test_a_pair_renewed_under_one_ca_regenerates_its_crl_once(app, monkeypatch, tmp_path):
    from services.cert import renewal
    from services.crl import CRLService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_renewal_overtaken import _linked_rows

    with _bound_to(app, f"sqlite:///{tmp_path / 'pair-crl.db'}"):
        a_id, (b_id,) = _linked_rows(app, n_b=1)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            ca = CA.query.filter_by(refid=a.caref).one()
            ca.cdp_enabled = True
            db.session.commit()
            ca_id, crls = ca.id, []
            monkeypatch.setattr(CRLService, 'generate_crl',
                                staticmethod(lambda ca_id, **kw: crls.append(ca_id)))
            outcome = renewal.renew_certificate_in_place(db.session.get(Certificate, a_id),
                                                         username='admin')
            monkeypatch.undo()
            assert [r['cert_id'] for r in outcome['related']] == [b_id]
            assert crls == [ca_id]
            db.session.remove()


def test_a_bulk_renewal_publishes_the_crl_of_the_record_that_remains(app, monkeypatch):
    """The bulk path publishes its CRLs after the loop: for the record each renewed
    certificate names by then, once per record, and only where the CDP is enabled."""
    from api.v2.certificates import bulk
    from services.crl import CRLService
    from services.ski_aki_backfill import _move_ca_dependents

    with app.app_context():
        key, cert = _authority()
        keeper, dupe, quiet = _ca_row(key, cert), _ca_row(key, cert), _ca_row(key, cert)
        quiet.cdp_enabled = False
        db.session.commit()
        keeper_id, dupe_id, quiet_id = keeper.id, dupe.id, quiet.id
        silent = _leaf_under(quiet.refid, 'bulk-no-cdp.example.test')
        moved = [_leaf_under(dupe.refid, f'bulk-merged-{i}.example.test') for i in range(2)]
        _move_ca_dependents(db, db.session.get(CA, dupe_id), db.session.get(CA, keeper_id))
        db.session.execute(text('DELETE FROM certificate_authorities WHERE id = :id'), {'id': dupe_id})
        db.session.commit()
        crls = []
        monkeypatch.setattr(CRLService, 'generate_crl',
                            staticmethod(lambda ca_id, **kw: crls.append(ca_id)))
        try:
            bulk._publish_crls(moved + [silent, 10 ** 9], 'admin')
            assert crls == [keeper_id]
        finally:
            monkeypatch.undo()
            _forget(moved + [silent], [keeper_id, dupe_id, quiet_id])


def test_the_scheduler_publishes_the_crl_of_the_record_that_remains(app, monkeypatch):
    """The scheduler publishes its CRLs after the batch: a record merged away while a later
    certificate was handled is not the one the first renewed certificate names by then."""
    from models import SystemConfig
    from services import auto_renewal_service as svc
    from services.ski_aki_backfill import _move_ca_dependents

    with app.app_context():
        key, cert = _authority()
        keeper, dupe = _ca_row(key, cert), _ca_row(key, cert)
        keeper_id, keeper_refid, dupe_id = keeper.id, keeper.refid, dupe.id
        first = _leaf_under(dupe.refid, 'sched-merged.example.test')
        second = _leaf_under(keeper.refid, 'sched-failed.example.test')
        enabled = SystemConfig.query.filter_by(key='auto_renewal_enabled').first()
        was = enabled.value if enabled is not None else None

        def renew(cert, regenerate_crl=True, known_serial=None):
            if cert.id == first:
                return True, cert.id
            _move_ca_dependents(db, db.session.get(CA, dupe_id), db.session.get(CA, keeper_id))
            db.session.execute(text('DELETE FROM certificate_authorities WHERE id = :id'), {'id': dupe_id})
            db.session.commit()
            return False, 'not renewed'

        published = []
        monkeypatch.setattr(svc.AutoRenewalService, 'renew_certificate', staticmethod(renew))
        monkeypatch.setattr(svc.AutoRenewalService, '_held_for_approval',
                            staticmethod(lambda cert, already_queued: None))
        monkeypatch.setattr(svc.AutoRenewalService, '_publish_crls',
                            staticmethod(lambda carefs: published.append(set(carefs))))
        monkeypatch.setattr(svc.AutoRenewalService, '_send_failure_notification',
                            staticmethod(lambda stats: None))
        monkeypatch.setattr(svc.AutoRenewalService, '_send_renewal_notification',
                            staticmethod(lambda stats: None))
        monkeypatch.setattr(svc.AutoRenewalService, 'get_certificates_for_renewal', staticmethod(
            lambda: [db.session.get(Certificate, first), db.session.get(Certificate, second)]))
        try:
            svc.AutoRenewalService.set_renewal_config({'enabled': True})
            stats = svc.AutoRenewalService.run_auto_renewal()
            assert (stats['renewed'], stats['failed']) == (1, 1), stats
            assert published == [{keeper_refid}]
        finally:
            monkeypatch.undo()
            db.session.rollback()
            row = SystemConfig.query.filter_by(key='auto_renewal_enabled').first()
            if was is None and row is not None:
                db.session.delete(row)
            elif row is not None:
                row.value = was
            db.session.commit()
            _forget([first, second], [keeper_id, dupe_id])
