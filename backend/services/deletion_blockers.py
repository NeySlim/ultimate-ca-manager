"""What forbids deleting a resource, written once for both delete paths.

Every deletable resource is reachable through two routes: `DELETE /<id>` and
`POST /bulk/delete`. They answer differently -- one an HTTP status, the other
a per-item entry in a `failed` list -- but the *question* they ask is the same:
may this row go? Asking it twice is how the two drifted. A template bound to a
SCEP profile was refused by the unit route and deleted by the bulk one, which
left the profile pointing at an id SQLite hands to the next template created.

So the question lives here and the answer is rendered by the caller. A blocker
carries both wordings because the two routes have always phrased them
differently and their clients read those strings; single-sourcing the *set* of
blockers is the point, not re-wording the messages.

The functions are generators: a caller that only needs the first blocker does
not pay for the queries behind the others, which is what the unit routes did
when they checked conditions one at a time.
"""

from dataclasses import dataclass
from typing import Iterator, Optional

from models import CA, Certificate, db
from models.policy import CertificatePolicy
from utils.datetime_utils import utc_now

# Bulk id lists are capped so one request cannot turn into an unbounded number
# of per-item transactions and audit entries. 100 is the cap the CA bulk routes
# have always published; the other bulk routes had none at all.
MAX_BULK_IDS = 100


@dataclass(frozen=True)
class DeletionBlocker:
    """One reason a row may not be deleted.

    `status` and `message` are what the unit route answers with; `brief` is the
    shorter phrasing the bulk routes put in their per-item `failed` entries.
    """

    status: int
    message: str
    brief: str


def first_blocker(blockers: Iterator[DeletionBlocker]) -> Optional[DeletionBlocker]:
    """The first blocker, or None when the row may go."""
    return next(iter(blockers), None)


def parse_bulk_ids(data):
    """Validate the `{ids: [...]}` body shared by every bulk route.

    Returns `(ids, None)` or `(None, flask_response)`. The messages are the
    ones the CA bulk routes already returned -- the other routes accepted
    anything truthy, so a JSON string was iterated character by character and
    an id list of any length became that many transactions.
    """
    from utils.response import error_response

    if not data or not data.get('ids'):
        return None, error_response('ids array required', 400)
    ids = data['ids']
    if not isinstance(ids, list):
        return None, error_response('ids must be an array', 400)
    if len(ids) > MAX_BULK_IDS:
        return None, error_response(
            f'Too many ids (max {MAX_BULK_IDS} per request)', 400)
    return ids, None


def ca_deletion_blockers(ca) -> Iterator[DeletionBlocker]:
    """Why this certificate authority may not be deleted."""
    child_cas = CA.query.filter_by(caref=ca.refid).count()
    if child_cas > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: {child_cas} intermediate CA(s) depend on it. '
            'Delete them first.',
            f'{child_cas} intermediate CA(s) depend on it',
        )

    issued_certs = Certificate.query.filter_by(caref=ca.refid).count()
    if issued_certs > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: {issued_certs} certificate(s) were issued by '
            'it. Revoke and delete them first.',
            f'{issued_certs} certificate(s) issued by it',
        )
    # Bindings that name the authority by foreign key: PostgreSQL refuses the
    # delete outright, SQLite would leave them pointing at nothing.
    from models.scep import ScepProfile
    scep_profiles = ScepProfile.query.filter_by(ca_refid=ca.refid).count()
    if scep_profiles > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: {scep_profiles} SCEP profile(s) issue from it. '
            'Rebind or delete them first.',
            f'{scep_profiles} SCEP profile(s) issue from it',
        )
    from models.acme_models import AcmeDomain, AcmeLocalDomain
    acme_domains = (AcmeDomain.query.filter_by(issuing_ca_id=ca.id).count()
                    + AcmeLocalDomain.query.filter_by(issuing_ca_id=ca.id).count())
    if acme_domains > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: {acme_domains} ACME domain(s) issue from it. '
            'Point them at another CA first.',
            f'{acme_domains} ACME domain(s) issue from it',
        )
    from models.policy import CertificatePolicy
    policies = CertificatePolicy.query.filter_by(ca_id=ca.id).count()
    if policies > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: {policies} issuance policy(ies) are scoped to it. '
            'Rescope or delete them first.',
            f'{policies} issuance policy(ies) scoped to it',
        )
    # Kept as a bare id: SQLite may hand it to the next CA created (#426)
    from models.system_config import SystemConfig
    scep_default = SystemConfig.query.filter_by(key='scep_ca_id').first()
    if scep_default and scep_default.value in (str(ca.id), ca.refid):
        yield DeletionBlocker(
            409,
            'Cannot delete CA: it is the default SCEP CA. '
            'Choose another one in the SCEP settings first.',
            'default SCEP CA',
        )
    from models.deploy import CRLDeployBinding
    crl_bindings = CRLDeployBinding.query.filter_by(ca_id=ca.id).count()
    if crl_bindings > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete CA: its CRL is deployed to {crl_bindings} target(s). '
            'Remove the CRL deployment binding(s) first.',
            f'CRL deployed to {crl_bindings} target(s)',
        )


def certificate_deletion_blockers(cert) -> Iterator[DeletionBlocker]:
    """Why this certificate may not be deleted.

    A certificate still trusted by relying parties must be revoked first, so
    that the CRL and the OCSP responder carry the withdrawal. Deleting it
    instead makes it disappear from UCM while remaining valid everywhere else.
    """
    if cert.crt and not cert.revoked:
        if not cert.valid_to or cert.valid_to >= utc_now():
            yield DeletionBlocker(
                409,
                'Cannot delete a valid certificate: revoke it first so the '
                'CRL and OCSP responder reflect the change.',
                'Cannot delete a valid certificate: revoke it first',
            )


def template_deletion_blockers(template) -> Iterator[DeletionBlocker]:
    """Why this certificate template may not be deleted.

    SCEP profiles and ACME profiles keep only the numeric id, with no foreign
    key: a binding left behind silently applies whichever template is created
    under that id next.
    """
    if template.is_system:
        yield DeletionBlocker(
            403, 'Cannot delete system templates', 'Cannot delete system template')
        return

    template_id = template.id

    cert_count = Certificate.query.filter_by(template_id=template_id).count()
    if cert_count > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete: template is used by {cert_count} certificate(s)',
            f'In use by {cert_count} certificate(s)',
        )

    policy_count = CertificatePolicy.query.filter_by(template_id=template_id).count()
    if policy_count > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete: template is used by {policy_count} policy/policies',
            f'In use by {policy_count} policy/policies',
        )

    from models.scep import ScepProfile
    scep_count = ScepProfile.query.filter_by(template_id=template_id).count()
    if scep_count > 0:
        yield DeletionBlocker(
            409,
            f'Cannot delete: template is bound to {scep_count} SCEP '
            'profile(s); unbind it first',
            f'Bound to {scep_count} SCEP profile(s)',
        )

    from services.acme import profiles as acme_profiles
    bound_profiles = acme_profiles.profiles_bound_to_template(template_id)
    if bound_profiles:
        joined = ', '.join(bound_profiles)
        yield DeletionBlocker(
            409,
            'Cannot delete: template is bound to ACME profile(s) ' + joined,
            'Bound to ACME profile(s) ' + joined,
        )


def intune_app_deletion_blockers(app) -> Iterator[DeletionBlocker]:
    """Why this Intune app registration may not be deleted."""
    from models.scep import ScepProfile
    names = sorted(p.name for p in ScepProfile.query.filter_by(intune_app_id=app.id))
    if names:
        yield DeletionBlocker(
            409,
            f"Cannot delete: the app registration is used by {len(names)} SCEP "
            f"profile(s): {', '.join(names)}. Point them at another one first.",
            f'Used by {len(names)} SCEP profile(s)',
        )


def purge_ca_dependents(ca) -> str:
    """Stage the rows that must not outlive a CA, and say what was staged.

    Deleting these was the unit route's job and the bulk route never learned
    it. `revoked_serials` is the one that matters: the rows deliberately
    outlive the certificate they describe, so an authority with no
    certificates left can still own them, and they carry a real foreign key
    to `certificate_authorities.refid`. Left behind they either refuse the
    delete outright on PostgreSQL or, on SQLite where foreign keys are not
    enforced, keep being emitted into CRLs for an authority that is gone.
    """
    from models.crl import CRLMetadata
    from models.ocsp import OCSPResponse
    from models.revoked_serial import RevokedSerial
    from models.scep import SCEPRequest

    from models.ca_cross_certificate import CACrossCertificate

    CACrossCertificate.query.filter_by(ca_id=ca.id).delete()
    crl_count = CRLMetadata.query.filter_by(ca_id=ca.id).delete()
    ocsp_count = OCSPResponse.query.filter_by(ca_id=ca.id).delete()
    rs_count = RevokedSerial.query.filter_by(caref=ca.refid).delete()
    # The enrolment history of the authority: same foreign key, same fate.
    scep_count = SCEPRequest.query.filter_by(ca_refid=ca.refid).delete()

    if crl_count or ocsp_count or rs_count or scep_count:
        return (f"Deleted {crl_count} CRL(s), {ocsp_count} OCSP response(s), "
                f"{rs_count} revoked serial(s) and {scep_count} SCEP request(s)")
    return ''
