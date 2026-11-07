"""Test teardown for certificate templates: the rows that point to them let go first."""
from models import CATemplatePin, Certificate, db
from models.certificate_template import CertificateTemplate


def template_ids_named(*names):
    return [tid for (tid,) in db.session.query(CertificateTemplate.id).filter(CertificateTemplate.name.in_(names))]


def delete_templates(ids):
    """Delete the templates ``ids``, their pins, and their certificates' reference to them (not committed).

    SQLite reuses a deleted id, so a reference left behind counts for the next template;
    PostgreSQL refuses the delete (``certificates_template_id_fkey``).
    """
    ids = [tid for tid in ids if tid is not None]
    if not ids:
        return
    Certificate.query.filter(Certificate.template_id.in_(ids)).update(
        {'template_id': None}, synchronize_session=False)
    CATemplatePin.query.filter(CATemplatePin.template_id.in_(ids)).delete(synchronize_session=False)
    CertificateTemplate.query.filter(CertificateTemplate.id.in_(ids)).delete(synchronize_session=False)
    db.session.expire_all()
