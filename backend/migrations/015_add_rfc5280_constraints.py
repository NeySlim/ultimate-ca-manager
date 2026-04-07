"""
Migration 015: RFC 5280 Extended Compliance

Adds support for 6 RFC 5280 features:

1. PathLength constraint (§4.2.1.9) — configurable BasicConstraints path length for CAs
2. NameConstraints (§4.2.1.10) — permitted/excluded DNS, IP, email domains for CAs
3. PolicyConstraints (§4.2.1.11) — requireExplicitPolicy + inhibitPolicyMapping
4. InhibitAnyPolicy (§4.2.1.11) — skip certs depth for anyPolicy inhibition
5. Subject Information Access (§4.2.2.2) — SIA URLs for CA cert/repo discovery
6. OCSP Must-Staple (RFC 6066 / TLS Feature) — TLS feature extension on end-entity certs

CA table additions:
  - path_length (INTEGER nullable) — BasicConstraints pathLenConstraint
  - name_constraints_permitted (TEXT/JSON) — permitted subtrees [{type, value}]
  - name_constraints_excluded (TEXT/JSON) — excluded subtrees [{type, value}]
  - policy_constraints_require (INTEGER nullable) — requireExplicitPolicy skip certs
  - policy_constraints_inhibit (INTEGER nullable) — inhibitPolicyMapping skip certs
  - inhibit_any_policy (INTEGER nullable) — inhibitAnyPolicy skip certs
  - sia_enabled (BOOLEAN) — enable SIA extension
  - sia_urls (TEXT/JSON) — SIA caRepository URLs

Certificate table additions:
  - ocsp_must_staple (BOOLEAN) — TLS Feature (status_request) extension
"""

import logging

logger = logging.getLogger(__name__)


def upgrade(conn):
    """Add RFC 5280 constraint columns."""
    ca_columns = [
        ("path_length", "INTEGER"),
        ("name_constraints_permitted", "TEXT"),
        ("name_constraints_excluded", "TEXT"),
        ("policy_constraints_require", "INTEGER"),
        ("policy_constraints_inhibit", "INTEGER"),
        ("inhibit_any_policy", "INTEGER"),
        ("sia_enabled", "BOOLEAN DEFAULT 0"),
        ("sia_urls", "TEXT"),
    ]

    cert_columns = [
        ("ocsp_must_staple", "BOOLEAN DEFAULT 0"),
    ]

    for col_name, col_type in ca_columns:
        try:
            conn.execute(f"ALTER TABLE certificate_authorities ADD COLUMN {col_name} {col_type}")
            logger.info(f"Added column certificate_authorities.{col_name}")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                logger.debug(f"Column certificate_authorities.{col_name} already exists")
            else:
                raise

    for col_name, col_type in cert_columns:
        try:
            conn.execute(f"ALTER TABLE certificates ADD COLUMN {col_name} {col_type}")
            logger.info(f"Added column certificates.{col_name}")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                logger.debug(f"Column certificates.{col_name} already exists")
            else:
                raise

    conn.commit()
    logger.info("Migration 015 complete: RFC 5280 extended compliance columns added")


def downgrade(conn):
    """SQLite doesn't support DROP COLUMN before 3.35.0, so we just log."""
    logger.warning("Migration 015 downgrade: columns cannot be removed in older SQLite versions")
