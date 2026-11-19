export default {
  helpContent: {
    title: 'Vertrauensspeicher',
    subtitle: 'Vertrauenswürdige Zertifikate verwalten',
    overview: 'Hält vertrauenswürdige Root- und Intermediate-CA-Zertifikate. Die Kettenansicht eines Zertifikats und seine Exporte vervollständigen die Kette mit einem Zertifikat des Vertrauensspeichers, dessen Subject dem Ausstellernamen entspricht. Der Speicher kann aus dem Betriebssystem-Vertrauensspeicher oder aus den von UCM verwalteten CAs gefüllt werden.',
    sections: [
      {
        title: 'Zertifikatstypen',
        definitions: [
          { term: 'Root-CA', description: 'Selbstsignierter Vertrauensanker der obersten Ebene' },
          { term: 'Intermediate', description: 'CA-Zertifikat, signiert von einer Root- oder einer anderen Intermediate-CA' },
          { term: 'System', description: 'Aus dem Vertrauensspeicher des Betriebssystems importiert' },
          { term: 'Code-Signierung', description: 'Zertifikat zur Verifizierung von Code-Signaturen' },
          { term: 'E-Mail', description: 'Zertifikat für S/MIME' },
          { term: 'Benutzerdefiniert', description: 'Manuell kategorisiertes vertrauenswürdiges Zertifikat' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Hinzufügen', text: 'Zertifikate der von UCM verwalteten CAs hinzufügen. Ein externes Zertifikat wird über die API hinzugefügt (POST /api/v2/truststore mit PEM, oder /api/v2/truststore/import mit einer PEM- oder DER-Datei)' },
          { label: 'Vom System synchronisieren', text: 'Vertrauenswürdige CAs des Betriebssystems in UCM importieren, bis zur gewählten Anzahl (standardmäßig 500, höchstens 1000)' },
          { label: 'Exportieren', text: 'Vertrauenswürdige Zertifikate einzeln herunterladen' },
          { label: 'Auswahl löschen', text: 'Mehrere Zertifikate auswählen und gemeinsam entfernen, zum Beispiel die als abgelaufen gefilterten System-CAs; nur die Zeilen, die die aktuellen Filter anzeigen, werden entfernt' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie „Vom System synchronisieren", um den Vertrauensspeicher schnell mit CAs auf OS-Ebene zu füllen',
      'Filtern Sie nach Zweck, um sich auf bestimmte Zertifikatskategorien zu konzentrieren',
    ],
  },
  helpGuides: {
    title: 'Vertrauensspeicher',
    content: `
## Übersicht

Der Vertrauensspeicher hält vertrauenswürdige CA-Zertifikate. Füllen Sie ihn aus den von UCM verwalteten CAs oder aus dem Vertrauensspeicher des Betriebssystems.

## Zertifikatskategorien

- **Root-CA**: Selbstsignierte Vertrauensanker
- **Intermediate**: CAs, signiert von Root- oder anderen Intermediate-CAs
- **System**: Aus dem Vertrauensspeicher des Betriebssystems importiert
- **Code-Signierung**: Zertifikate zur Verifizierung von Code-Signaturen
- **E-Mail**: Zertifikate für S/MIME
- **Benutzerdefiniert**: Manuell kategorisierte Zertifikate

## Zertifikate hinzufügen

### Aus verwalteten CAs
**Hinzufügen** listet die von UCM verwalteten CAs auf: Wählen Sie die aus, denen vertraut werden soll.

### Externe Zertifikate
Die Seite hat kein Upload-Formular für ein Zertifikat von außerhalb von UCM. Fügen Sie es über die API hinzu: \`POST /api/v2/truststore\` mit seinem PEM, oder \`POST /api/v2/truststore/import\` mit einer PEM- oder DER-Datei.

### Vom System synchronisieren
Die vertrauenswürdigen CAs aus dem Vertrauensspeicher des Betriebssystems importieren (z.B. Mozillas CA-Bundle unter Linux), bis zur gewählten Anzahl: standardmäßig 500, höchstens 1000.

> 💡 Die Synchronisierung vom System ist ein einmaliger Import. Änderungen am OS-Vertrauensspeicher werden nicht automatisch übernommen.

## Einträge verwalten

- **Nach Zweck filtern**: Die Liste nach Zertifikatskategorie eingrenzen
- **Suche**: Zertifikate nach Betreffsname suchen
- **Exportieren**: Einzelne Zertifikate im PEM-Format herunterladen
- **Löschen**: Ein Zertifikat aus dem Vertrauensspeicher entfernen
- **Auswahl löschen**: Mehrere Zertifikate auswählen und gemeinsam entfernen, zum Beispiel die als abgelaufen gefilterten System-CAs; nur die Zeilen, die die aktuellen Filter anzeigen, werden entfernt

## Anwendungsfälle

### Ketten
Die Kettenansicht eines Zertifikats und seine Exporte mit Kette nehmen ein Zertifikat des Vertrauensspeichers, dessen Subject dem Ausstellernamen entspricht, um die Kette zu vervollständigen. Gegen den Vertrauensspeicher wird keine Signatur geprüft.

Der Vertrauensspeicher spielt weder bei der mTLS-Client-Authentifizierung (die die unter Einstellungen › Sicherheit gewählte vertrauenswürdige CA verwendet) noch bei der Verbindung des ACME-Clients zu seiner CA eine Rolle.
`
  }
}
