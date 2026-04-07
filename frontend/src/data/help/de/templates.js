export default {
  helpContent: {
    title: 'Zertifikatstemplates',
    subtitle: 'Wiederverwendbare Zertifikatsprofile',
    overview: 'Definieren Sie wiederverwendbare Zertifikatsprofile mit vorkonfigurierten Betreffsfeldern, Key Usage, Extended Key Usage, Gültigkeitszeiträumen und anderen Erweiterungen. Wenden Sie Templates bei der Ausstellung oder Signierung von Zertifikaten an.',
    sections: [
      {
        title: 'Template-Typen',
        definitions: [
          { term: 'Endentität', description: 'Für Server-, Client-, Code-Signierungs- und E-Mail-Zertifikate' },
          { term: 'CA', description: 'Zum Erstellen von Intermediate-Zertifizierungsstellen' },
        ]
      },
      {
        title: 'Funktionen',
        items: [
          { label: 'Betreffsstandards', text: 'Organisation, OU, Land, Bundesland, Stadt vorausfüllen' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, usw.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Gültigkeit', text: 'Standard-Gültigkeitsdauer in Tagen' },
          { label: 'Duplizieren', text: 'Ein vorhandenes Template klonen und modifizieren' },
          { label: 'Import/Export', text: 'Templates als JSON-Dateien zwischen UCM-Instanzen teilen' },
        ]
      },
    ],
    tips: [
      'Erstellen Sie separate Templates für TLS-Server, Clients und Code-Signierung',
      'Verwenden Sie die Duplizieren-Aktion, um schnell Varianten eines Templates zu erstellen',
    ],
  },
  helpGuides: {
    title: 'Zertifikatstemplates',
    content: `
## Übersicht

Templates definieren wiederverwendbare Zertifikatsprofile. Anstatt Key Usage, Extended Key Usage, Gültigkeit und Betreffsfelder jedes Mal manuell zu konfigurieren, wenden Sie ein Template an, um alles vorzufüllen.

## Template-Typen

### Endentitäts-Templates
Für Serverzertifikate, Client-Zertifikate, Code-Signierung und E-Mail-Schutz. Diese Templates setzen typischerweise:
- **Key Usage** — Digital Signature, Key Encipherment
- **Extended Key Usage** — Server Auth, Client Auth, Code Signing, Email Protection

### CA-Templates
Zum Erstellen von Intermediate-CAs. Diese setzen:
- **Key Usage** — Certificate Sign, CRL Sign
- **Basic Constraints** — CA:TRUE, optionale Pfadlänge

## Template erstellen

1. Klicken Sie auf **Template erstellen**
2. Geben Sie einen **Namen** und eine optionale Beschreibung ein
3. Wählen Sie den Template-**Typ** (Endentität oder CA)
4. Konfigurieren Sie **Betreffsstandards** (O, OU, C, ST, L)
5. Wählen Sie **Key Usage**-Flags
6. Wählen Sie **Extended Key Usage**-Werte
7. Legen Sie die **Standard-Gültigkeitsdauer** in Tagen fest
8. Klicken Sie auf **Erstellen**

## Templates verwenden

Wählen Sie beim Ausstellen eines Zertifikats oder Signieren eines CSR ein Template aus der Dropdown-Liste. Das Template füllt vor:
- Betreffsfelder (die Sie überschreiben können)
- Key Usage und Extended Key Usage
- Gültigkeitsdauer

## Templates duplizieren

Klicken Sie auf **Duplizieren**, um eine Kopie eines vorhandenen Templates zu erstellen. Modifizieren Sie die Kopie, ohne das Original zu beeinflussen.

## Import & Export

### Export
Exportieren Sie Templates als JSON zum Teilen zwischen UCM-Instanzen.

### Import
Importieren Sie aus:
- **JSON-Datei** — Template-JSON-Datei hochladen
- **JSON einfügen** — JSON direkt in den Textbereich einfügen

## Gängige Template-Beispiele

### TLS-Server
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Gültigkeit: 365 Tage

### Client-Authentifizierung
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Gültigkeit: 365 Tage

### Code-Signierung
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Gültigkeit: 365 Tage
`
  }
}
