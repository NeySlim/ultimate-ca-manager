export default {
  helpContent: {
    title: 'CRL & OCSP',
    subtitle: 'Zertifikatswiderrufsdienste',
    overview: 'Verwalten Sie Certificate Revocation Lists (CRL) und Online Certificate Status Protocol (OCSP)-Dienste. Diese Dienste ermöglichen es Clients zu überprüfen, ob ein Zertifikat widerrufen wurde.',
    sections: [
      {
        title: 'CRL-Verwaltung',
        items: [
          { label: 'Auto-Regenerierung', text: 'Automatische CRL-Regenerierung pro CA umschalten' },
          { label: 'Manuell regenerieren', text: 'CRL-Regenerierung sofort erzwingen' },
          { label: 'CRL herunterladen', text: 'Die CRL-Datei im DER- oder PEM-Format herunterladen' },
          { label: 'CDP-URL', text: 'CRL Distribution Point-URL zum Einbetten in Zertifikate' },
        ]
      },
      {
        title: 'OCSP-Dienst',
        items: [
          { label: 'Status', text: 'Zeigt an, ob der OCSP-Responder für jede CA aktiv ist' },
          { label: 'AIA-URL', text: 'Authority Information Access-URLs — OCSP-Responder- und CA-Aussteller-Zertifikat-Download-Endpunkte, die in ausgestellte Zertifikate eingebettet werden' },
          { label: 'Cache', text: 'Antwort-Cache mit automatischer täglicher Bereinigung abgelaufener Einträge' },
          { label: 'Gesamtabfragen', text: 'Anzahl der verarbeiteten OCSP-Anfragen' },
        ]
      },
    ],
    tips: [
      'Aktivieren Sie die Auto-Regenerierung, um CRLs nach Zertifikatswiderrufen aktuell zu halten',
      'Kopieren Sie CDP-, OCSP- und AIA-CA-Aussteller-URLs, um sie in Ihre Zertifikatsprofile einzubetten',
      'OCSP bietet Echtzeit-Widerrufsprüfung und wird gegenüber CRL bevorzugt',
    ],
  },
  helpGuides: {
    title: 'CRL & OCSP',
    content: `
## Übersicht

Certificate Revocation Lists (CRL) und Online Certificate Status Protocol (OCSP) ermöglichen es Clients zu überprüfen, ob ein Zertifikat widerrufen wurde. UCM unterstützt beide Mechanismen.

## CRL-Verwaltung

### Was ist eine CRL?
Eine CRL ist eine signierte Liste widerrufener Zertifikatsseriennummern, die von einer CA veröffentlicht wird. Clients laden die CRL herunter und prüfen, ob die Seriennummer eines Zertifikats darin enthalten ist.

### CRL pro CA
Jede CA hat ihre eigene CRL. Die CRL-Liste zeigt alle Ihre CAs mit:
- **Widerrufene Anzahl** — Anzahl der Zertifikate in der CRL
- **Zuletzt regeneriert** — Wann die CRL zuletzt neu erstellt wurde
- **Auto-Regenerierung** — Ob automatische CRL-Updates aktiviert sind

### CRL regenerieren
Klicken Sie auf **Regenerieren**, um die CRL einer CA sofort neu zu erstellen. Dies ist nützlich nach dem Widerruf von Zertifikaten.

### Auto-Regenerierung
Aktivieren Sie die Auto-Regenerierung, um die CRL automatisch nach jedem Zertifikatswiderruf neu zu erstellen. Konfigurierbar pro CA.

### CRL Distribution Point (CDP)
Die CDP-URL wird in Zertifikate eingebettet, damit Clients wissen, wo sie die CRL herunterladen können. Kopieren Sie die URL aus den CRL-Details.

\`\`\`
http://ihr-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Automatisch aktiviert**: Wenn Sie eine neue CA erstellen, wird CDP automatisch aktiviert, wenn eine Protokoll-Basis-URL oder ein HTTP-Protokollserver konfiguriert ist. Die CDP-URL wird automatisch generiert — keine manuellen Schritte erforderlich.

> ⚠️ **Wichtig**: URLs werden automatisch mit dem HTTP-Protokollport und dem Server-FQDN generiert. Wenn Sie über \`localhost\` auf UCM zugreifen, kann die URL nicht generiert werden. Konfigurieren Sie zuerst Ihren **FQDN** oder die **Protokoll-Basis-URL** unter Einstellungen → Allgemein.

### CRLs herunterladen
Laden Sie CRLs im DER- oder PEM-Format zur Verteilung an Clients oder Integration mit anderen Systemen herunter.

## OCSP-Responder

### Was ist OCSP?
OCSP bietet Echtzeit-Zertifikatsstatusprüfung. Anstatt eine gesamte CRL herunterzuladen, senden Clients eine Anfrage für ein bestimmtes Zertifikat und erhalten eine sofortige Antwort.

### OCSP-Status
Der OCSP-Bereich zeigt:
- **Responder-Status** — Aktiv oder inaktiv pro CA
- **Gesamtabfragen** — Anzahl der verarbeiteten OCSP-Anfragen
- **Cache** — Antwort-Cache mit automatischer täglicher Bereinigung abgelaufener Einträge

### OCSP-Cache

UCM speichert OCSP-Antworten für die Leistung im Cache. Der Cache wird:
- **Automatisch bereinigt** — Abgelaufene Antworten werden täglich vom Scheduler gelöscht
- **Bei Widerruf ungültig gemacht** — Wenn ein Zertifikat widerrufen wird, wird die zwischengespeicherte OCSP-Antwort sofort gelöscht
- **Bei Sperre-Aufhebung ungültig gemacht** — Wenn eine Zertifikatssperre aufgehoben wird, wird der OCSP-Cache aktualisiert

### AIA-URLs
Die Authority Information Access (AIA)-Erweiterung wird in Zertifikate eingebettet, um Clients mitzuteilen, wo sie finden:

**OCSP-Responder** — Echtzeit-Widerrufsprüfung:
\`\`\`
http://ihr-server:8080/ocsp
\`\`\`

**CA-Aussteller** (RFC 5280 §4.2.2.1) — Zertifikat der ausstellenden CA für den Kettenaufbau herunterladen:
\`\`\`
http://ihr-server:8080/ca/{ca_refid}.cer   (DER-Format)
http://ihr-server:8080/ca/{ca_refid}.pem   (PEM-Format)
\`\`\`

Aktivieren Sie CA-Aussteller pro CA im Bereich **AIA CA-Aussteller** des Detailpanels. Die URL wird automatisch mit dem HTTP-Protokollserver und dem konfigurierten FQDN generiert.

> ⚠️ **Voraussetzung**: Protokoll-URLs (CDP, OCSP, AIA) erfordern einen gültigen **FQDN** oder eine konfigurierte **Protokoll-Basis-URL** unter Einstellungen → Allgemein. Wenn Sie über \`localhost\` auf UCM zugreifen, schlägt die Aktivierung dieser Funktionen fehl — legen Sie zuerst den FQDN fest.

### OCSP vs CRL

| Eigenschaft | CRL | OCSP |
|-------------|-----|------|
| Aktualisierungshäufigkeit | Periodisch | Echtzeit |
| Bandbreite | Jedes Mal vollständige Liste | Einzelabfrage |
| Datenschutz | Keine Verfolgung | Server sieht Abfragen |
| Offline-Unterstützung | Ja (zwischengespeichert) | Erfordert Verbindung |

> 💡 Best Practice: Aktivieren Sie sowohl CRL als auch OCSP für maximale Kompatibilität.
`
  }
}
