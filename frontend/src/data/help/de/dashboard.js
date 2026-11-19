export default {
  helpContent: {
    title: 'Dashboard',
    subtitle: 'Systemübersicht und Überwachung',
    overview: 'Echtzeit-Übersicht Ihrer PKI-Infrastruktur. Widgets zeigen Zertifikatsstatus, Ablaufwarnungen, Systemzustand und aktuelle Aktivitäten an. Das Layout ist vollständig anpassbar per Drag-and-Drop.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Statistiken', text: 'Alle Zertifikate (abgelaufene und widerrufene eingeschlossen), CAs, ausstehende CSRs und ACME-Konten, dazu SSH-Zertifikate, wenn eine SSH-CA existiert' },
          { label: 'Zertifikatsaktivität', text: 'Ausgestellte, widerrufene und abgelaufene Zertifikate pro Tag im gewählten Zeitraum' },
          { label: 'Statusverteilung', text: 'Kreisdiagramm: gültig / ablaufend / abgelaufen / widerrufen' },
          { label: 'Nächster Ablauf', text: 'Die sechs gültigen Zertifikate, die am ehesten ablaufen, unabhängig vom Datum; der konfigurierte dedizierte TSA-Signierer wird mit einem "TSA signer"-Chip gekennzeichnet (v2.218)' },
          { label: 'Systemstatus', text: 'Dienststatus: ACME, SCEP, EST, OCSP, CRL/CDP, TSA (v2.218), Auto-Erneuerung, SMTP und Webhooks. Badges zeigen einen eigenen bernsteinfarbenen Warnzustand (bald ablaufender TSA-Signierer, SMTP konfiguriert, aber deaktiviert) und beim Überfahren mit dem Mauszeiger ihre Statusmeldung' },
          { label: 'Letzte Aktivitäten', text: 'Neueste Vorgänge im gesamten System' },
          { label: 'Neueste Zertifikate', text: 'Kürzlich ausgestellte oder importierte Zertifikate' },
          { label: 'Zertifizierungsstellen', text: 'Neueste CAs, jeweils als Root oder Sub gekennzeichnet' },
          { label: 'ACME-Konten', text: 'Registrierte ACME-Client-Konten' },
          { label: 'Ablauf des Trust Store', text: 'Vertrauenswürdige Zertifikate, die am ehesten ablaufen' },
        ]
      },
    ],
    tips: [
      'Klicken Sie in der Kopfzeile auf Layout bearbeiten und ziehen Sie dann die Widgets, um sie neu anzuordnen',
      'Klicken Sie in der Kopfzeile auf die Schaltfläche Anpassen (Reglersymbol), dann auf das Auge neben einem Widget, um es ein- oder auszublenden',
      'Das Dashboard aktualisiert sich in Echtzeit über WebSocket: kein manuelles Aktualisieren nötig',
      'Das Layout wird in diesem Browser gespeichert, für jedes Konto, das sich von hier anmeldet',
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
