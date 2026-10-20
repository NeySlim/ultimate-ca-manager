"""Migration 078 (PLANB-B.1): revocation records table and renewal columns.
À implémenter selon SPEC (§2, §3.2, §3.3). Même nom de fichier : le suivi des
migrations se fait par nom, une base qui l'a déjà appliquée ne la rejoue pas."""
pg_compatible = True  # PLANB-B.1: SQLite et PostgreSQL
def upgrade(conn):  # PLANB-B.1: table, index et colonnes, idempotent
    raise NotImplementedError('PLANB-B.1: migration 078 upgrade')
def downgrade(conn):  # PLANB-B.1: retrait selon le moteur
    raise NotImplementedError('PLANB-B.1: migration 078 downgrade')
