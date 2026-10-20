"""Persistent revocation records (PLANB-B.1: modèle à implémenter selon SPEC, §3.3)."""
from models import db  # PLANB-B.1: seuls le nom de table et la clé primaire sont posés ici
class RevokedSerial(db.Model):  # PLANB-B.1: colonnes, défauts et to_dict du §3.3
    __tablename__ = 'revoked_serials'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
