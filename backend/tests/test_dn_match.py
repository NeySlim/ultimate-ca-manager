"""Distinguished names compared as RFC 5280 §7.1 asks (utils.dn_match), and the key the
certificates index holds them by, written with crt."""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import NameOID

from utils.dn_match import name_key, same_name

CN, OU, DC, EMAIL, SERIAL = (NameOID.COMMON_NAME, NameOID.ORGANIZATIONAL_UNIT_NAME, NameOID.DOMAIN_COMPONENT,
                             NameOID.EMAIL_ADDRESS, NameOID.SERIAL_NUMBER)


def _name(*attrs):
    return x509.Name([x509.NameAttribute(oid, value, *rest) for oid, value, *rest in attrs])


@pytest.mark.parametrize('a,b', [
    (_name((CN, 'John Smith')), _name((CN, 'john smith'))),
    (_name((CN, 'John Smith')), _name((CN, '  John   Smith '))),
    (_name((CN, 'John Smith')), _name((CN, 'John Smith'))),
    (_name((CN, 'Straße')), _name((CN, 'STRASSE'))),
    (_name((CN, 'Ｊｏｈｎ')), _name((CN, 'john'))),
    (_name((CN, 'Jo­hn')), _name((CN, 'John'))),
    (_name((CN, 'PC1')), _name((CN, 'pc1', _ASN1Type.PrintableString))),
    (_name((CN, 'pc1'), (DC, 'Example'), (DC, 'TEST')), _name((CN, 'PC1'), (DC, 'example'), (DC, 'test'))),
    (_name((EMAIL, 'alice@EXAMPLE.test')), _name((EMAIL, 'alice@example.TEST'))),
    (x509.Name([x509.RelativeDistinguishedName([x509.NameAttribute(CN, 'a'), x509.NameAttribute(OU, 'b')])]),
     x509.Name([x509.RelativeDistinguishedName([x509.NameAttribute(OU, 'B'), x509.NameAttribute(CN, 'A')])])),
], ids=['case', 'spaces', 'nbsp', 'fold', 'nfkc', 'soft-hyphen', 'string-type', 'dc', 'email-host', 'rdn-set'])
def test_names_equal_under_rfc_5280(a, b):
    assert same_name(a, b) and name_key(a) == name_key(b)


@pytest.mark.parametrize('a,b', [
    (_name((CN, 'John Smith')), _name((CN, 'John Smyth'))),
    (_name((CN, 'John Smith')), _name((CN, 'JohnSmith'))),
    (_name((CN, 'a'), (OU, 'b')), _name((OU, 'b'), (CN, 'a'))),
    (_name((CN, 'a')), _name((CN, 'a'), (OU, 'b'))),
    (_name((CN, 'a')), _name((OU, 'a'))),
    (_name((EMAIL, 'Alice@example.test')), _name((EMAIL, 'alice@example.test'))),
    (_name((SERIAL, 'ab12', _ASN1Type.IA5String)), _name((SERIAL, 'AB12', _ASN1Type.IA5String))),
    (_name((CN, 'a'), (OU, 'b')),
     x509.Name([x509.RelativeDistinguishedName([x509.NameAttribute(CN, 'a'), x509.NameAttribute(OU, 'b')])])),
], ids=['letter', 'space-removed', 'rdn-order', 'one-more-rdn', 'type', 'email-local', 'ia5-exact', 'rdn-split'])
def test_names_that_differ(a, b):
    assert not same_name(a, b) and name_key(a) != name_key(b)


def test_the_listener_writes_the_key_with_crt(app):
    import base64
    import datetime
    from cryptography.hazmat.primitives import hashes, serialization
    from models import Certificate
    key = ec.generate_private_key(ec.SECP256R1())
    subject = _name((CN, 'Key Follows Crt'))
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    row = Certificate(refid='dnmatch1', descr='x')
    row.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
    assert row.subject_key == name_key(_name((CN, 'key follows crt')))
    row.crt = base64.b64encode(b'not a certificate').decode()
    assert row.subject_key == name_key(subject)  # an unreadable crt changes nothing, as for the other columns
