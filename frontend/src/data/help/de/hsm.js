export default {
  helpContent: {
    title: 'Hardware-Sicherheitsmodule',
    subtitle: 'Externe Schlüsselspeicherung',
    overview: 'Integration mit Hardware-Sicherheitsmodulen für sichere Speicherung privater Schlüssel. Unterstützung für PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS und OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Unterstützte Anbieter',
        definitions: [
          { term: 'PKCS#11', description: 'Industriestandard-HSM-Schnittstelle (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Services Cloud-basiertes HSM' },
          { term: 'Azure Key Vault', description: 'Microsoft Azure verwalteter Schlüsselspeicher' },
          { term: 'Google KMS', description: 'Google Cloud Key Management Service' },
          { term: 'OpenBao / Vault Transit', description: 'OpenBao- oder Vault-Transit-Secrets-Engine für Schlüsselverwaltung als Dienst' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Anbieter hinzufügen', text: 'Verbindung zu einem HSM konfigurieren (Bibliothekspfad, Anmeldedaten, Slot)' },
          { label: 'Verbindung testen', text: 'Überprüfen, ob das HSM erreichbar ist und die Anmeldedaten gültig sind' },
          { label: 'Schlüssel generieren', text: 'Ein neues Schlüsselpaar direkt auf dem HSM erstellen' },
          { label: 'Status', text: 'Verbindungszustand des Anbieters überwachen' },
          { label: 'Zertifizierung', text: 'Die Zertifizierung des HSM angeben: Common Criteria EAL 4+, EUCC high, FIPS 140-3 Level 3, FIPS 140-2 Level 3 oder andere. Bleibt das Feld leer, ist sie nicht angegeben. Das Compliance-Profil eu-acm akzeptiert für eine HSM-gestützte CA nur Common Criteria EAL 4+, EUCC high und FIPS 140-3 Level 3 (bis 31. Dezember 2030)' },
        ]
      },
      {
        title: 'HSM-gestützte CAs (v2.130+)',
        content: 'Sobald ein Provider konfiguriert ist, können Sie den privaten Schlüssel einer CA bei der Erstellung an diesen HSM binden:',
        items: [
          { label: 'Key-Storage-Toggle', text: 'Im CA-Erstellungsformular Local (in DB verschlüsselt) oder HSM wählen. Provider + Key-Label auswählen' },
          { label: 'Signaturpfad', text: 'Jede Ausstellung, CRL- und OCSP-Signatur dieser CA läuft über den HSM, der Schlüssel verlässt ihn nie' },
          { label: 'Export-Einschränkungen', text: 'PKCS#12-, JKS- und Key-only-Exporte sind für HSM-CAs deaktiviert (nur das öffentliche Zertifikat / die Chain können exportiert werden)' },
          { label: 'CRL & OCSP', text: 'Beide funktionieren transparent mit HSM-CAs (signiert via HSM)' },
          { label: 'Migration', text: 'Bestehende lokale CAs können nach der Erstellung nicht in einen HSM verschoben werden, bei der Erstellung wählen' },
        ]
      },

    ],
    tips: [
      'Verwenden Sie SoftHSM zum Testen, bevor Sie mit einem physischen HSM bereitstellen',
      'Auf einem HSM generierte Schlüssel verlassen niemals die Hardware: sie können nicht exportiert werden',
      'Testen Sie die Verbindung, bevor Sie einen HSM-Anbieter für die CA-Signierung verwenden',
      'Für langlebige Root-CAs in Produktion HSM-gestützte Schlüsselablage bevorzugen',
    ],
    warnings: [
      'Die angegebene Zertifizierung ist die Aussage des Betreibers über das HSM: UCM prüft die Hardware nicht. An eIDAS ausgerichtete Profile lesen sie, um den Schutz des CA-Schlüssels zu prüfen',
      'Falsche HSM-Anbieter-Konfiguration kann die Zertifikatssignierung verhindern',
      'Der Verlust des Zugangs zum HSM bedeutet den Verlust der dort gespeicherten Schlüssel',
    ],
  },
  helpGuides: {
    title: 'Hardware-Sicherheitsmodule',
    content: `
## Übersicht

Hardware-Sicherheitsmodule (HSMs) bieten manipulationssichere Speicherung für kryptografische Schlüssel. Private Schlüssel, die auf einem HSM gespeichert sind, verlassen niemals die Hardware und bieten so das höchste Maß an Schlüsselschutz.

## Unterstützte Anbieter

### PKCS#11
Die Industriestandard-HSM-Schnittstelle. Unterstützte Geräte:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (softwarebasiert, zum Testen)
- Jedes PKCS#11-kompatible Gerät

> 💡 **Docker**: SoftHSM ist im Docker-Image vorinstalliert. Beim ersten Start wird automatisch ein Standard-Token initialisiert und als \`SoftHSM-Default\`-Anbieter registriert, sofort einsatzbereit.

Konfiguration:
- **Bibliothekspfad**: Pfad zur PKCS#11-Shared-Library (.so/.dll)
- **Slot**: HSM-Slotnummer
- **PIN**: Benutzer-PIN zur Authentifizierung

### AWS CloudHSM
Amazon Web Services Cloud-basiertes HSM:
- **Cluster-ID**: CloudHSM-Cluster-Kennung
- **Token-Label**: Label des PKCS#11-Tokens von CloudHSM
- **Crypto-Benutzer / Crypto-Passwort**: der Crypto-Benutzer (CU), mit dem sich UCM anmeldet; ein AWS-Zugriffsschlüssel ist nicht nötig

### Azure Key Vault
Microsoft Azure verwalteter Schlüsselspeicher:
- **Vault-URL**: Azure Key Vault-Endpunkt
- **Mandanten-ID**: Azure AD-Mandant
- **Client-ID/Geheimnis**: Dienstprinzipal-Anmeldedaten

### Google Cloud KMS
Google Cloud Key Management Service:
- **Projekt**: GCP-Projekt-ID
- **Standort**: KMS-Schlüsselring-Standort
- **Schlüsselring**: Name des Schlüsselrings
- **Anmeldedaten**: Dienstkonto-JSON-Schlüssel

### OpenBao / Vault Transit
OpenBao- oder HashiCorp Vault Transit Secrets Engine. Schlüssel werden remote über die Transit-API verwaltet: keine PKCS#11-Bibliothek erforderlich.

Konfiguration:
- **URL**: Serveradresse (z.B. \`https://openbao.example.com:8200\`)
- **Token**: Authentifizierungstoken
- **Mount-Pfad**: Transit-Engine-Mountpoint (Standard: \`transit\`)
- **Namespace**: Optionaler Namespace für Multi-Tenant-Setups
- **TLS-Überprüfung überspringen**: TLS-Zertifikatsprüfung überspringen (für selbstsignierte Zertifikate)

Unterstützte Schlüsseltypen:
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- AES-256-GCM (symmetrisch)

> 💡 OpenBao ist ein Community-Fork von HashiCorp Vault. UCM funktioniert mit beiden.

## Anbieter verwalten

### Anbieter hinzufügen
1. Klicken Sie auf **Anbieter hinzufügen**
2. Wählen Sie den **Anbietertyp**
3. Geben Sie die Verbindungsdetails ein
4. Klicken Sie auf **Verbindung testen** zur Überprüfung
5. Klicken Sie auf **Speichern**

### Verbindung testen
Testen Sie die Verbindung immer nach dem Erstellen oder Ändern eines Anbieters. UCM überprüft, ob es mit dem HSM kommunizieren und sich authentifizieren kann.

### Anbieterstatus
Jeder Anbieter zeigt einen Verbindungsstatusindikator:
- **Verbunden**: HSM ist erreichbar und authentifiziert
- **Getrennt**: HSM nicht erreichbar
- **Fehler**: Authentifizierungs- oder Konfigurationsproblem

## Schlüsselverwaltung

### Schlüssel generieren
1. Wählen Sie einen verbundenen Anbieter
2. Klicken Sie auf **Schlüssel generieren**
3. Wählen Sie den Algorithmus (RSA 2048/4096, ECDSA P-256/P-384)
4. Geben Sie ein Schlüssel-Label/Alias ein
5. Klicken Sie auf **Generieren**

Der Schlüssel wird direkt auf dem HSM erstellt. UCM speichert nur eine Referenz.

### HSM-Schlüssel verwenden
Wählen Sie beim Erstellen einer CA einen HSM-Anbieter und -Schlüssel anstatt einen Software-Schlüssel zu generieren. Die Signierungsvorgänge der CA werden auf dem HSM ausgeführt.

> ⚠ Auf einem HSM generierte Schlüssel können nicht exportiert werden. Wenn Sie den Zugang zum HSM verlieren, verlieren Sie die Schlüssel.

> 💡 Verwenden Sie SoftHSM für Entwicklung und Tests, bevor Sie mit physischen HSMs bereitstellen.
`
  }
}
