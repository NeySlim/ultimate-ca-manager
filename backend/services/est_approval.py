"""EST requests held for approval (RFC 7030 §4.2.3).

An approved enrolment or re-enrolment is signed at once, as the EST route
would have; the client receives it when it sends the same request again. A
server key generation is approved only: its key is generated when the
client comes back, so no private key waits in the database.
"""
from cryptography import x509

from models import CA, Certificate, db
from services import protocol_approval
from services.protocol_approval import ProtocolRequestGone


def _issue(approval, data):
    if data.get('operation') == 'serverkeygen':
        return {'id': None, 'cn': data.get('cn'), 'protocol': 'est', 'deferred': True}
    from api.est_protocol import sign_est_csr
    ca = db.session.get(CA, int(data['ca_id'])) if data.get('ca_id') is not None else None
    if ca is None:
        raise ProtocolRequestGone('The EST CA no longer exists', refusal=protocol_approval.ISSUANCE_REFUSAL)
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    renewal_of = supersedes = None
    if data.get('operation') == 'reenroll':
        from services.cert.issued_lookup import OK, protocol_renewal_status
        renewal_of = x509.load_pem_x509_certificate(data['renewal_of'].encode())
        supersedes, status = protocol_renewal_status(ca, renewal_of)
        if status != OK:
            raise ProtocolRequestGone(f'The certificate being renewed can no longer be renewed ({status})',
                                      refusal=protocol_approval.ISSUANCE_REFUSAL)
    from services.ad_connector.renewal_identity import RenewalAccountGone
    try:
        pem, _serial = sign_est_csr(ca, csr, renewal_of=renewal_of, supersedes=supersedes,
                                    on_stored=protocol_approval.linker(approval))
    except RenewalAccountGone as e:
        raise ProtocolRequestGone(f'The EST request can no longer be issued: {e}',
                                  refusal=protocol_approval.ISSUANCE_REFUSAL) from e
    serial = x509.load_pem_x509_certificate(pem.encode()).serial_number
    row = Certificate.query.filter_by(serial_number=str(serial), caref=ca.refid).first()
    return {'id': row.id if row is not None else None, 'cn': data.get('cn'), 'protocol': 'est',
            'serial_number': row.serial_number if row is not None else None}


def _gone(approval, data):
    if data.get('ca_id') is None or db.session.get(CA, int(data['ca_id'])) is None:
        return 'The EST CA no longer exists'
    return None


protocol_approval.register('est_enroll', _issue, gone=_gone)

