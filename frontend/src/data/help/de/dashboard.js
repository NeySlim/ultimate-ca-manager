export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
  },
  helpGuides: {
    title: 'Dashboard',
    content: `
## Übersicht

Das Dashboard ist Ihre zentrale Überwachungszentrale. Es zeigt Echtzeit-Metriken, Diagramme und Warnungen über Ihre gesamte PKI-Infrastruktur durch anpassbare Widgets an.

## Widgets

### Statistik-Karte
Zeigt diese Zähler an:
- **Zertifikate**: alle Zertifikate, abgelaufene und widerrufene eingeschlossen
- **CAs**: Root- und Intermediate-Zertifizierungsstellen
- **CSRs**: Zertifikatsignierungsanfragen, die auf Signatur warten
- **ACME**: registrierte ACME-Konten
- **SSH-Zertifikate**: angezeigt, wenn eine SSH-CA existiert

### Zertifikatsaktivität
Ein Flächendiagramm der ausgestellten, widerrufenen und abgelaufenen Zertifikate pro Tag im gewählten Zeitraum. Bewegen Sie den Mauszeiger über Datenpunkte, um genaue Zahlen zu sehen.

### Statusverteilung
Kreisdiagramm mit der Aufschlüsselung der Zertifikatszustände:
- **Gültig**: Innerhalb des Gültigkeitszeitraums und nicht widerrufen
- **Ablaufend**: Läuft innerhalb von 30 Tagen ab
- **Abgelaufen**: Nach dem „Nicht nach"-Datum
- **Widerrufen**: Explizit widerrufen

### Nächster Ablauf
Listet die sechs gültigen Zertifikate auf, die am ehesten ablaufen, unabhängig vom Datum. Klicken Sie auf ein Zertifikat, um zu seinen Details zu navigieren.

### Systemstatus
Zeigt den Zustand der UCM-Dienste:
- ACME-Server (aktiviert/deaktiviert)
- SCEP-Server
- EST-Protokoll (aktiviert/deaktiviert, zugewiesene CA)
- CRL-Auto-Regenerierung mit CDP-Anzahl
- OCSP-Responder
- TSA, SMTP und Webhooks
- Auto-Erneuerungsstatus

Das Systemzustand-Panel zeigt außerdem die WebSocket-Verbindung, die Datenbank, die API und den Zeitpunkt der letzten Aktualisierung.

### Letzte Aktivitäten
Ein Live-Feed der neuesten Vorgänge: Zertifikatsausstellung, Widerrufe, Importe, Benutzeranmeldungen. Aktualisiert sich in Echtzeit über WebSocket.

### Zertifizierungsstellen
Schnellansicht der neuesten CAs, jeweils als Root oder Sub gekennzeichnet.

### Ablauf des Trust Store
Vertrauenswürdige Zertifikate, die am ehesten ablaufen.

### ACME-Konten
Listet registrierte ACME-Client-Konten und deren Bestellanzahl auf.

## Anpassung

### Widgets neu anordnen
Klicken Sie in der Seitenkopfzeile auf **Layout bearbeiten** und ziehen Sie dann ein Widget an seiner Kopfzeile, um es zu verschieben. Das Layout verwendet ein responsives Raster, das sich an Ihre Bildschirmgröße anpasst.

### Widgets ein-/ausblenden
Klicken Sie in der Seitenkopfzeile auf **Anpassen** (Reglersymbol), dann auf das Auge neben einem Widget, um dessen Sichtbarkeit umzuschalten. Ausgeblendete Widgets werden über Sitzungen hinweg gespeichert.

### Layout-Persistenz
Ihr Layout wird im Browser gespeichert, nicht in Ihrem Konto: Jedes Konto, das sich im selben Browserprofil anmeldet, teilt es, und ein anderer Browser beginnt mit dem Standardlayout.

## Echtzeit-Aktualisierungen
Das Dashboard empfängt Live-Updates über WebSocket. Kein manuelles Aktualisieren nötig: neue Zertifikate, Statusänderungen und Aktivitätseinträge erscheinen automatisch.

> 💡 Der grüne Punkt in der Seitenleiste zeigt eine aktive WebSocket-Verbindung an. Er verschwindet, wenn die Verbindung abbricht. Die Daten werden bei Wiederverbindung aktualisiert.
`
  }
}
