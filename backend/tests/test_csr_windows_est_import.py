"""EST and the smart import read a CSR whose BasicConstraints is CA:FALSE with a
path length, the way Windows clients write it."""
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from api import est_protocol
from services.smart_import.parser import SmartParser
from tests.test_csr_windows_basic_constraints import _windows_shaped_csr

CN = 'win-est.example.test'


def _csr():
    return _windows_shaped_csr(rsa.generate_private_key(65537, 2048), CN)


def test_est_reads_the_san_of_a_windows_csr():
    assert est_protocol._san_values(_csr()) == {('DNSName', CN)}


def test_est_serverkeygen_copies_the_extensions_of_a_windows_csr():
    builder = x509.CertificateSigningRequestBuilder().subject_name(_csr().subject)
    builder = est_protocol._copy_csr_extensions(builder, _csr())
    rebuilt = builder.sign(rsa.generate_private_key(65537, 2048), hashes.SHA256())
    assert rebuilt.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
        .get_values_for_type(x509.DNSName) == [CN]
    assert rebuilt.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False


def test_import_detects_a_windows_csr_and_its_san():
    pem = _csr().public_bytes(serialization.Encoding.PEM).decode()
    csrs = [o for o in SmartParser().parse(pem) if o.type.name == 'CSR']
    assert len(csrs) == 1
    assert csrs[0].san_dns == [CN]
