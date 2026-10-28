"""
SKI/AKI Backfill & Chain Repair Task

Phase 1: Populate missing SKI/AKI from stored PEM certificates
Phase 2: Re-chain orphan CAs via AKI→SKI matching
Phase 3: Re-chain orphan certificates via AKI→SKI matching
Phase 4: Deduplicate CAs with identical SKI and certificate (merge into best record)

Runs at startup then hourly. Phases 2-4 handle late imports
(e.g., CA imported after its child certificates).
"""
import base64
import logging
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID
from utils.cert_issuer import find_ca_by_ski

logger = logging.getLogger(__name__)


def _certificate_fingerprint(crt):
    """SHA-256 of the stored certificate, None when the record holds none yet."""
    if not crt:
        return None
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(crt), default_backend())
        return cert.fingerprint(hashes.SHA256()).hex()
    except Exception:
        return f'raw:{crt}'


def _merge_ca_group(db, cas_with_ski, stats):
    """Merge records of one CA into the best of them (parent link, then key)."""
    keeper = None
    for c in cas_with_ski:
        if c.caref and c.prv:
            keeper = c
            break
    if not keeper:
        for c in cas_with_ski:
            if c.caref:
                keeper = c
                break
    if not keeper:
        for c in cas_with_ski:
            if c.prv:
                keeper = c
                break
    if not keeper:
        keeper = cas_with_ski[0]

    latest = max(cas_with_ski, key=lambda c: c.id)
    if latest.descr != keeper.descr:
        logger.info(f"SKI/AKI backfill: renaming keeper '{keeper.descr}' -> '{latest.descr}'")
        keeper.descr = latest.descr
    if not keeper.caref:
        for c in cas_with_ski:
            if c.caref:
                keeper.caref = c.caref
                break
    if not keeper.prv:
        for c in cas_with_ski:
            if c.prv:
                keeper.prv = c.prv
                break

    for c in cas_with_ski:
        if c.id == keeper.id:
            continue
        try:
            with db.session.begin_nested():
                _move_ca_dependents(db, c, keeper)
                # Raw SQL to avoid ORM cascade issues with incomplete schemas
                db.session.execute(db.text("DELETE FROM certificate_authorities WHERE id = :id"), {'id': c.id})
        except Exception as exc:
            logger.warning(f"SKI/AKI backfill: CA '{c.descr}' (id={c.id}) not merged into id={keeper.id}: {exc}")
            continue
        db.session.expunge(c)
        logger.info(f"SKI/AKI backfill: dedup CA '{c.descr}' (id={c.id}) -> merged into '{keeper.descr}' (id={keeper.id})")
        stats['deduplicated'] += 1


# Derived per-CA data the keeper regenerates; every other reference moves to it
# (CRL history included: CRL numbers must not restart below the published ones)
_DISCARDED_WITH_CA = {'ocsp_responses'}
# Tables unique on (CA, column): the duplicate's rows the keeper already has are dropped
_UNIQUE_PER_CA = {'ca_template_pins': 'template_id', 'crl_deploy_bindings': 'target_id'}
# Parent references declared without a foreign key
_UNDECLARED_CAREF = (('certificate_authorities', 'caref'), ('crls', 'caref'),
                     ('ca_cross_certificates', 'issuer_caref'))


def _move_ca_dependents(db, dupe, keeper):
    """Point every row referencing *dupe* (by refid or id) at *keeper*, so none is orphaned."""
    for table in db.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name != 'certificate_authorities' or fk.column.name not in ('id', 'refid'):
                continue
            column = fk.parent.name
            old, new = ((dupe.refid, keeper.refid) if fk.column.name == 'refid' else (dupe.id, keeper.id))
            if table.name in _DISCARDED_WITH_CA:
                db.session.execute(table.delete().where(fk.parent == old))
            elif table.name in _UNIQUE_PER_CA:
                other = table.c[_UNIQUE_PER_CA[table.name]]
                db.session.execute(table.delete().where(
                    (fk.parent == old) & other.in_(db.select(other).where(fk.parent == new))))
                db.session.execute(table.update().where(fk.parent == old).values({column: new}))
            else:
                db.session.execute(table.update().where(fk.parent == old).values({column: new}))
    for name, column in _UNDECLARED_CAREF:
        table = db.metadata.tables[name]
        db.session.execute(table.update().where(table.c[column] == dupe.refid).values({column: keeper.refid}))


def backfill_ski_aki():
    """Extract and store SKI/AKI for all certs/CAs missing them, then repair chains."""
    from models import db, CA, Certificate

    stats = {
        'updated_cas': 0,
        'updated_certs': 0,
        'rechained_cas': 0,
        'rechained_certs': 0,
        'deduplicated': 0,
        'same_key_distinct_certs': 0,
        'orphan_cas': 0,
        'orphan_certs': 0,
        'total_cas': 0,
        'total_certs': 0,
    }

    stats['total_cas'] = CA.query.count()
    stats['total_certs'] = Certificate.query.count()

    # --- CAs: populate SKI ---
    cas = CA.query.filter(
        CA.crt.isnot(None), CA.crt != '',
        CA.ski.is_(None)
    ).all()

    for ca in cas:
        try:
            pem = base64.b64decode(ca.crt)
            if isinstance(pem, bytes):
                pem_str = pem.decode('utf-8')
            else:
                pem_str = pem
            cert_obj = x509.load_pem_x509_certificate(pem_str.encode(), default_backend())
            ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            ca.ski = ext.value.key_identifier.hex(':').upper()
            stats['updated_cas'] += 1
        except Exception:
            pass  # Cert may not have SKI extension

    # --- Certificates: populate AKI + SKI ---
    certs = Certificate.query.filter(
        Certificate.crt.isnot(None), Certificate.crt != '',
        Certificate.aki.is_(None)
    ).all()

    for cert in certs:
        try:
            pem = base64.b64decode(cert.crt)
            if isinstance(pem, bytes):
                pem_str = pem.decode('utf-8')
            else:
                pem_str = pem
            cert_obj = x509.load_pem_x509_certificate(pem_str.encode(), default_backend())

            try:
                ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
                if ext.value.key_identifier:
                    cert.aki = ext.value.key_identifier.hex(':').upper()
            except Exception:
                pass

            try:
                ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                cert.ski = ext.value.key_identifier.hex(':').upper()
            except Exception:
                pass

            stats['updated_certs'] += 1
        except Exception:
            pass

    if stats['updated_cas'] or stats['updated_certs']:
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ski_aki_backfill.py:93: {_commit_err}", exc_info=True)
            raise
        logger.info(f"SKI/AKI backfill: updated {stats['updated_cas']} CAs, {stats['updated_certs']} certificates")
    else:
        logger.debug("SKI/AKI backfill: all records up to date")

    # --- Phase 2: Re-chain orphan CAs (caref empty but AKI available) ---
    orphan_cas_list = CA.query.filter(
        CA.caref.is_(None) | (CA.caref == ''),
        CA.crt.isnot(None), CA.crt != ''
    ).all()

    for ca in orphan_cas_list:
        try:
            pem = base64.b64decode(ca.crt)
            cert_obj = x509.load_pem_x509_certificate(
                pem.decode('utf-8').encode() if isinstance(pem, bytes) else pem.encode(),
                default_backend()
            )
            try:
                ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
                if ext.value.key_identifier:
                    aki = ext.value.key_identifier.hex(':').upper()
                else:
                    continue
            except Exception:
                continue  # Self-signed root, no AKI

            if aki == ca.ski:
                continue

            parent = find_ca_by_ski(aki, exclude_id=ca.id)
            if parent:
                ca.caref = parent.refid
                stats['rechained_cas'] += 1
                logger.info(f"SKI/AKI backfill: re-chained CA '{ca.descr}' -> parent '{parent.descr}'")
        except Exception:
            pass

    # --- Phase 3: Re-chain orphan certificates ---
    # Include certs with NULL/empty caref AND certs whose caref points to a non-existent CA
    ca_refids = set(ca.refid for ca in CA.query.with_entities(CA.refid).all())
    
    orphan_certs_list = Certificate.query.filter(
        Certificate.aki.isnot(None)
    ).all()

    for cert in orphan_certs_list:
        # Skip if caref is valid (points to existing CA)
        if cert.caref and cert.caref in ca_refids:
            continue
        try:
            parent = find_ca_by_ski(cert.aki)
            if parent:
                old_caref = cert.caref
                cert.caref = parent.refid
                stats['rechained_certs'] += 1
                logger.info(f"SKI/AKI backfill: re-chained cert '{cert.descr}' (caref={old_caref}) -> CA '{parent.descr}'")
        except Exception:
            pass

    # --- Phase 4: Deduplicate CAs with same SKI ---
    # Only records holding the same certificate are one CA: a cross-certificate
    # shares the SKI of the root it cross-signs, and a record without one has
    # nothing the keeper could take over.
    from sqlalchemy import func
    dupes = db.session.query(CA.ski).filter(CA.ski.isnot(None)).group_by(CA.ski).having(func.count(CA.id) > 1).all()
    for (dupe_ski,) in dupes:
        cas_with_ski = CA.query.filter(CA.ski == dupe_ski).order_by(CA.id.asc()).all()
        by_cert = {}
        for c in cas_with_ski:
            fingerprint = _certificate_fingerprint(c.crt)
            if fingerprint:
                by_cert.setdefault(fingerprint, []).append(c)
        if len(by_cert) > 1:
            stats['same_key_distinct_certs'] += 1
            logger.info(f"SKI/AKI backfill: CAs {[c.id for c in cas_with_ski]} share SKI {dupe_ski} "
                           f"with distinct certificates (cross-certificate?), not merged")
        for group in by_cert.values():
            if len(group) > 1:
                _merge_ca_group(db, group, stats)

    if stats['rechained_cas'] or stats['rechained_certs'] or stats['deduplicated']:
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ski_aki_backfill.py:212: {_commit_err}", exc_info=True)
            raise
        logger.info(f"SKI/AKI chain repair: re-chained {stats['rechained_cas']} CAs, {stats['rechained_certs']} certs, deduplicated {stats['deduplicated']} CAs")

    # Phase 5: Populate subject_cn for certificates missing it
    certs_missing_cn = Certificate.query.filter(
        (Certificate.subject_cn.is_(None)) | (Certificate.subject_cn == '')
    ).all()
    for cert in certs_missing_cn:
        cn = None
        # Try extracting from subject string
        if cert.subject:
            import re
            m = re.search(r'CN=([^,]+)', cert.subject)
            if m:
                cn = m.group(1).strip()
        # Try extracting from PEM
        if not cn and cert.crt:
            try:
                pem_bytes = base64.b64decode(cert.crt)
                x509_cert = x509.load_pem_x509_certificate(pem_bytes, default_backend())
                for attr in x509_cert.subject:
                    if attr.oid == x509.oid.NameOID.COMMON_NAME:
                        cn = attr.value
                        break
            except Exception:
                pass
        if not cn:
            cn = cert.descr
        if cn:
            cert.subject_cn = cn
            stats.setdefault('populated_cn', 0)
            stats['populated_cn'] += 1
    if certs_missing_cn:
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ski_aki_backfill.py:245: {_commit_err}", exc_info=True)
            raise
        if stats.get('populated_cn'):
            logger.info(f"SKI/AKI backfill: populated subject_cn for {stats['populated_cn']} certificates")

    # Count remaining orphans after repair (certs with invalid/missing caref)
    ca_refids_final = set(ca.refid for ca in CA.query.with_entities(CA.refid).all())
    stats['orphan_cas'] = CA.query.filter(
        CA.caref.is_(None) | (CA.caref == ''),
        CA.ski.isnot(None),
        CA.crt.isnot(None), CA.crt != '',
        CA.subject != CA.issuer
    ).count()
    orphan_cert_count = 0
    for cert in Certificate.query.filter(Certificate.aki.isnot(None)).all():
        if not cert.caref or cert.caref not in ca_refids_final:
            orphan_cert_count += 1
    stats['orphan_certs'] = orphan_cert_count

    # Store stats for API access
    _last_run_stats.update(stats)
    return stats


# Module-level dict to store last run stats for API access
_last_run_stats = {}


def get_last_run_stats():
    """Return stats from the last backfill run."""
    return dict(_last_run_stats)
