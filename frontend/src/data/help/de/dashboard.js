export default {
  helpContent: {
    title: 'Dashboard',
    subtitle: 'Systemübersicht und Überwachung',
    overview: 'Echtzeit-Übersicht Ihrer PKI-Infrastruktur. Widgets zeigen Zertifikatsstatus, Ablaufwarnungen, Systemzustand und aktuelle Aktivitäten an. Das Layout ist vollständig anpassbar per Drag-and-Drop.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Statistiken', text: 'Gesamtzahl CAs, aktive Zertifikate, ausstehende CSRs und bald ablaufende Zertifikate' },
          { label: 'Zertifikatstrend', text: 'Ausstellungsverlauf als Diagramm über die Zeit' },
          { label: 'Statusverteilung', text: 'Kreisdiagramm: gültig / ablaufend / abgelaufen / widerrufen' },
          { label: 'Nächster Ablauf', text: 'Zertifikate, die innerhalb von 30 Tagen ablaufen' },
          { label: 'Systemstatus', text: 'Dienststatus: ACME, SCEP, EST, OCSP, CRL/CDP, Auto-Erneuerung' },
          { label: 'Letzte Aktivitäten', text: 'Neueste Vorgänge im gesamten System' },
          { label: 'Neueste Zertifikate', text: 'Kürzlich ausgestellte oder importierte Zertifikate' },
          { label: 'Zertifizierungsstellen', text: 'CA-Liste mit Ketteninformationen' },
          { label: 'ACME-Konten', text: 'Registrierte ACME-Client-Konten' },
        ]
      },
    ],
    tips: [
      'Ziehen Sie Widgets per Drag-and-Drop, um Ihr Dashboard-Layout anzupassen',
      'Klicken Sie auf das Augen-Symbol in der Kopfzeile, um einzelne Widgets ein-/auszublenden',
      'Das Dashboard aktualisiert sich in Echtzeit über WebSocket — kein manuelles Aktualisieren nötig',
      'Das Layout wird pro Benutzer gespeichert und bleibt über Sitzungen hinweg erhalten',
    ],
  },
  helpGuides: {
    title: 'Dashboard',
    content: `
## Übersicht

Das Dashboard ist Ihre zentrale Überwachungszentrale. Es zeigt Echtzeit-Metriken, Diagramme und Warnungen über Ihre gesamte PKI-Infrastruktur durch anpassbare Widgets an.

## Widgets

### Statistik-Karte
Zeigt vier wichtige Zähler an:
- **Gesamte CAs** — Root- und Intermediate-Zertifizierungsstellen
- **Aktive Zertifikate** — Gültige, nicht widerrufene Zertifikate
- **Ausstehende CSRs** — Zertifikatsignierungsanfragen, die auf Genehmigung warten
- **Bald ablaufend** — Zertifikate, die innerhalb von 30 Tagen ablaufen

### Zertifikatstrend
Ein Liniendiagramm, das die Zertifikatsausstellung über die Zeit zeigt. Bewegen Sie den Mauszeiger über Datenpunkte, um genaue Zahlen zu sehen.

### Statusverteilung
Kreisdiagramm mit der Aufschlüsselung der Zertifikatszustände:
- **Gültig** — Innerhalb des Gültigkeitszeitraums und nicht widerrufen
- **Ablaufend** — Läuft innerhalb von 30 Tagen ab
- **Abgelaufen** — Nach dem „Nicht nach"-Datum
- **Widerrufen** — Explizit widerrufen

### Nächster Ablauf
Listet die Zertifikate auf, die am ehesten ablaufen. Klicken Sie auf ein Zertifikat, um zu seinen Details zu navigieren. Konfigurieren Sie den Schwellenwert unter **Einstellungen → Allgemein**.

### Systemstatus
Zeigt den Zustand der UCM-Dienste:
- ACME-Server (aktiviert/deaktiviert)
- SCEP-Server
- EST-Protokoll (aktiviert/deaktiviert, zugewiesene CA)
- CRL-Auto-Regenerierung mit CDP-Anzahl
- OCSP-Responder
- Auto-Erneuerungsstatus
- Dienst-Betriebszeit

### Letzte Aktivitäten
Ein Live-Feed der neuesten Vorgänge: Zertifikatsausstellung, Widerrufe, Importe, Benutzeranmeldungen. Aktualisiert sich in Echtzeit über WebSocket.

### Zertifizierungsstellen
Schnellansicht aller CAs mit ihrem Typ (Root/Intermediate) und Zertifikatsanzahl.

### ACME-Konten
Listet registrierte ACME-Client-Konten und deren Bestellanzahl auf.

## Anpassung

### Widgets neu anordnen
Ziehen Sie ein Widget an seiner Kopfzeile, um es zu verschieben. Das Layout verwendet ein responsives Raster, das sich an Ihre Bildschirmgröße anpasst.

### Widgets ein-/ausblenden
Klicken Sie auf das **Augen-Symbol** in der Seitenkopfzeile, um die Sichtbarkeit einzelner Widgets umzuschalten. Ausgeblendete Widgets werden über Sitzungen hinweg gespeichert.

### Layout-Persistenz
Ihre Layout-Konfiguration wird pro Benutzer im Browser gespeichert. Sie bleibt über Sitzungen und Geräte mit demselben Browserprofil erhalten.

## Echtzeit-Aktualisierungen
Das Dashboard empfängt Live-Updates über WebSocket. Kein manuelles Aktualisieren nötig — neue Zertifikate, Statusänderungen und Aktivitätseinträge erscheinen automatisch.

> 💡 Wenn die WebSocket-Verbindung unterbrochen ist, erscheint ein gelber Indikator in der Seitenleiste. Die Daten werden bei Wiederverbindung aktualisiert.
`
  }
}
