"""Migration 069 (EAB domain restrictions): placeholder, see PLANB-E.1."""
# PLANB-E.1: à implémenter selon SPEC. Texte à réécrire, même nom de fichier ;
# no-op d'ici là pour que le reste du schéma migre.
pg_compatible = True  # PLANB-E.1 (placeholder)
#
#
def upgrade(conn) -> None:
    return None
#
#
def downgrade(conn) -> None:
    return None
