"""The key of a certificate or CSR as the API shows it, whatever pyca can load.

A post-quantum key carries its label in key_type and key_algorithm, no size
(key_size None) and its NIST security level; classical keys keep the
"<family> <size>" spelling of ``certificates.key_algo``.
"""
from utils import key_algorithms
from utils.foreign_algorithms import describe_public_key

UNREADABLE = {'key_type': 'N/A', 'key_algorithm': 'Unknown', 'key_size': 0,
              'security_level': None, 'post_quantum': False, 'verifiable': None}


def facts_for_key_type(key_type: str, verifiable: bool = True) -> dict:
    """Facts of a ``key_algo`` spelling; *verifiable* is False when pyca cannot load the key."""
    pq = key_algorithms.post_quantum_info(key_type)
    if pq:
        return {'key_type': pq.label, 'key_algorithm': pq.label, 'key_size': None,
                'security_level': pq.security_level, 'post_quantum': True, 'verifiable': verifiable}
    parts = (key_type or '').split()
    size = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    return {'key_type': key_type, 'key_algorithm': parts[0] if parts else 'Unknown', 'key_size': size,
            'security_level': None, 'post_quantum': False, 'verifiable': verifiable}


def _key_type(obj, foreign) -> str:
    if foreign:
        return f"{foreign['label']} {foreign['key_size']}" if foreign['key_size'] else foreign['label']
    return key_algorithms.key_algo_for_public_key(obj.public_key())


def key_type_of(obj) -> str:
    """``key_algo``-style spelling of the key of a certificate or CSR: 'RSA 2048',
    'ML-DSA-65', 'SLH-DSA-SHA2-128s', 'SM2 256'."""
    return _key_type(obj, describe_public_key(obj))


def key_facts(obj) -> dict:
    """key_type, key_algorithm, key_size, security_level, post_quantum and verifiable
    of the key of a certificate or CSR."""
    foreign = describe_public_key(obj)
    return facts_for_key_type(_key_type(obj, foreign), verifiable=foreign is None)


def public_key_fields(obj) -> dict:
    """``{'security_level', 'post_quantum'}`` to merge into a parser's key description."""
    facts = key_facts(obj)
    return {'security_level': facts['security_level'], 'post_quantum': facts['post_quantum']}
