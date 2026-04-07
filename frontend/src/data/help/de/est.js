export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Enrollment over Secure Transport',
    overview: 'EST (RFC 7030) ermöglicht sichere Zertifikatsregistrierung über HTTPS mit gegenseitigem TLS (mTLS) oder HTTP-Basic-Authentifizierung. Ideal für moderne Unternehmensumgebungen, die standardbasierte Registrierung mit starker Transportsicherheit erfordern.',
    sections: [
      {
        title: 'Tabs',
        items: [
          { label: 'Einstellungen', text: 'EST aktivieren, signierende CA auswählen, Authentifizierungsdaten und Zertifikatsgültigkeit konfigurieren' },
          { label: 'Information', text: 'EST-Endpunkt-URLs für die Integration, Registrierungsstatistiken und Verwendungsbeispiele' },
        ]
      },
      {
        title: 'Authentifizierung',
        items: [
          { label: 'mTLS (Mutual TLS)', text: 'Client präsentiert ein Zertifikat beim TLS-Handshake — stärkste Authentifizierungsmethode' },
          { label: 'HTTP Basic Auth', text: 'Benutzername/Passwort-Fallback, wenn mTLS nicht verfügbar ist' },
        ]
      },
      {
        title: 'Endpunkte',
        items: [
          { label: '/cacerts', text: 'CA-Zertifikatskette abrufen (keine Authentifizierung erforderlich)' },
          { label: '/simpleenroll', text: 'Einen CSR einreichen und ein signiertes Zertifikat erhalten' },
          { label: '/simplereenroll', text: 'Ein bestehendes Zertifikat erneuern (erfordert mTLS)' },
          { label: '/csrattrs', text: 'Vom Server empfohlene CSR-Attribute abrufen' },
          { label: '/serverkeygen', text: 'Server generiert das Schlüsselpaar und gibt Zertifikat + Schlüssel zurück' },
        ]
      },
    ],
    tips: [
      'EST ist der moderne Ersatz für SCEP — bevorzugen Sie EST für neue Implementierungen',
      'Verwenden Sie mTLS-Authentifizierung für höchste Sicherheit — Basic Auth ist ein Fallback',
      'Der /simplereenroll-Endpunkt erfordert, dass der Client sein aktuelles Zertifikat über mTLS präsentiert',
      'Kopieren Sie Endpunkt-URLs vom Informations-Tab, um Ihre EST-Clients zu konfigurieren',
    ],
    warnings: [
      'EST erfordert HTTPS — der Client muss dem UCM-Serverzertifikat oder der CA vertrauen',
      'mTLS-Authentifizierung erfordert eine korrekte TLS-Terminierungskonfiguration (Reverse Proxy muss Client-Zertifikate weiterleiten)',
    ],
  },
  helpGuides: {
    title: 'EST-Protokoll',
    content: `
## Übersicht

Enrollment over Secure Transport (EST) ist in **RFC 7030** definiert und bietet Zertifikatsregistrierung, Erneuerung und CA-Zertifikatsabruf über HTTPS. EST ist der moderne Ersatz für SCEP und bietet stärkere Sicherheit durch gegenseitige TLS-Authentifizierung (mTLS).

## Konfiguration

### Einstellungen-Tab

1. **EST aktivieren** — Das EST-Protokoll ein- oder ausschalten
2. **Signierende CA** — Auswählen, welche Zertifizierungsstelle EST-registrierte Zertifikate signiert
3. **Authentifizierung** — HTTP-Basic-Auth-Anmeldeinformationen konfigurieren (Benutzername und Passwort)
4. **Zertifikatsgültigkeit** — Standard-Gültigkeitsdauer für EST-ausgestellte Zertifikate (in Tagen)

### Konfiguration speichern

Klicken Sie auf **Speichern**, um Änderungen anzuwenden. Die EST-Endpunkte werden sofort verfügbar, wenn aktiviert.

## Authentifizierung

EST unterstützt zwei Authentifizierungsmethoden:

### Mutual TLS (mTLS) — Empfohlen

Der Client präsentiert ein Zertifikat beim TLS-Handshake. UCM validiert das Zertifikat und authentifiziert den Client automatisch.

- **Stärkste Methode** — kryptografische Client-Identität
- **Erforderlich für** \`/simplereenroll\` — der Client muss sein aktuelles Zertifikat präsentieren
- **Abhängig von** korrekter TLS-Terminierungskonfiguration (Reverse Proxy muss \`SSL_CLIENT_CERT\` an UCM weiterleiten)

### HTTP Basic Auth — Fallback

Benutzername- und Passwort-Authentifizierung über HTTPS. Wird in den EST-Einstellungen konfiguriert.

- **Einfacher einzurichten** — kein Client-Zertifikat erforderlich
- **Weniger sicher** — Anmeldeinformationen werden pro Anfrage übertragen (durch HTTPS geschützt)
- **Verwenden, wenn** die mTLS-Infrastruktur nicht verfügbar ist

## EST-Endpunkte

Alle Endpunkte befinden sich unter \`/.well-known/est/\`:

### GET /cacerts
CA-Zertifikatskette abrufen. **Keine Authentifizierung erforderlich.**

Verwenden Sie dies zum Aufbau des Vertrauens — Clients rufen das CA-Zertifikat vor der Registrierung ab.

\`\`\`bash
curl -k https://ihr-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Einen PKCS#10-CSR einreichen und ein signiertes Zertifikat erhalten.

Erfordert Authentifizierung (mTLS oder Basic Auth).

\`\`\`bash
# Mit curl und Basic Auth
curl -k --user est-benutzer:est-passwort \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://ihr-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Ein bestehendes Zertifikat erneuern. **Erfordert mTLS** — der Client muss das zu erneuernde Zertifikat präsentieren.

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://ihr-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Vom Server empfohlene CSR-Attribute (OIDs) abrufen.

### POST /serverkeygen
Server generiert ein Schlüsselpaar und gibt das Zertifikat zusammen mit dem privaten Schlüssel zurück. Nützlich, wenn der Client keine Schlüssel lokal generieren kann.

## Informations-Tab

Der Informations-Tab zeigt:
- **Endpunkt-URLs** — Zum Kopieren bereite URLs für jede EST-Operation
- **Registrierungsstatistiken** — Anzahl der Registrierungen, Erneuerungen und Fehler
- **Letzte Aktivität** — Neueste EST-Vorgänge aus den Audit-Protokollen

## Integrationsbeispiele

### EST-Client (libest) verwenden
\`\`\`bash
estclient -s ihr-server -p 8443 \\
  --srp-user est-benutzer --srp-password est-passwort \\
  -o /tmp/certs --enroll
\`\`\`

### OpenSSL verwenden
\`\`\`bash
# CA-Zertifikate abrufen
curl -k https://ihr-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# CSR generieren
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=mein-geraet/O=MeineOrg"

# Registrieren (Basic Auth)
curl -k --user est-benutzer:est-passwort \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://ihr-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://ihr-server:8443/.well-known/est" \\
  kerberos
\`\`\`

## EST vs SCEP

| Eigenschaft | EST | SCEP |
|-------------|-----|------|
| Transport | HTTPS (TLS) | HTTP oder HTTPS |
| Authentifizierung | mTLS + Basic Auth | Challenge-Passwort |
| Standard | RFC 7030 (2013) | RFC 8894 (2020, aber Legacy) |
| Schlüsselgenerierung | Serverseitige Option | Nur Client |
| Erneuerung | mTLS-Erneuerung | Erneuerung |
| Sicherheit | Stark (TLS-basiert) | Schwächer (geteiltes Geheimnis) |
| Empfehlung | ✅ Bevorzugt für neue | Nur Legacy-Geräte |

> 💡 Verwenden Sie EST für neue Implementierungen. Verwenden Sie SCEP nur für ältere Netzwerkgeräte, die EST nicht unterstützen.
`
  }
}
