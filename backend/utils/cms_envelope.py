"""RSAES-OAEP helpers shared by the CMS envelopes UCM builds and reads (SCEP, EST)."""
import asn1crypto.algos
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

OAEP_HASHES = {
    "sha1": hashes.SHA1,
    "sha224": hashes.SHA224,
    "sha256": hashes.SHA256,
    "sha384": hashes.SHA384,
    "sha512": hashes.SHA512,
}


def oaep_parameters(params) -> tuple[str, str, bytes]:
    """(hash, MGF1 hash, label) of an RSAES-OAEP AlgorithmIdentifier.
    Absent parameters mean the RFC 3560 defaults: SHA-1, MGF1 with SHA-1, no label."""
    if params is None or not getattr(params, "contents", b""):
        return "sha1", "sha1", b""
    hash_name = params["hash_algorithm"]["algorithm"].native
    mgf = params["mask_gen_algorithm"]
    if mgf["algorithm"].native != "mgf1":
        raise ValueError("Unsupported OAEP mask generation function")
    if not getattr(mgf["parameters"], "contents", b""):
        raise ValueError("OAEP MGF1 without a digest")
    mgf_hash = mgf["parameters"]["algorithm"].native
    source = params["p_source_algorithm"]
    if source["algorithm"].native != "p_specified":
        raise ValueError("Unsupported OAEP label source")
    label = source["parameters"].native or b""
    return hash_name, mgf_hash, label


def oaep_padding(params) -> asym_padding.OAEP:
    """The cryptography padding matching an RSAES-OAEP AlgorithmIdentifier."""
    hash_name, mgf_hash, label = oaep_parameters(params)
    if label:
        raise ValueError("OAEP label is not supported")
    try:
        hash_cls, mgf_cls = OAEP_HASHES[hash_name], OAEP_HASHES[mgf_hash]
    except KeyError as e:
        raise ValueError(f"Unsupported OAEP digest: {e.args[0]}") from e
    return asym_padding.OAEP(
        mgf=asym_padding.MGF1(mgf_cls()), algorithm=hash_cls(), label=None
    )


def oaep_algorithm(hash_name: str, mgf_hash: str | None = None) -> dict:
    """RSAES-OAEP AlgorithmIdentifier (RFC 4055 §4.1); DER drops the SHA-1 defaults."""
    return {
        'algorithm': 'rsaes_oaep',
        'parameters': asn1crypto.algos.RSAESOAEPParams({
            'hash_algorithm': {'algorithm': hash_name},
            'mask_gen_algorithm': {
                'algorithm': 'mgf1', 'parameters': {'algorithm': mgf_hash or hash_name},
            },
        }),
    }
