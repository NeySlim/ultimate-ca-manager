"""Test teardown for certificate templates: the rows that point to them let go first."""
from contextlib import contextmanager

from models import CATemplatePin, Certificate, db
from models.certificate_template import CertificateTemplate


def template_ids_named(*names):
    return [tid for (tid,) in db.session.query(CertificateTemplate.id).filter(CertificateTemplate.name.in_(names))]


def delete_templates(ids):
    """Delete the templates ``ids``, their pins and the policies scoped to them, and the
    certificates' and SCEP profiles' reference to them (not committed).

    SQLite reuses a deleted id, so a reference left behind counts for the next template;
    PostgreSQL refuses the delete (``certificates_template_id_fkey``). A policy loses its
    scope with its template, so it goes rather than widening to every request.
    """
    from models.policy import ApprovalRequest, CertificatePolicy
    from models.scep import ScepProfile

    ids = [tid for tid in ids if tid is not None]
    if not ids:
        return
    Certificate.query.filter(Certificate.template_id.in_(ids)).update(
        {'template_id': None}, synchronize_session=False)
    ScepProfile.query.filter(ScepProfile.template_id.in_(ids)).update(
        {'template_id': None}, synchronize_session=False)
    policies = [pid for (pid,) in db.session.query(CertificatePolicy.id).filter(
        CertificatePolicy.template_id.in_(ids))]
    if policies:
        ApprovalRequest.query.filter(ApprovalRequest.policy_id.in_(policies)).update(
            {'policy_id': None}, synchronize_session=False)
        CertificatePolicy.query.filter(CertificatePolicy.id.in_(policies)).delete(synchronize_session=False)
    CATemplatePin.query.filter(CATemplatePin.template_id.in_(ids)).delete(synchronize_session=False)
    CertificateTemplate.query.filter(CertificateTemplate.id.in_(ids)).delete(synchronize_session=False)
    db.session.expire_all()


@contextmanager
def templates_created_here_removed(app):
    """Delete on exit the templates created inside the block: the sequential
    suite shares one database, and WSTEP/XCEP offer every active template."""
    with app.app_context():
        before = set(db.session.query(CertificateTemplate.id, CertificateTemplate.name))
    yield
    with app.app_context():
        db.session.rollback()
        rows = db.session.query(CertificateTemplate.id, CertificateTemplate.name)
        delete_templates([tid for tid, name in rows if (tid, name) not in before])
        db.session.commit()
