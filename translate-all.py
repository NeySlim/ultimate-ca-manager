#!/usr/bin/env python3
"""
Quick translation helper for UCM wiki
Translates key French terms to English while preserving structure
"""

import re
import sys

# Translation dictionary for common terms
TRANSLATIONS = {
    # Navigation
    "Retour": "Back",
    "Suivant": "Next",
    "Précédent": "Previous",
    
    # Common words
    "Bienvenue": "Welcome",
    "Guide": "Guide",
    "Manuel": "Manual",
    "Documentation": "Documentation",
    "Installation": "Installation",
    "Configuration": "Configuration",
    "Utilisation": "Usage",
    "Démarrage": "Start",
    "Rapide": "Quick",
    "Premiers pas": "First steps",
    "configuration initiale": "initial configuration",
    
    # Sections
    "Table des Matières": "Table of Contents",
    "Fonctionnalité": "Feature",
    "Gestion": "Management",
    "Opérations": "Operations",
    "Support": "Support",
    "Dépannage": "Troubleshooting",
    "Questions": "Questions",
    "fréquemment posées": "Frequently Asked",
    
    # Technical
    "Certificat": "Certificate",
    "Certificats": "Certificates",
    "Autorité": "Authority",
    "Émission": "Issuance",
    "Révocation": "Revocation",
    "Renouvellement": "Renewal",
    "Serveur": "Server",
    "Client": "Client",
    
    # Actions
    "Créer": "Create",
    "Modifier": "Modify",
    "Supprimer": "Delete",
    "Exporter": "Export",
    "Importer": "Import",
    "Télécharger": "Download",
    "Installer": "Install",
    
    # Status
    "actif": "active",
    "révoqué": "revoked",
    "expiré": "expired",
    "valide": "valid",
}

def translate_file(input_path, output_path):
    """Basic translation keeping structure"""
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Keep code blocks unchanged
    code_blocks = []
    def save_code(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks)-1}__"
    
    content = re.sub(r'```.*?```', save_code, content, flags=re.DOTALL)
    
    #Simple word replacement for common terms
    for fr, en in TRANSLATIONS.items():
        content = re.sub(r'\b' + re.escape(fr) + r'\b', en, content)
    
    # Restore code blocks
    for i, block in enumerate(code_blocks):
        content = content.replace(f"__CODE_BLOCK_{i}__", block)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: translate-all.py input.md output.md")
        sys.exit(1)
    
    translate_file(sys.argv[1], sys.argv[2])
    print(f"✅ Translated {sys.argv[1]} -> {sys.argv[2]}")
