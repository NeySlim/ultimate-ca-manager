"""
Migration 036: Rename 'User' system role to 'Viewer' and add 'Auditor' role
"""


def upgrade(conn):
    # Rename the 'User' system role to 'Viewer'
    conn.execute(
        "UPDATE pro_custom_roles SET name = 'Viewer', description = 'Basic read access to certificates and CAs' "
        "WHERE name = 'User' AND is_system = 1"
    )

    # Update Viewer permissions to match new restricted set
    import json
    viewer_perms = json.dumps([
        "read:dashboard", "read:certificates", "read:cas", "read:csrs",
        "read:templates", "read:truststore"
    ])
    conn.execute(
        "UPDATE pro_custom_roles SET permissions = ? WHERE name = 'Viewer' AND is_system = 1",
        (viewer_perms,)
    )

    # Add Auditor system role if it doesn't exist
    existing = conn.execute(
        "SELECT id FROM pro_custom_roles WHERE name = 'Auditor'"
    ).fetchone()

    if not existing:
        auditor_perms = json.dumps([
            "read:dashboard", "read:certificates", "read:cas", "read:csrs",
            "read:templates", "read:truststore", "read:crl", "read:acme",
            "read:scep", "read:hsm", "read:policies", "read:approvals",
            "read:audit", "read:groups"
        ])
        conn.execute(
            "INSERT INTO pro_custom_roles (name, description, permissions, is_system) "
            "VALUES ('Auditor', 'Read-only access to all operational data for compliance and audit', ?, 1)",
            (auditor_perms,)
        )

    conn.commit()


def downgrade(conn):
    import json

    # Rename back
    conn.execute(
        "UPDATE pro_custom_roles SET name = 'User', description = 'Basic read access to certificates' "
        "WHERE name = 'Viewer' AND is_system = 1"
    )

    # Restore old permissions
    old_perms = json.dumps(["read:dashboard", "read:certificates", "read:cas", "read:templates"])
    conn.execute(
        "UPDATE pro_custom_roles SET permissions = ? WHERE name = 'User' AND is_system = 1",
        (old_perms,)
    )

    # Remove Auditor
    conn.execute("DELETE FROM pro_custom_roles WHERE name = 'Auditor' AND is_system = 1")

    conn.commit()
