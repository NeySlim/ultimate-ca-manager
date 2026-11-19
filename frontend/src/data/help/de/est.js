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
          { label: 'EST-Endpunkte', text: 'EST-Endpunkt-URLs für die Integration und Registrierungsstatistiken' },
        ]
      },
      {
        title: 'Authentifizierung',
        items: [
          { label: 'mTLS (Mutual TLS)', text: 'Client präsentiert ein Zertifikat beim TLS-Handshake, stärkste Authentifizierungsmethode' },
          { label: 'HTTP Basic Auth', text: 'Benutzername/Passwort-Fallback, wenn mTLS nicht verfügbar ist. Mit allow_empty_username, gesetzt über PATCH /api/v2/est/config, darf ein Client auch einen leeren Benutzernamen mit dem Passwort senden (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Präsentiertes Zertifikat', text: 'Für /simpleenroll und /serverkeygen über mTLS muss ein von der EST-CA signiertes Zertifikat eines sein, das sie noch hält: widerrufene, ersetzte oder gelöschte Zertifikate werden abgelehnt (RFC 7030 §3.3.2). Ein Zertifikat, das eine andere CA dieses Servers ausgestellt hat, wird abgelehnt, sobald es oder eine CA darüber widerrufen oder es abgelaufen ist (v2.252); eines von einer Stelle, die dieser Server nicht hält, bleibt der TLS-Schicht überlassen' },
          { label: 'tls-unique-Bindung', text: 'Eine CSR mit challengePassword muss den tls-unique-Wert ihrer TLS-1.2-Verbindung zu UCM tragen (RFC 7030 §3.5); sie wird mit 400 abgelehnt, wenn der Wert abweicht oder nicht geprüft werden kann (TLS 1.3, vorgeschalteter Proxy). /csrattrs verlangt keinen. ignore_challenge_password, gesetzt über PATCH /api/v2/est/config, überspringt die Prüfung für einen Client, der dort ein Passwort einträgt (v2.252)' },
          { label: 'Kompromittierte Schlüssel', text: 'Eine CSR, deren Schlüssel als kompromittiert (keyCompromise) widerrufen wurde, wird mit 400 abgelehnt (v2.252)' },
        ]
      },
      {
        title: 'Endpunkte',
        items: [
          { label: '/cacerts', text: 'CA-Zertifikatskette abrufen (keine Authentifizierung erforderlich)' },
          { label: '/simpleenroll', text: 'Einen CSR einreichen und ein signiertes Zertifikat erhalten' },
          { label: '/simplereenroll', text: 'Ein bestehendes Zertifikat erneuern (erfordert mTLS; ohne Client-Zertifikat: 403). Eine CSR ohne SubjectAltName erneuert die eigenen Namen des Zertifikats, oder keine, wenn es keine hatte, statt eines aus dem CN gebildeten Namens (RFC 7030 §4.2.2, v2.252)' },
          { label: '/csrattrs', text: 'Vom Server empfohlene CSR-Attribute abrufen: keyUsage, subjectAltName und extKeyUsage als reine OIDs (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, gesetzt über PATCH /api/v2/est/config, liefert die frühere Form (die OIDs in einer extensionRequest) für einen Client, der sie braucht' },
          { label: 'Fehler', text: 'Registrierungsablehnungen, auch durch Ratenbegrenzung, kommen als Klartextmeldung (text/plain, RFC 8951 §5) mit dem Grund, etwa ein Body, der nicht base64 oder keine PKCS#10-CSR ist, oder die Name Constraints der CA (v2.252)' },
          { label: '/serverkeygen', text: 'Server generiert ein Schlüsselpaar und gibt Zertifikat + Schlüssel zurück. Der Schlüssel übernimmt die Stärke der ausstellenden CA, in der Familie des Anfrageschlüssels bei RSA oder EC (dessen Größe oder Kurve wird ignoriert), sonst der der CA, auf den nächstliegenden Typ verschoben, den die Richtlinien erlauben. Der Schlüssel kommt unter TLS als unverschlüsseltes PKCS#8; eine CSR, die den Schlüssel des mTLS-Zertifikats nennt (AsymmetricDecryptKeyIdentifier), erhält ihn an dieses Zertifikat verschlüsselt, per Schlüsseltransport für RSA ab 2048 Bit (keyEncipherment) oder per Schlüsselvereinbarung für EC (keyAgreement), mit den Algorithmen aus den SMIMECapabilities der CSR, in einem Schlüsselpaket, das ein EST-key-generator-Zertifikat signiert, das die ausstellende CA dafür ausstellt (Ed25519 unter einer Ed448-CA, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST ist der moderne Ersatz für SCEP: bevorzugen Sie EST für neue Implementierungen',
      'Verwenden Sie mTLS-Authentifizierung für höchste Sicherheit. Basic Auth ist ein Fallback',
      'Der /simplereenroll-Endpunkt erfordert, dass der Client sein aktuelles Zertifikat über mTLS präsentiert',
      'Kopieren Sie Endpunkt-URLs vom Tab EST-Endpunkte, um Ihre EST-Clients zu konfigurieren',
    ],
    warnings: [
      'EST erfordert HTTPS: der Client muss dem UCM-Serverzertifikat oder der CA vertrauen',
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

1. **EST aktivieren**: Das EST-Protokoll ein- oder ausschalten
2. **Signierende CA**: Auswählen, welche Zertifizierungsstelle EST-registrierte Zertifikate signiert
3. **Authentifizierung**: HTTP-Basic-Auth-Anmeldeinformationen konfigurieren (Benutzername und Passwort)
4. **Zertifikatsgültigkeit**: Standard-Gültigkeitsdauer für EST-ausgestellte Zertifikate (in Tagen)
5. **CA-Labels**: andere CAs unter \`/.well-known/est/<label>/\` bereitstellen. Ein Operationsname (\`cacerts\`, \`simpleenroll\`, \`simplereenroll\`, \`fullcmc\`, \`serverkeygen\`, \`csrattrs\`) darf kein Label sein (RFC 7030 §3.2.2, v2.252)

### Konfiguration speichern

Klicken Sie auf **Speichern**, um Änderungen anzuwenden. Die EST-Endpunkte werden sofort verfügbar, wenn aktiviert.

## Authentifizierung

EST unterstützt zwei Authentifizierungsmethoden:

### Mutual TLS (mTLS): Empfohlen

Der Client präsentiert ein Zertifikat beim TLS-Handshake. UCM validiert das Zertifikat und authentifiziert den Client automatisch.

- **Stärkste Methode**: kryptografische Client-Identität
- **Erforderlich für** \`/simplereenroll\`: der Client muss sein aktuelles Zertifikat präsentieren
- **Präsentiertes Zertifikat**: für \`/simpleenroll\` und \`/serverkeygen\` muss ein von der EST-CA signiertes Zertifikat eines sein, das sie noch hält: widerrufene, ersetzte oder gelöschte Zertifikate werden abgelehnt (RFC 7030 §3.3.2); ein Zertifikat, das eine andere CA dieses Servers ausgestellt hat, wird abgelehnt, sobald es oder eine CA darüber widerrufen oder es abgelaufen ist (v2.252); eines von einer Stelle, die dieser Server nicht hält, bleibt der TLS-Schicht überlassen
- **tls-unique-Bindung**: eine CSR mit \`challengePassword\` muss den \`tls-unique\`-Wert ihrer TLS-1.2-Verbindung zu UCM tragen (RFC 7030 §3.5) und wird mit 400 abgelehnt, wenn der Wert abweicht oder nicht geprüft werden kann (TLS 1.3, vorgeschalteter Proxy); \`/csrattrs\` verlangt keinen. \`ignore_challenge_password\`, gesetzt über \`PATCH /api/v2/est/config\`, überspringt die Prüfung für einen Client, der dort ein Passwort einträgt (v2.252)
- **Abhängig von** korrekter TLS-Terminierungskonfiguration (Reverse Proxy muss \`SSL_CLIENT_CERT\` an UCM weiterleiten)

### HTTP Basic Auth. Fallback

Benutzername- und Passwort-Authentifizierung über HTTPS. Wird in den EST-Einstellungen konfiguriert.

- **Einfacher einzurichten**: kein Client-Zertifikat erforderlich
- **Weniger sicher**: Anmeldeinformationen werden pro Anfrage übertragen (durch HTTPS geschützt)
- **Verwenden, wenn** die mTLS-Infrastruktur nicht verfügbar ist
- **Nur Passwort**: mit \`allow_empty_username\`, gesetzt über \`PATCH /api/v2/est/config\`, darf ein Client einen leeren Benutzernamen mit dem Passwort senden (RFC 7030 §3.2.3, v2.252)

Eine CSR, deren Schlüssel als kompromittiert widerrufen wurde, wird mit 400 abgelehnt, und jede Registrierungsablehnung, auch durch Ratenbegrenzung, kommt als Klartextmeldung mit dem Grund (RFC 8951 §5, v2.252).

## EST-Endpunkte

Alle Endpunkte befinden sich unter \`/.well-known/est/\`:

### GET /cacerts
CA-Zertifikatskette abrufen. **Keine Authentifizierung erforderlich.**

Verwenden Sie dies zum Aufbau des Vertrauens. Clients rufen das CA-Zertifikat vor der Registrierung ab.

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
Ein bestehendes Zertifikat erneuern. **Erfordert mTLS**: der Client muss das zu erneuernde Zertifikat präsentieren, sonst gibt es 403. Eine CSR ohne SubjectAltName erneuert die eigenen Namen des Zertifikats, oder keine, wenn es keine hatte, nicht einen aus dem CN gebildeten Namen (RFC 7030 §4.2.2, v2.252).

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://ihr-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Die vom Server empfohlenen CSR-Attribute abrufen: keyUsage, subjectAltName und extKeyUsage als reine OIDs, die Form, die RFC 9908 §5.2 für eine ohne Wert angefragte OID vorsieht (v2.252). Ein Client, der die frühere Form braucht (die OIDs in einem extensionRequest-Attribut), erhält sie mit \`csrattrs_legacy_encoding\`, gesetzt über \`PATCH /api/v2/est/config\`.

### POST /serverkeygen
Server generiert ein Schlüsselpaar und gibt das Zertifikat zusammen mit dem privaten Schlüssel zurück. Nützlich, wenn der Client keine Schlüssel lokal generieren kann.

Der erzeugte Schlüssel übernimmt die Stärke der ausstellenden CA: die Familie des Anfrageschlüssels bei RSA oder EC (dessen Größe oder Kurve wird ignoriert), sonst die der CA, auf den nächstliegenden Typ verschoben, den die Richtlinien erlauben.

Der private Schlüssel kommt als unverschlüsseltes PKCS#8 (\`application/pkcs8\`), durch TLS geschützt. Um ihn verschlüsselt zu erhalten, authentifizieren Sie sich per mTLS und tragen den Schlüsselbezeichner des Client-Zertifikats in die CSR ein (AsymmetricDecryptKeyIdentifier): Der Schlüssel kommt dann in einem RFC-5958-Schlüsselpaket, das für dieses Zertifikat umhüllt ist, per Schlüsseltransport für ein RSA-Zertifikat ab 2048 Bit mit keyEncipherment oder per Schlüsselvereinbarung (ECDH) für ein EC-Zertifikat mit keyAgreement; Schlüsseltransport bzw. Schlüsselvereinbarung und Inhaltsalgorithmen stammen aus den SMIMECapabilities der CSR in der Reihenfolge des Clients. Das Paket signiert ein Zertifikat „EST key generator“, das die ausstellende CA bei der ersten Nutzung ausstellt und selbst erneuert; es führt zu der CA, die \`/cacerts\` liefert, und hat deren Schlüsselfamilie, Ed25519 unter einer Ed448-CA (v2.252).

## Tab EST-Endpunkte

Der Tab EST-Endpunkte zeigt:
- **Endpunkt-URLs**: Zum Kopieren bereite URLs für jede EST-Operation
- **Registrierungsstatistiken**: Gesamtzahl sowie erfolgreiche und fehlgeschlagene Registrierungen

## Integrationsbeispiele

### EST-Client (libest) verwenden
Verwenden Sie \`estclient\` mit HTTP-Basic-Zugangsdaten (\`-u\` und \`-h\`) oder einem Client-Zertifikat. Seine TLS-SRP-Optionen gelten nicht: UCM bietet kein TLS-SRP an.

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
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

Die Antwort ist ein base64-kodiertes PKCS#7 (nur Zertifikate), kein einzelnes Zertifikat: Lesen Sie sie mit \`openssl pkcs7\`, nicht mit \`openssl x509\`.

### Windows
Windows hat keinen eingebauten EST-Client: \`certutil -enrollmentServerURL\` registriert einen Certificate-Enrollment-Webdienst (WSTEP), keinen EST-Server. Für Windows-Rechner verwenden Sie das Windows-Autoenrollment (XCEP/WSTEP).

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
