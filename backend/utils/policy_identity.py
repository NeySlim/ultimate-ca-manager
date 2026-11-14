"""The identity of an enrollment policy (MS-XCEP policyID, template OID root), held by its profile.

A profile created in 3.0 draws both at random; the 2.x derivation from a CA refid survives for
the values 2.254 served and for the template OIDs certificates issued before carry.
Pure functions: the model, migration 155 and the restore share them.
"""
import struct
import uuid

# Microsoft's template arc, under which AD CS mints its own template OIDs
TEMPLATE_OID_ARC = '1.3.6.1.4.1.311.21.8'
# The 2.x namespace: changing it changes every value derived from a CA
_LEGACY_NAMESPACE = uuid.UUID('a12b3c4d-5e6f-4789-9abc-def012345678')


def _root_of(seed):
    # Four uint32 arcs, never one 128-bit arc: certenroll drops a policy whose OID has one
    return '{}.{}.{}.{}.{}'.format(TEMPLATE_OID_ARC, *struct.unpack('>4I', seed.bytes))


def random_policy_id():
    return str(uuid.uuid4())


def random_oid_root():
    return _root_of(uuid.uuid4())


def derived_policy_id(refid):
    """The policyID 2.x served for the CA of *refid*."""
    return str(uuid.uuid5(_LEGACY_NAMESPACE, f'ucm-ca-policy-{refid}'))


def derived_oid_root(refid):
    """The template OID root 2.x derived from the CA of *refid*."""
    return _root_of(uuid.uuid5(_LEGACY_NAMESPACE, f'ucm-ca-{refid}'))


def template_oid(root, template_id):
    return f'{root}.1.{template_id}'


def identity_for(refid, taken_ids=(), taken_roots=()):
    """``(policy_id, oid_root)`` derived from the CA of *refid*, at random without one or when
    another profile already holds a derived value: two profiles never share an identity."""
    if refid:
        policy_id, root = derived_policy_id(refid), derived_oid_root(refid)
        if policy_id not in taken_ids and root not in taken_roots:
            return policy_id, root
    return random_policy_id(), random_oid_root()
