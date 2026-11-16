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
