"""What still depends on a CA in what UCM issues and delivers (#400).

The default chain is resolved once per issuing CA, not per certificate; certificates are counted in SQL.
"""
import base64

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import or_

from models import CA, Certificate, DeployBinding, DeployTarget, db
from models.ca_cross_certificate import CACrossCertificate
from utils.ca_chain import AUTO, issuer_chain, parse_variant
from utils.cert_issuer import same_key_refids
from utils.datetime_utils import utc_isoformat, utc_now

LIMIT = 100
NOTE = ('UCM only sees what it issues and delivers: a client that cached a chain, '
        'or got it from somewhere else, is not counted.')


def _active(now):
    return [Certificate.crt.isnot(None), Certificate.revoked.isnot(True), Certificate.archived.isnot(True),
            or_(Certificate.valid_to.is_(None), Certificate.valid_to > now)]


def _subtree(ca):
    """Ids and refids of *ca* and every CA below it (by ``caref``)."""
    rows = CA.query.with_entities(CA.id, CA.refid, CA.caref).all()
    children = {}
    for cid, refid, caref in rows:
        children.setdefault(caref, []).append((cid, refid))
    ids, refids, todo = {ca.id}, {ca.refid}, [ca.refid]
    while todo:
        for cid, refid in children.get(todo.pop(), []):
            if refid not in refids:
                ids.add(cid)
                refids.add(refid)
                todo.append(refid)
    return ids, refids


def _default_cross(ca, issuer_refids):
    """The cross-certificate in *ca*'s default chain when X issued it, else None."""
    row = next((l.cross for l in issuer_chain(ca) if l.cross is not None), None)
    return row if row is not None and row.issuer_caref in issuer_refids else None


def _cert_item(cert, names):
    return {'id': cert.id, 'name': cert.descr or cert.subject_cn, 'cn': cert.subject_cn,
            'ca': names.get(cert.caref), 'ca_refid': cert.caref, 'valid_to': utc_isoformat(cert.valid_to)}


def _section(query, names):
    total = query.count()
    rows = query.order_by(Certificate.valid_to.asc(), Certificate.id.asc()).limit(LIMIT).all()
    return {'count': total, 'items': [_cert_item(c, names) for c in rows], 'truncated': total > LIMIT}


def _pushes_chain_of(binding, cert, subtree_ids):
    """Whether the chain this binding pushes (as the push resolves it) holds a certificate of a CA in the subtree."""
    from services.deploy.service import DeployService
    pem = DeployService._chain_pem(cert, base64.b64decode(cert.crt).decode(), include_root=bool(binding.include_root),
                                   variant=binding.chain_variant or AUTO)
    der = {c.public_bytes(serialization.Encoding.DER) for c in
           (x509.load_pem_x509_certificate(b.encode()) for b in DeployService._split_pem(pem))}
    if not der:
        return False
    for ca in CA.query.filter(CA.id.in_(subtree_ids), CA.crt.isnot(None)).all():
        try:
            if x509.load_pem_x509_certificate(base64.b64decode(ca.crt)).public_bytes(serialization.Encoding.DER) in der:
                return True
        except Exception:
            continue
    return False


def _deployments(issued_ids, via_ids, issuer_refids, subtree_ids, now):
    from services.deploy.service import DeployService
    pinned = {r.id for r in CACrossCertificate.query.filter(
        CACrossCertificate.issuer_caref.in_(issuer_refids)).all() if r.servable}
    q = (db.session.query(DeployBinding, DeployTarget, Certificate)
         .join(DeployTarget, DeployBinding.target_id == DeployTarget.id)
         .join(Certificate, DeployBinding.certificate_id == Certificate.id)
         .filter(DeployBinding.enabled.is_(True), DeployTarget.enabled.is_(True),
                 DeployBinding.fullchain_path.isnot(None), DeployBinding.fullchain_path != '', *_active(now)))
    found = []
    for binding, target, cert in q.order_by(Certificate.valid_to.asc(), DeployBinding.id.asc()).all():
        try:
            wanted = parse_variant(DeployService.push_chain_variant(cert, binding.chain_variant or AUTO))
            if isinstance(wanted, tuple):
                hit = wanted[1] in pinned
            else:
                hit = wanted == AUTO and cert.id in via_ids
            if not hit and cert.id in issued_ids:
                hit = _pushes_chain_of(binding, cert, subtree_ids)
        except ValueError:  # the push itself would refuse this binding
            continue
        if hit:
            found.append({'id': binding.id, 'target_id': target.id, 'target': target.name,
                          'certificate_id': cert.id, 'certificate': cert.descr or cert.subject_cn,
                          'variant': binding.chain_variant or AUTO})
    return {'count': len(found), 'items': found[:LIMIT], 'truncated': len(found) > LIMIT}


def chain_usage(ca):
    now = utc_now()
    names = dict(CA.query.with_entities(CA.refid, CA.descr).all())
    sub_ids, sub_refids = _subtree(ca)
    issuer_refids = set(same_key_refids(ca))
    active = _active(now)

    issued_q = Certificate.query.filter(Certificate.caref.in_(sub_refids), *active)

    chains = {}
    for (caref,) in db.session.query(Certificate.caref).filter(Certificate.caref.isnot(None), *active).distinct():
        start = CA.query.filter_by(refid=caref).first()
        row = _default_cross(start, issuer_refids) if start is not None else None
        if row is not None:
            chains[caref] = row
    via_q = Certificate.query.filter(Certificate.caref.in_(list(chains)), *active)
    via = _section(via_q, names)
    via['cross_certificates'] = [
        {'id': r.id, 'ca_id': r.ca_id, 'ca_name': r.ca.descr if r.ca else None, 'served': bool(r.served)}
        for r in sorted({r.id: r for r in chains.values()}.values(), key=lambda r: r.id)]

    issued_ids = {i for (i,) in issued_q.with_entities(Certificate.id).all()}
    via_ids = {i for (i,) in via_q.with_entities(Certificate.id).all()}
    return {'issued': _section(issued_q, names), 'via_cross': via,
            'deployments': _deployments(issued_ids, via_ids, issuer_refids, sub_ids, now), 'note': NOTE}
