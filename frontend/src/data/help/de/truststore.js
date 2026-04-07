export default {
  helpContent: {
    title: 'Vertrauensspeicher',
    subtitle: 'Vertrauenswürdige Zertifikate verwalten',
    overview: 'Importieren und verwalten Sie vertrauenswürdige Root- und Intermediate-CA-Zertifikate. Der Vertrauensspeicher wird für die Kettenvalidierung verwendet und kann mit dem Betriebssystem-Vertrauensspeicher synchronisiert werden.',
    sections: [
      {
        title: 'Zertifikatstypen',
        definitions: [
          { term: 'Root-CA', description: 'Selbstsignierter Vertrauensanker der obersten Ebene' },
          { term: 'Intermediate', description: 'CA-Zertifikat, signiert von einer Root- oder einer anderen Intermediate-CA' },
          { term: 'Client-Auth', description: 'Zertifikat für Client-Authentifizierung (mTLS)' },
          { term: 'Code-Signierung', description: 'Zertifikat zur Verifizierung von Code-Signaturen' },
          { term: 'Benutzerdefiniert', description: 'Manuell kategorisiertes vertrauenswürdiges Zertifikat' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Datei importieren', text: 'PEM-, DER- oder PKCS#7-Zertifikatsdateien hochladen' },
          { label: 'URL importieren', text: 'Ein Zertifikat von einer Remote-URL abrufen' },
          { label: 'PEM hinzufügen', text: 'PEM-kodierten Zertifikatstext direkt einfügen' },
          { label: 'Vom System synchronisieren', text: 'Vertrauenswürdige CAs des Betriebssystems in UCM importieren' },
          { label: 'Exportieren', text: 'Vertrauenswürdige Zertifikate einzeln herunterladen' },
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

Der Vertrauensspeicher verwaltet vertrauenswürdige CA-Zertifikate, die für die Kettenvalidierung verwendet werden. Importieren Sie Root- und Intermediate-CAs aus externen Quellen oder synchronisieren Sie mit dem Vertrauensspeicher des Betriebssystems.

## Zertifikatskategorien

- **Root-CA** — Selbstsignierte Vertrauensanker
- **Intermediate** — CAs, signiert von Root- oder anderen Intermediate-CAs
- **Client-Auth** — Zertifikate für mTLS-Client-Authentifizierung
- **Code-Signierung** — Zertifikate zur Verifizierung von Code-Signaturen
- **Benutzerdefiniert** — Manuell kategorisierte Zertifikate

## Zertifikate importieren

### Aus Datei
Zertifikatsdateien in folgenden Formaten hochladen:
- **PEM** — Base64-kodiert (einzeln oder gebündelt)
- **DER** — Binärformat
- **PKCS#7 (P7B)** — Zertifikatskette

### Von URL
Ein Zertifikat von einem Remote-HTTPS-Endpunkt abrufen. UCM lädt die Zertifikatskette des Servers herunter und importiert sie.

### PEM einfügen
PEM-kodierten Zertifikatstext direkt in den Textbereich einfügen.

### Vom System synchronisieren
Alle vertrauenswürdigen CAs aus dem Vertrauensspeicher des Betriebssystems importieren. Dies füllt UCM mit denselben Root-CAs, die das OS vertraut (z.B. Mozillas CA-Bundle unter Linux).

> 💡 Die Synchronisierung vom System ist ein einmaliger Import. Änderungen am OS-Vertrauensspeicher werden nicht automatisch übernommen.

## Einträge verwalten

- **Nach Zweck filtern** — Die Liste nach Zertifikatskategorie eingrenzen
- **Suche** — Zertifikate nach Betreffsname suchen
- **Exportieren** — Einzelne Zertifikate im PEM-Format herunterladen
- **Löschen** — Ein Zertifikat aus dem Vertrauensspeicher entfernen

## Anwendungsfälle

### Kettenvalidierung
Bei der Überprüfung einer Zertifikatskette prüft UCM den Vertrauensspeicher auf erkannte Root-CAs.

### mTLS
Client-Zertifikate, die bei der gegenseitigen TLS-Authentifizierung präsentiert werden, werden gegen den Vertrauensspeicher validiert.

### ACME
Wenn UCM als ACME-Client fungiert (Let's Encrypt), wird der Vertrauensspeicher verwendet, um das Zertifikat der ACME-CA zu verifizieren.
`
  }
}
