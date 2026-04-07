export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Zeitstempeldienst',
    overview: 'TSA (RFC 3161) bietet vertrauenswürdige Zeitstempel, die beweisen, dass ein Dokument oder Hash zu einem bestimmten Zeitpunkt existierte. Wird für Code-Signierung, rechtliche Compliance und Audit-Trails verwendet.',
    sections: [
      {
        title: 'Tabs',
        items: [
          { label: 'Einstellungen', text: 'TSA aktivieren, signierende CA auswählen und TSA-Richtlinien-OID konfigurieren' },
          { label: 'Information', text: 'TSA-Endpunkt-URL, Verwendungsbeispiele mit OpenSSL und Anfragestatistiken' },
        ]
      },
      {
        title: 'Konfiguration',
        items: [
          { label: 'Signierende CA', text: 'Die CA, deren privater Schlüssel Zeitstempel-Token signiert — muss eine gültige, nicht abgelaufene CA sein' },
          { label: 'Richtlinien-OID', text: 'Object Identifier für die TSA-Richtlinie (z.B. 1.2.3.4.1) — in jeder Zeitstempel-Antwort enthalten' },
          { label: 'Aktivieren/Deaktivieren', text: 'Den TSA-Endpunkt ein- oder ausschalten, ohne die Konfiguration zu verlieren' },
        ]
      },
      {
        title: 'Verwendung',
        items: [
          { label: 'Anfrage erstellen', text: 'openssl ts -query -data datei.txt -sha256 -no_nonce -out request.tsq' },
          { label: 'An TSA senden', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://ihr-server/tsa -o response.tsr' },
          { label: 'Verifizieren', text: 'openssl ts -verify -data datei.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'TSA-Zeitstempel werden bei der Code-Signierung verwendet, um sicherzustellen, dass Signaturen nach Zertifikatsablauf gültig bleiben',
      'Der TSA-Endpunkt akzeptiert HTTP POST mit Content-Type: application/timestamp-query',
      'Verwenden Sie SHA-256 oder stärkere Hash-Algorithmen beim Erstellen von Zeitstempel-Anfragen',
      'Keine Authentifizierung erforderlich — der TSA-Endpunkt ist öffentlich zugänglich wie CRL/OCSP',
    ],
    warnings: [
      'Eine gültige signierende CA muss konfiguriert sein, bevor TSA aktiviert wird',
      'Der TSA-Endpunkt ist ein öffentlicher Protokoll-Endpunkt — fügen Sie keine sensiblen Daten in Zeitstempel-Anfragen ein',
    ],
  },
  helpGuides: {
    title: 'TSA-Protokoll',
    content: `
## Übersicht

Der Zeitstempeldienst (TSA) implementiert **RFC 3161** zur Bereitstellung vertrauenswürdiger Zeitstempel, die kryptografisch beweisen, dass ein Dokument, Hash oder eine digitale Signatur zu einem bestimmten Zeitpunkt existierte. TSA wird häufig für Code-Signierung, rechtliche Compliance, Langzeitarchivierung und Audit-Trails verwendet.

## Funktionsweise

1. **Client erstellt eine Zeitstempel-Anfrage** — hasht eine Datei mit SHA-256/SHA-512 und erstellt ein \`TimeStampReq\` (ASN.1 DER-kodiert)
2. **Client sendet Anfrage an TSA** — HTTP POST an den \`/tsa\`-Endpunkt mit \`Content-Type: application/timestamp-query\`
3. **UCM signiert den Zeitstempel** — die konfigurierte CA signiert den Hash + aktuelle Uhrzeit in ein \`TimeStampResp\`
4. **Client empfängt und speichert die Antwort** — die \`.tsr\`-Datei kann später beweisen, dass das Dokument zu diesem Zeitpunkt existierte

## Konfiguration

### Einstellungen-Tab

1. **TSA aktivieren** — Den TSA-Server ein- oder ausschalten
2. **Signierende CA** — Auswählen, welche Zertifizierungsstelle Zeitstempel-Token signiert
3. **Richtlinien-OID** — Object Identifier für die TSA-Richtlinie (z.B. \`1.2.3.4.1\`), in jeder Zeitstempel-Antwort enthalten

### Signierende CA auswählen

Der private Schlüssel der signierenden CA wird zum Signieren jedes Zeitstempel-Tokens verwendet. Best Practices:

- Verwenden Sie eine **dedizierte Sub-CA** für Zeitstempel anstelle Ihrer Root-CA
- Das CA-Zertifikat sollte die **id-kp-timeStamping** Extended Key Usage (OID 1.3.6.1.5.5.7.3.8) enthalten
- Stellen Sie sicher, dass das CA-Zertifikat eine **ausreichende Gültigkeit** hat — Zeitstempel müssen über Jahre hinweg verifizierbar bleiben

### Richtlinien-OID

Die Richtlinien-OID identifiziert die TSA-Richtlinie, unter der Zeitstempel ausgestellt werden. Sie wird in jedes \`TimeStampResp\` eingebettet.

- Standard: \`1.2.3.4.1\` (Platzhalter)
- Für die Produktion registrieren Sie eine OID unter dem Arc Ihrer Organisation oder verwenden Sie eine aus Ihrem CP/CPS

## Informations-Tab

Der Informations-Tab zeigt:

- **TSA-Endpunkt-URL** — Zum Kopieren bereite URL für die Client-Konfiguration
- **Verwendungsbeispiele** — OpenSSL-Befehle zum Erstellen von Anfragen, Senden und Verifizieren von Antworten
- **Statistiken** — Gesamte verarbeitete Zeitstempel-Anfragen (erfolgreich und fehlgeschlagen)

## Verwendungsbeispiele

### Zeitstempel-Anfrage erstellen

\`\`\`bash
# Datei hashen und Zeitstempel-Anfrage erstellen
openssl ts -query -data datei.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### Anfrage an TSA senden

\`\`\`bash
# Anfrage senden und Zeitstempel-Antwort empfangen
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://ihr-server:8443/tsa -o response.tsr
\`\`\`

### Zeitstempel verifizieren

\`\`\`bash
# Zeitstempel-Antwort gegen die Originaldatei verifizieren
openssl ts -verify -data datei.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### Code-Signierung mit Zeitstempeln

Beim Signieren von Code fügen Sie die TSA-URL hinzu, um sicherzustellen, dass Signaturen nach Zertifikatsablauf gültig bleiben:

\`\`\`bash
# Mit Zeitstempel signieren (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://ihr-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# Mit Zeitstempel signieren (signtool.exe unter Windows)
signtool sign /fd SHA256 /tr https://ihr-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### PDF-Dokumenten-Zeitstempel

\`\`\`bash
# Einen separaten Zeitstempel für ein PDF erstellen
openssl ts -query -data dokument.pdf -sha256 -cert \\
  -out dokument.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @dokument.tsq \\
  https://ihr-server:8443/tsa -o dokument.tsr
\`\`\`

## Protokolldetails

| Eigenschaft | Wert |
|-------------|------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Endpunkt | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Antworttyp | \`application/timestamp-reply\` |
| Hash-Algorithmen | SHA-256, SHA-384, SHA-512, SHA-1 (Legacy) |
| Authentifizierung | Keine (öffentlicher Endpunkt) |
| Transport | HTTP oder HTTPS |

## Sicherheitshinweise

- Der TSA-Endpunkt ist **öffentlich** — keine Authentifizierung erforderlich (wie CRL/OCSP)
- Jede Zeitstempel-Antwort wird mit dem CA-Schlüssel **signiert** — Clients verifizieren die Signatur, um die Authentizität sicherzustellen
- Verwenden Sie **SHA-256 oder stärkere** Hash-Algorithmen beim Erstellen von Anfragen (SHA-1 wird akzeptiert, aber nicht empfohlen)
- Die TSA sieht **nicht** das Originaldokument — nur der Hash wird übertragen
- Erwägen Sie eine **Ratenbegrenzung**, wenn der TSA-Endpunkt dem Internet ausgesetzt ist

> 💡 Zeitstempel sind für die Code-Signierung unverzichtbar: Sie stellen sicher, dass Ihre signierte Software auch nach Ablauf des Signierungszertifikats vertrauenswürdig bleibt.
`
  }
}
