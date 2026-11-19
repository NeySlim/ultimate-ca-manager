export default {
  helpContent: {
    title: 'Import & Export',
    subtitle: 'Datenmigration und Sicherung',
    overview: 'Importieren Sie Zertifikate aus externen Quellen und exportieren Sie Ihre PKI-Daten. Smart Import erkennt Dateitypen automatisch. Die OPNsense-Integration importiert die Zertifikate und CAs einer Firewall auf Abruf.',
    sections: [
      {
        title: 'Import',
        items: [
          { label: 'Smart Import', text: 'Laden Sie eine beliebige Zertifikatsdatei hoch, UCM erkennt automatisch das Format (PEM, DER, P12, P7B)' },
          { label: 'OPNsense-Import', text: 'Verbinden Sie sich mit einer OPNsense-Firewall und importieren Sie deren Zertifikate und CAs, einmal pro Durchlauf (keine laufende Synchronisation)' },
        ]
      },
      {
        title: 'Export',
        items: [
          { label: 'Zertifikate exportieren', text: 'Zertifikate als PEM- oder PKCS#7-Bündel herunterladen' },
          { label: 'CAs exportieren', text: 'CA-Zertifikate und -Ketten herunterladen' },
        ]
      },
      {
        title: 'OPNsense-Integration',
        items: [
          { label: 'Verbindung', text: 'OPNsense-Host und Port, API-Schlüssel und API-Geheimnis angeben' },
          { label: 'Verbindung testen', text: 'Konnektivität vor dem Import überprüfen' },
          { label: 'Elemente auswählen', text: 'Auswählen, welche Zertifikate und CAs importiert werden sollen' },
        ]
      },
    ],
    tips: [
      'Smart Import verarbeitet PEM-Bündel mit mehreren Zertifikaten in einer einzelnen Datei',
      'Testen Sie die OPNsense-Verbindung, bevor Sie einen vollständigen Import durchführen',
      'PKCS#12-Dateien erfordern das korrekte Passwort zum Import privater Schlüssel',
      'Post-Quanten-Zertifikate (ML-DSA, SLH-DSA) und ML-DSA-Schlüssel werden als PEM oder DER importiert, die Zertifikate tragen ein Post-Quanten-Badge; UCM kann einen ML-DSA-Schlüssel noch nicht aus einer PKCS#12-Datei lesen',
    ],
  },
  helpGuides: {
    title: 'Import & Export',
    content: `
## Übersicht

Importieren Sie Zertifikate aus externen Quellen und exportieren Sie Ihre PKI-Daten für Sicherung oder Migration.

## Smart Import

Der Smart-Import-Assistent erkennt Dateitypen automatisch und verarbeitet sie:

### Unterstützte Formate
- **PEM**: Einzelne oder gebündelte Zertifikate, CAs und Schlüssel
- **DER**: Binäres Zertifikat oder Schlüssel
- **PKCS#12 (P12/PFX)**: Zertifikat + Schlüssel + Kette (erfordert Passwort)
- **PKCS#7 (P7B)**: Zertifikatskette ohne Schlüssel

### Funktionsweise
1. Klicken Sie auf **Importieren** oder ziehen Sie Dateien in den Ablagebereich
2. UCM analysiert jede Datei und identifiziert deren Inhalte
3. Überprüfen Sie die erkannten Elemente (CAs, Zertifikate, Schlüssel)
4. Klicken Sie auf **Importieren**, um sie zu UCM hinzuzufügen

> 💡 Smart Import verarbeitet PEM-Bündel mit mehreren Zertifikaten in einer einzelnen Datei. Es unterscheidet automatisch zwischen CAs und Endentitätszertifikaten.

### Post-Quanten-Zertifikate
**ML-DSA**- (FIPS 204) und **SLH-DSA**-Zertifikate (FIPS 205) werden als PEM oder DER importiert, ebenso private ML-DSA-Schlüssel. Sie werden mit ihrer Sicherheitsstufe angezeigt, z. B. *ML-DSA-65 (Stufe 3)*, und tragen ein **Post-Quanten**-Badge. UCM kann einen ML-DSA-Schlüssel noch nicht aus einer PKCS#12-Datei lesen: Importieren Sie Zertifikat und Schlüssel als PEM.

## OPNsense-Integration

Importieren Sie Zertifikate und CAs von einer OPNsense-Firewall, auf Abruf (UCM hält sie nicht synchron):

### Einrichtung
1. Erstellen Sie in OPNsense einen API-Schlüssel (System → Zugang → Benutzer → API-Schlüssel)
2. Geben Sie in UCM den OPNsense-Host und -Port, den API-Schlüssel und das API-Geheimnis ein
3. Klicken Sie auf **Verbindung testen**: Es prüft die Verbindung und listet die verfügbaren Zertifikate und CAs auf

### Import
1. Wählen Sie die Elemente aus, die Sie importieren möchten
2. Klicken Sie auf **Ausgewählte importieren**

UCM importiert Zertifikate mit ihren privaten Schlüsseln (falls verfügbar) und bewahrt die CA-Hierarchie.

## Zertifikate exportieren

Massenexport aller Zertifikate:
- **PEM**: Alle Zertifikate in einem einzelnen PEM-Bündel
- **P7B-Bündel**: Alle Zertifikate in einer einzelnen PKCS#7-Datei

## CAs exportieren

Massenexport aller Zertifizierungsstellen:
- **PEM**: Zertifikatskette im PEM-Format
- **Vollständige Kette**: Root → Intermediate → Sub-CA

## Migration zwischen UCM-Instanzen

Für die Migration von einer UCM-Instanz zu einer anderen:
1. Erstellen Sie eine **Sicherung** auf der Quellinstanz (Einstellungen → Sicherung)
2. Installieren Sie UCM auf dem Ziel
3. **Stellen Sie** die Sicherung auf dem Ziel **wieder her**

Dies bewahrt alle Daten: Zertifikate, CAs, Schlüssel, Benutzer, Einstellungen und Audit-Protokolle.
`
  }
}
