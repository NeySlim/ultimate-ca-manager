"""What still depends on a CA in what UCM issues and delivers (#400).

A chain depends on X when one of its links is a CA of X's subtree (records of the same key included), or a
cross-certificate of such a CA or issued by one. Chains are resolved once per issuing CA, never per certificate.
"""
import base64
from collections import defaultdict
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import and_, or_, select

from models import CA, Certificate, DeployBinding, DeployTarget, db
from models.ca_cross_certificate import CACrossCertificate
from services.ca import cross_certs
from utils.ca_chain import AUTO, issuer_chain
from utils.cert_issuer import same_key_refids
from utils.datetime_utils import utc_isoformat, utc_now

LIMIT = 100
NOTE = ('UCM only sees what it issues and delivers: a client that cached a chain, '
        'or got it from somewhere else, is not counted.')


def _active(now):
    return [Certificate.crt.isnot(None), Certificate.revoked.isnot(True), Certificate.archived.isnot(True),
            or_(Certificate.valid_to.is_(None), Certificate.valid_to > now)]


def _der(b64_pem):
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(b64_pem)).public_bytes(serialization.Encoding.DER)
    except Exception:
        return None


def _scope(ca, all_cas):
    """Refids of *ca*, every CA below it and every record of the same key as one of them."""
    children = defaultdict(list)
    for c in all_cas.values():
        children[c.caref].append(c.refid)
    scope, todo = set(), [ca.refid]
    while todo:
        refid = todo.pop()
        if refid in scope:
            continue
        member = all_cas.get(refid)
        new = [r for r in (same_key_refids(member) if member else []) + [refid] if r not in scope]
        scope.update(new)
        for r in new:
            todo.extend(children.get(r, []))
    return scope


class _Hits:
    """Which certificates of a chain belong to the dependency set of one CA."""

    def __init__(self, scope, all_cas):
        self.scope, self.known = scope, set(all_cas)
        self.scope_ders = {d for r in scope if r in all_cas and all_cas[r].crt and (d := _der(all_cas[r].crt))}
        self.ders = set(self.scope_ders)
        scope_ids = {all_cas[r].id for r in scope if r in all_cas}
        self.issued_crosses, self.hot_crosses = [], []
        for row in CACrossCertificate.query.order_by(CACrossCertificate.id).all():
            issuer = cross_certs.issuer_of(row)
            by_scope = issuer is not None and issuer.refid in scope
            if by_scope:
                self.issued_crosses.append(row)
            if by_scope or row.ca_id in scope_ids:
                self.hot_crosses.append(row)
                if der := _der(row.crt):
                    self.ders.add(der)
        self.hot_cross_ids = {r.id for r in self.hot_crosses}

    def link(self, link):
        if link.cross is None:
            return link.ca is not None and link.ca.refid in self.scope
        return link.cross.id in self.hot_cross_ids

    def chain_pem(self, pem_text):
        from services.deploy.service import DeployService
        return [x509.load_pem_x509_certificate(b.encode()).public_bytes(serialization.Encoding.DER)
                for b in DeployService._split_pem(pem_text)]


def _cert_item(cert, names):
    return {'id': cert.id, 'name': cert.descr or cert.subject_cn, 'cn': cert.subject_cn,
            'ca': names.get(cert.caref), 'ca_refid': cert.caref, 'valid_to': utc_isoformat(cert.valid_to)}


def _section(condition, names):
    query = Certificate.query.filter(condition)
    total = query.count()
    rows = (query.order_by(Certificate.valid_to.is_(None), Certificate.valid_to.asc(), Certificate.id.asc())
            .limit(LIMIT).all())
    return {'count': total, 'items': [_cert_item(c, names) for c in rows], 'truncated': total > LIMIT}


def _orphans(hits, orphan_cond, now):
    """``(issued_ids, via_ids)`` of certificates with no usable caref, chained as the export chains them."""
    from api.v2.certificates.export import _build_ca_chain
    issued, via = set(), set()
    for cert in Certificate.query.filter(orphan_cond, *_active(now)).all():
        try:
            chain = _build_ca_chain(cert, base64.b64decode(cert.crt), include_root=True)
            ders = [c.public_bytes(serialization.Encoding.DER) for c in chain]
        except Exception:
            continue
        if ders and ders[0] in hits.scope_ders:
            issued.add(cert.id)
        elif any(d in hits.ders for d in ders):
            via.add(cert.id)
    return issued, via


def _binding_items(hits, concerned, orphan_cond, now, with_targets):
    from services.deploy.service import DeployService
    pins = [f'cross:{i}' for i in hits.hot_cross_ids]
    q = (db.session.query(DeployBinding, DeployTarget, Certificate)
         .join(DeployTarget, DeployBinding.target_id == DeployTarget.id)
         .join(Certificate, DeployBinding.certificate_id == Certificate.id)
         .filter(DeployBinding.enabled.is_(True), DeployTarget.enabled.is_(True),
                 DeployBinding.fullchain_path.isnot(None), DeployBinding.fullchain_path != '', *_active(now),
                 or_(concerned, orphan_cond, DeployBinding.chain_variant.in_(pins))))
    memo, found = {}, []
    for binding, target, cert in q.all():
        variant, include_root = binding.chain_variant or AUTO, bool(binding.include_root)
        inline = base64.b64decode(cert.crt).count(b'BEGIN CERTIFICATE') > 1
        key = (cert.id if inline or cert.caref not in hits.known else cert.caref, variant, include_root)
        if key not in memo:
            try:
                pem = DeployService._chain_pem(cert, base64.b64decode(cert.crt).decode(), include_root=include_root,
                                               variant=variant, quiet=True)
                memo[key] = any(d in hits.ders for d in hits.chain_pem(pem))
            except ValueError:  # the push itself would refuse this binding
                memo[key] = False
        if memo[key]:
            found.append((binding, target, cert))
    found.sort(key=lambda r: (r[2].valid_to is None, r[2].valid_to or datetime.min, r[0].id))
    items = [{'id': b.id, 'target_id': t.id, 'target': t.name, 'certificate_id': c.id,
              'certificate': c.descr or c.subject_cn, 'variant': b.chain_variant or AUTO}
             for b, t, c in found[:LIMIT]] if with_targets else []
    return {'count': len(found), 'items': items, 'truncated': with_targets and len(found) > LIMIT}


def chain_usage(ca, with_targets=True):
    """*with_targets* False counts the bindings but names none of them."""
    now = utc_now()
    all_cas = {c.refid: c for c in CA.query.all()}
    names = {r: c.descr for r, c in all_cas.items()}
    hits = _Hits(_scope(ca, all_cas), all_cas)
    active = _active(now)
    orphan_cond = or_(Certificate.caref.is_(None), Certificate.caref == '',
                      Certificate.caref.notin_(select(CA.refid)))

    via_carefs = set()
    for (caref,) in db.session.query(Certificate.caref).filter(Certificate.caref.in_(list(all_cas)), *active).distinct():
        if caref not in hits.scope and any(hits.link(l) for l in issuer_chain(all_cas[caref])):
            via_carefs.add(caref)

    orphan_issued, orphan_via = _orphans(hits, orphan_cond, now)
    issued = _section(and_(or_(Certificate.caref.in_(list(hits.scope)), Certificate.id.in_(orphan_issued)), *active), names)
    via = _section(and_(or_(Certificate.caref.in_(list(via_carefs)), Certificate.id.in_(orphan_via)), *active), names)
    via['cross_certificates'] = [
        {'id': r.id, 'ca_id': r.ca_id, 'ca_name': r.ca.descr if r.ca else None, 'served': bool(r.served),
         'servable': r.servable} for r in hits.issued_crosses]
    concerned = Certificate.caref.in_(list(hits.scope | via_carefs))
    return {'issued': issued, 'via_cross': via,
            'deployments': _binding_items(hits, concerned, orphan_cond, now, with_targets), 'note': NOTE}
