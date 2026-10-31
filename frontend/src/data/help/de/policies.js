export default {
  helpContent: {
    title: 'Zertifikatsrichtlinien',
    subtitle: 'Ausstellungsregeln und Compliance-Durchsetzung',
    overview: 'Definieren und verwalten Sie Zertifikatsrichtlinien, die Ausstellungsregeln, Schlüsselanforderungen, Gültigkeitsgrenzen und Genehmigungsworkflows steuern. Richtlinien werden in Prioritätsreihenfolge ausgewertet, wenn Zertifikate angefordert werden.',
    sections: [
      {
        title: 'Operationen',
        items: [
          { label: 'Ausstellung', text: 'Das Ausstellungsformular, CSR-Signierung und Massensignierung sowie die von einem Operator ausgeführten Erneuerungen' },
          { label: 'Erneuerung', text: 'Erneuerungen durch einen Operator, einzeln oder in Masse, und durch den Planer, der seine Erneuerung einreiht, statt sie auszuführen' },
          { label: 'Widerruf', text: 'Widerrufe von Zertifikaten und Zwischen-CAs durch einen Operator (bei einer CA auch unter den auf sie eingegrenzten Richtlinien); ein ACME-Client kann nicht auf eine Entscheidung warten, daher wird sein Widerruf abgelehnt' },
          { label: 'Mehrere gleichzeitig', text: 'Eine Richtlinie kann mehrere Operationen steuern; eine ohne Operation (ein alter, nie durchgesetzter Erneuerungs- oder Widerrufstyp) steuert nichts, bis Sie eine wählen' },
        ]
      },
      {
        title: 'Regeln',
        items: [
          { label: 'Maximale Gültigkeit', text: 'Maximale Zertifikatslaufzeit in Tagen' },
          { label: 'Erlaubte Schlüsseltypen', text: 'Einschränken, welche Schlüsselalgorithmen und -größen verwendet werden können, einschließlich ML-DSA-44, ML-DSA-65 und ML-DSA-87; der FIPS-Modus entfernt ML-DSA' },
          { label: 'Erlaubte Signaturverfahren', text: 'PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA oder SLH-DSA, abgeglichen mit dem Schlüssel der signierenden CA. Erlaubte Signatur-Hashes binden eine ML-DSA-CA nicht, da sie ohne separaten Digest signiert' },
          { label: 'SAN-Einschränkungen', text: 'Anzahl der SANs begrenzen und DNS-Namensmuster durchsetzen' },
          { label: 'Erlaubte Signatur-Hashes', text: 'SHA-256, SHA-384 oder SHA-512; keine Auswahl erlaubt jeden. Hat niemand den Hash gewählt, gilt der Standard, falls erlaubt, sonst der schwächste erlaubte. Das Ausstellungsformular bietet nur die erlaubten Schlüsseltypen an, die CA-Erstellung nur die erlaubten Schlüsseltypen und Hashes' },
        ]
      },
      {
        title: 'Genehmigungsworkflows',
        items: [
          { label: 'Genehmigungsgruppen', text: 'Eine Benutzergruppe zuweisen, die für die Genehmigung von Anfragen verantwortlich ist' },
          { label: 'Min. Genehmiger', text: 'Anzahl der erforderlichen Genehmigungen vor der Ausstellung' },
          { label: 'Benachrichtigungen', text: 'E-Mail, wenn die Richtlinie einen Vorgang ablehnt oder zur Genehmigung zurückhält; an die aufgeführten Adressen, sonst an ihre Genehmiger. Eine wiederholte Ablehnung wird nur einmal pro Stunde gemeldet' },
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

## Operationen

Eine Richtlinie steuert eine oder mehrere Operationen: Ihre Genehmigungspflicht und ihre Regeln gelten für diese.

### Ausstellung
Das Ausstellungsformular, CSR-Signierung und Massensignierung sowie die von einem Operator ausgeführten Erneuerungen. Dies ist die häufigste Wahl. Steuert Schlüsseltypen, Gültigkeitszeiträume, SAN-Einschränkungen und ob eine Genehmigung erforderlich ist.

### Erneuerung
Erneuerungen durch einen Operator, einzeln oder in Masse, und durch den Planer. Bei einer Erneuerungsrichtlinie mit Genehmigungspflicht reiht der Planer die Erneuerung ein, statt sie auszuführen, und die Genehmigung signiert den vom Server gehaltenen Schlüssel neu.

### Widerruf
Widerrufe von Zertifikaten (einzeln, in Masse, aus den Benutzerzertifikaten) und von Zwischen-CAs. Eingegrenzt durch die ausstellende CA, die Vorlage und das DNS-Muster; der Widerruf einer CA wird auch von den auf diese CA eingegrenzten Richtlinien angehalten, da alle von ihr ausgestellten Zertifikate mit fallen. Die übrigen Regeln gelten nicht. Ein ACME-Client kann nicht auf eine Entscheidung warten: Sein Widerruf wird abgelehnt und den Operatoren überlassen. Das Entfernen einer mTLS-Registrierung wird abgelehnt, bis ihr Zertifikat widerrufen ist, unabhängig davon, wem sie gehört; Administratoren umgehen dies.

Eine Richtlinie, die vor den Operationen erstellt wurde, behält ihr Verhalten: Eine Ausstellungsrichtlinie bleibt eine solche, und ein nie durchgesetzter Erneuerungs- oder Widerrufstyp steuert nichts, bis Sie seine Operationen wählen.

## Regelkonfiguration

### Maximale Gültigkeit
Maximale Zertifikatslaufzeit in Tagen. Gängige Werte:
- **90 Tage**: Kurzlebige Automatisierung (ACME-Stil)
- **397 Tage**: CA/Browser Forum Baseline für öffentliches TLS
- **730 Tage**: Interne/private PKI
- **365 Tage**: Code-Signierung

### Erlaubte Schlüsseltypen
Einschränken, welche Schlüsselalgorithmen und -größen verwendet werden können:
- **RSA-2048**: Minimum für öffentliches Vertrauen
- **RSA-3072**: Die Standard-Schlüsselgröße für neue CAs
- **RSA-4096**: Höhere Sicherheit, größere Zertifikate
- **EC-P256**: Modern, schnell, empfohlen
- **EC-P384**: Höhere Sicherheit mit elliptischer Kurve
- **EC-P521**: Maximale Sicherheit (selten erforderlich)
- **ML-DSA-44 / ML-DSA-65 / ML-DSA-87**: Post-Quanten (FIPS 204), NIST-Level 2, 3 und 5; im FIPS-Modus entfernt

**Erlaubte Signaturverfahren** schränkt ein, wie die signierende CA signiert (PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA, SLH-DSA). Erlaubte Signatur-Hashes binden eine ML-DSA-CA nicht, da sie ohne separaten Digest signiert.

**Erlaubte Signatur-Hashes** schränkt den Signatur-Hash auf dieselbe Weise ein (SHA-256, SHA-384, SHA-512); keine Auswahl erlaubt jeden. Hat niemand den Hash gewählt, gilt der Standard, falls erlaubt, sonst der schwächste erlaubte. Das Ausstellungsformular bietet nur die erlaubten Schlüsseltypen an, die CA-Erstellung nur die erlaubten Schlüsseltypen und Hashes.

### SAN-Einschränkungen
- **Max. DNS-Namen**: Anzahl der Subject Alternative Names begrenzen
- **DNS-Muster**: Auf bestimmte Domänenmuster einschränken (z.B. \`*.firma.com\`)

## Genehmigungsworkflows

Wenn **Genehmigung erforderlich** aktiviert ist, wird die Zertifikatsausstellung pausiert, bis die erforderliche Anzahl von Genehmigern aus der zugewiesenen Gruppe die Anfrage genehmigt hat.

### Konfiguration
- **Genehmigungsgruppe**: Eine Benutzergruppe auswählen, die für Genehmigungen verantwortlich ist
- **Min. Genehmiger**: Anzahl der erforderlichen Genehmigungen (z.B. 2 von 3 Gruppenmitgliedern)
- **Benachrichtigungen**: E-Mail, wenn die Richtlinie einen Vorgang ablehnt (eine Regel verletzt) oder zur Genehmigung zurückhält. Sie gehen an die Benachrichtigungsadressen der Richtlinie, sonst an ihre Genehmiger (die Mitglieder ihrer Genehmigungsgruppe oder alle Benutzer, die genehmigen dürfen). Jede zurückgehaltene Anfrage wird einmal mit einem Link darauf gemeldet; dieselbe wiederholte Ablehnung, etwa durch einen ACME-Client mit Wiederholungsversuchen, einmal pro Stunde. SMTP muss konfiguriert sein

> 💡 Verwenden Sie Genehmigungsworkflows für hochwertige Zertifikate wie Code-Signierung und Wildcard-Zertifikate.

## Prioritätssystem

Richtlinien werden in Prioritätsreihenfolge ausgewertet. Niedrigere Nummern haben höhere Priorität:
- **1–10**: Kritische Sicherheitsrichtlinien (Code-Signierung, Wildcard)
- **10–20**: Standard-Compliance (öffentliches TLS, interne PKI)
- **20+**: Permissive Standardwerte

Wenn mehrere Richtlinien auf eine Zertifikatsanfrage zutreffen, gewinnt die Richtlinie mit der höchsten Priorität (niedrigste Nummer).

## Geltungsbereich

### Alle CAs
Richtlinie gilt für jede CA im System. Verwenden Sie dies für organisationsweite Regeln.

### Bestimmte CA
Richtlinie gilt nur für Zertifikate, die von der ausgewählten CA ausgestellt werden. Verwenden Sie dies für granulare Kontrolle.

## Standardrichtlinien

UCM wird mit 5 integrierten Richtlinien ausgeliefert, die reale PKI-Best-Practices widerspiegeln:
- **Code-Signierung** (Priorität 5): Starke Schlüssel, Genehmigung erforderlich
- **Wildcard-Zertifikate** (Priorität 8): Genehmigung erforderlich, max. 10 SANs
- **Webserver-TLS** (Priorität 10): CA/B-Forum-konform, 397 Tage max.
- **Kurzlebige Automatisierung** (Priorität 15): 90 Tage ACME-Stil
- **Interne PKI** (Priorität 20): 730 Tage, lockere Regeln

> 💡 Passen Sie die Standardrichtlinien an die Anforderungen Ihrer Organisation an oder deaktivieren Sie sie.
`
  }
}
