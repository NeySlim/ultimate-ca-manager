"""What still depends on a CA in what UCM issues and delivers (#400).

A chain depends on X when one of its links is a CA of X's subtree (records of X's key included), or a
cross-certificate of such a CA or issued by one. Chains are resolved once per issuing CA; certificates with
no CA once per issuer and AKI, or per inline chain above the leaf, and alone without an AKI or self-signed.
"""
import base64
from collections import defaultdict
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import and_, or_, select

from models import CA, Certificate, CRLDeployBinding, DeployBinding, DeployTarget, db
from models.ca_cross_certificate import CACrossCertificate
from services.ca import cross_certs
from utils.ca_chain import AUTO, issuer_chain
from utils.cert_issuer import authority_key_identifier_hex, same_key_refids
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
    """``(scope, own)``: refids of *ca*, its records of the same key and every CA below them; *own* is the first two."""
    children = defaultdict(list)
    for c in all_cas.values():
        children[c.caref].append(c.refid)
    own = set(same_key_refids(ca)) | {ca.refid}
    scope, todo = set(), list(own)
    while todo:
        refid = todo.pop()
        if refid not in scope:
            scope.add(refid)
            todo.extend(children.get(refid, []))
    return scope, own


class _Hits:
    """Which certificates of a chain belong to the dependency set of one CA."""

    def __init__(self, scope, all_cas):
        self.scope, self.known = scope, set(all_cas)
        self.scope_ders = {d for r in scope if r in all_cas and all_cas[r].crt and (d := _der(all_cas[r].crt))}
        self.ders = set(self.scope_ders)
        scope_ids = {all_cas[r].id for r in scope if r in all_cas}
        self.issued_crosses, self.hot_crosses = [], []
        refid_of = {c.id: c.refid for c in all_cas.values()}
        self.hot_served = set()
        for row in CACrossCertificate.query.order_by(CACrossCertificate.id).all():
            issuer = all_cas.get(row.issuer_caref) or cross_certs.issuer_of(row)
            by_scope = issuer is not None and issuer.refid in scope
            if by_scope:
                self.issued_crosses.append(row)
            if by_scope or row.ca_id in scope_ids:
                self.hot_crosses.append(row)
                if row.served and row.servable and row.ca_id in refid_of:
                    self.hot_served.add(refid_of[row.ca_id])
                if der := _der(row.crt):
                    self.ders.add(der)
        self.hot_cross_ids = {r.id for r in self.hot_crosses}

    def may_reach(self, caref, all_cas):
        """Whether the default chain of *caref* can include a hot cross: an ancestor serves one."""
        seen, ca = set(), all_cas.get(caref)
        while ca is not None and ca.refid not in seen:
            if ca.refid in self.hot_served:
                return True
            seen.add(ca.refid)
            ca = all_cas.get(ca.caref)
        return False

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


def _group_key(cert):
    """Certificates with the same key chain alike: inline ones by the chain above their leaf, the others by
    issuer and AKI. Without an AKI only the signature tells two keys of one name apart, and a self-signed
    copy of a CA shares its name and AKI with what it issued: each of those is resolved alone."""
    try:
        raw = base64.b64decode(cert.crt)
        if raw.count(b'BEGIN CERTIFICATE') > 1:
            return ('inline', raw.split(b'-----END CERTIFICATE-----', 1)[1].strip())
        parsed = x509.load_pem_x509_certificate(raw)
        aki = authority_key_identifier_hex(parsed)
        if aki and parsed.issuer != parsed.subject:
            return ('issuer', parsed.issuer.rfc4514_string(), aki)
    except Exception:
        pass
    return ('cert', cert.id)


def _orphans(hits, orphan_cond, now):
    """``(issued_ids, via_ids)`` of certificates with no usable caref, chained as the export chains them."""
    from api.v2.certificates.export import _build_ca_chain
    groups = defaultdict(list)
    for cert in Certificate.query.filter(orphan_cond, *_active(now)).all():
        groups[_group_key(cert)].append(cert)
    issued, via = set(), set()
    for members in groups.values():
        cert = members[0]
        try:
            chain = _build_ca_chain(cert, base64.b64decode(cert.crt), include_root=True)
            ders = [c.public_bytes(serialization.Encoding.DER) for c in chain]
        except Exception:
            continue
        if ders and ders[0] in hits.scope_ders:
            issued.update(m.id for m in members)
        elif any(d in hits.ders for d in ders):
            via.update(m.id for m in members)
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
        # A pinned variant also depends on the caref, so an inline chain with a known one keeps it in the key
        group = _group_key(cert) if inline or cert.caref not in hits.known else cert.caref
        if inline and cert.caref in hits.known:
            group = (group, cert.caref)
        key = (group, variant, include_root)
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


def _crl_items(scope_ids, with_targets):
    q = (db.session.query(CRLDeployBinding, DeployTarget, CA)
         .join(DeployTarget, CRLDeployBinding.target_id == DeployTarget.id)
         .join(CA, CRLDeployBinding.ca_id == CA.id)
         .filter(CRLDeployBinding.enabled.is_(True), DeployTarget.enabled.is_(True),
                 CRLDeployBinding.ca_id.in_(scope_ids)))
    total = q.count()
    rows = q.order_by(CRLDeployBinding.id).limit(LIMIT).all() if with_targets else []
    items = [{'id': b.id, 'target_id': t.id, 'target': t.name, 'ca_id': c.id, 'ca_name': c.descr,
              'crl_path': b.crl_path} for b, t, c in rows]
    return {'count': total, 'items': items, 'truncated': with_targets and total > LIMIT}


def _subordinates(scope, own, all_cas, now):
    """Active CAs below the CA, its records of the same key left out."""
    live = [c for r in scope - own if (c := all_cas.get(r)) and c.crt and not c.revoked
            and (c.valid_to is None or c.valid_to > now)]
    live.sort(key=lambda c: (c.valid_to is None, c.valid_to or datetime.min, c.id))
    return {'count': len(live), 'truncated': len(live) > LIMIT,
            'items': [{'id': c.id, 'name': c.descr, 'valid_to': utc_isoformat(c.valid_to)} for c in live[:LIMIT]]}


def chain_usage(ca, with_targets=True):
    """*with_targets* False counts the bindings but names none of them."""
    with cross_certs.without_storing():
        return _chain_usage(ca, with_targets)


def _chain_usage(ca, with_targets):
    now = utc_now()
    all_cas = {c.refid: c for c in CA.query.all()}
    names = {r: c.descr for r, c in all_cas.items()}
    scope, own = _scope(ca, all_cas)
    hits = _Hits(scope, all_cas)
    active = _active(now)
    orphan_cond = or_(Certificate.caref.is_(None), Certificate.caref.notin_(select(CA.refid)))

    via_carefs = set()
    for (caref,) in db.session.query(Certificate.caref).filter(Certificate.caref.in_(list(all_cas)), *active).distinct():
        if (caref not in scope and hits.may_reach(caref, all_cas)
                and any(hits.link(l) for l in issuer_chain(all_cas[caref]))):
            via_carefs.add(caref)

    orphan_issued, orphan_via = _orphans(hits, orphan_cond, now)
    issued = _section(and_(or_(Certificate.caref.in_(list(hits.scope)), Certificate.id.in_(orphan_issued)), *active), names)
    via = _section(and_(or_(Certificate.caref.in_(list(via_carefs)), Certificate.id.in_(orphan_via)), *active), names)
    via['cross_certificates'] = [
        {'id': r.id, 'ca_id': r.ca_id, 'ca_name': r.ca.descr if r.ca else None, 'served': bool(r.served),
         'servable': r.servable} for r in hits.issued_crosses]
    concerned = Certificate.caref.in_(list(hits.scope | via_carefs))
    return {'issued': issued, 'via_cross': via,
            'subordinate_cas': _subordinates(scope, own, all_cas, now),
            'deployments': _binding_items(hits, concerned, orphan_cond, now, with_targets),
            'crl_deployments': _crl_items([all_cas[r].id for r in scope if r in all_cas], with_targets),
            'note': NOTE}
