export default {
  helpContent: {
    title: 'Zertifikatsrichtlinien',
    subtitle: 'Ausstellungsregeln und Compliance-Durchsetzung',
    overview: 'Definieren und verwalten Sie Zertifikatsrichtlinien, die Ausstellungsregeln, Schlüsselanforderungen, Gültigkeitsgrenzen und Genehmigungsworkflows steuern. Richtlinien werden in Prioritätsreihenfolge ausgewertet, wenn Zertifikate angefordert werden.',
    sections: [
      {
        title: 'Richtlinientypen',
        items: [
          { label: 'Ausstellung', text: 'Regeln, die bei der Erstellung neuer Zertifikate angewendet werden' },
          { label: 'Erneuerung', text: 'Regeln, die bei der Erneuerung von Zertifikaten angewendet werden' },
          { label: 'Widerruf', text: 'Regeln, die beim Widerruf von Zertifikaten angewendet werden' },
        ]
      },
      {
        title: 'Regeln',
        items: [
          { label: 'Maximale Gültigkeit', text: 'Maximale Zertifikatslaufzeit in Tagen' },
          { label: 'Erlaubte Schlüsseltypen', text: 'Einschränken, welche Schlüsselalgorithmen und -größen verwendet werden können' },
          { label: 'SAN-Einschränkungen', text: 'Anzahl der SANs begrenzen und DNS-Namensmuster durchsetzen' },
        ]
      },
      {
        title: 'Genehmigungsworkflows',
        items: [
          { label: 'Genehmigungsgruppen', text: 'Eine Benutzergruppe zuweisen, die für die Genehmigung von Anfragen verantwortlich ist' },
          { label: 'Min. Genehmiger', text: 'Anzahl der erforderlichen Genehmigungen vor der Ausstellung' },
          { label: 'Benachrichtigungen', text: 'Administratoren bei Richtlinienverstößen benachrichtigen' },
        ]
      },
    ],
    tips: [
      'Niedrigere Prioritätsnummer = höhere Priorität. Verwenden Sie 1–10 für kritische Richtlinien.',
      'Richten Sie Richtlinien auf bestimmte CAs aus für granulare Kontrolle.',
      'Aktivieren Sie Benachrichtigungen, um Richtlinienverstöße frühzeitig zu erkennen.',
    ],
  },
  helpGuides: {
    title: 'Zertifikatsrichtlinien',
    content: `
## Übersicht

Zertifikatsrichtlinien definieren die Regeln und Einschränkungen, die bei der Ausstellung, Erneuerung oder dem Widerruf von Zertifikaten durchgesetzt werden. Richtlinien werden in **Prioritätsreihenfolge** ausgewertet (niedrigere Nummer = höhere Priorität) und können auf bestimmte CAs beschränkt werden.

## Richtlinientypen

### Ausstellungsrichtlinien
Regeln, die bei der Erstellung neuer Zertifikate angewendet werden. Dies ist der häufigste Typ. Steuert Schlüsseltypen, Gültigkeitszeiträume, SAN-Einschränkungen und ob eine Genehmigung erforderlich ist.

### Erneuerungsrichtlinien
Regeln, die bei der Erneuerung von Zertifikaten angewendet werden. Können kürzere Gültigkeitsdauern bei der Erneuerung erzwingen oder eine erneute Genehmigung erfordern.

### Widerrufsrichtlinien
Regeln, die beim Widerruf von Zertifikaten angewendet werden. Können eine Genehmigung vor dem Widerruf kritischer Zertifikate erfordern.

## Regelkonfiguration

### Maximale Gültigkeit
Maximale Zertifikatslaufzeit in Tagen. Gängige Werte:
- **90 Tage** — Kurzlebige Automatisierung (ACME-Stil)
- **397 Tage** — CA/Browser Forum Baseline für öffentliches TLS
- **730 Tage** — Interne/private PKI
- **365 Tage** — Code-Signierung

### Erlaubte Schlüsseltypen
Einschränken, welche Schlüsselalgorithmen und -größen verwendet werden können:
- **RSA-2048** — Minimum für öffentliches Vertrauen
- **RSA-4096** — Höhere Sicherheit, größere Zertifikate
- **EC-P256** — Modern, schnell, empfohlen
- **EC-P384** — Höhere Sicherheit mit elliptischer Kurve
- **EC-P521** — Maximale Sicherheit (selten erforderlich)

### SAN-Einschränkungen
- **Max. DNS-Namen** — Anzahl der Subject Alternative Names begrenzen
- **DNS-Muster** — Auf bestimmte Domänenmuster einschränken (z.B. \`*.firma.com\`)

## Genehmigungsworkflows

Wenn **Genehmigung erforderlich** aktiviert ist, wird die Zertifikatsausstellung pausiert, bis die erforderliche Anzahl von Genehmigern aus der zugewiesenen Gruppe die Anfrage genehmigt hat.

### Konfiguration
- **Genehmigungsgruppe** — Eine Benutzergruppe auswählen, die für Genehmigungen verantwortlich ist
- **Min. Genehmiger** — Anzahl der erforderlichen Genehmigungen (z.B. 2 von 3 Gruppenmitgliedern)
- **Benachrichtigungen** — Administratoren bei Richtlinienverstößen benachrichtigen

> 💡 Verwenden Sie Genehmigungsworkflows für hochwertige Zertifikate wie Code-Signierung und Wildcard-Zertifikate.

## Prioritätssystem

Richtlinien werden in Prioritätsreihenfolge ausgewertet. Niedrigere Nummern haben höhere Priorität:
- **1–10** — Kritische Sicherheitsrichtlinien (Code-Signierung, Wildcard)
- **10–20** — Standard-Compliance (öffentliches TLS, interne PKI)
- **20+** — Permissive Standardwerte

Wenn mehrere Richtlinien auf eine Zertifikatsanfrage zutreffen, gewinnt die Richtlinie mit der höchsten Priorität (niedrigste Nummer).

## Geltungsbereich

### Alle CAs
Richtlinie gilt für jede CA im System. Verwenden Sie dies für organisationsweite Regeln.

### Bestimmte CA
Richtlinie gilt nur für Zertifikate, die von der ausgewählten CA ausgestellt werden. Verwenden Sie dies für granulare Kontrolle.

## Standardrichtlinien

UCM wird mit 5 integrierten Richtlinien ausgeliefert, die reale PKI-Best-Practices widerspiegeln:
- **Code-Signierung** (Priorität 5) — Starke Schlüssel, Genehmigung erforderlich
- **Wildcard-Zertifikate** (Priorität 8) — Genehmigung erforderlich, max. 10 SANs
- **Webserver-TLS** (Priorität 10) — CA/B-Forum-konform, 397 Tage max.
- **Kurzlebige Automatisierung** (Priorität 15) — 90 Tage ACME-Stil
- **Interne PKI** (Priorität 20) — 730 Tage, lockere Regeln

> 💡 Passen Sie die Standardrichtlinien an die Anforderungen Ihrer Organisation an oder deaktivieren Sie sie.
`
  }
}
