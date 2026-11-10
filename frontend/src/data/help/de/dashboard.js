export default {
  helpContent: {
    title: 'Übersicht',
    subtitle: 'Was zu tun ist und wie es um die PKI steht',
    overview: 'Sechs voneinander unabhängige Karten über den Live-Daten Ihrer PKI. Jede Karte lädt für sich und zeigt ihren eigenen Zustand für Laden, Leer, Fehler oder fehlende Berechtigung. Jeder Zähler mit einer Liste öffnet die Zertifikatsliste, gefiltert auf genau die Zertifikate, die er zählt.',
    sections: [
      {
        title: 'Karten',
        items: [
          { label: 'Zu bearbeiten', text: 'Die sechs dringendsten Einträge, kritische zuerst, jeweils mit Link zum Datensatz; eine eingeklappte Ebene zeigt die Summe je Art, und die vier Erneuerungsarten öffnen die Zertifikatsliste' },
          { label: 'Automatisierungsstatus', text: 'Je Protokoll (ACME, SCEP, EST) die täglichen Erfolge und Fehler sowie der Zustand des Planers' },
          { label: 'Hierarchie', text: 'Die Zertifizierungsstellen als Baum unter ihrer übergeordneten CA, mit CRL- und OCSP-Status, einer Offline- oder Cross-signed-Markierung und den Zertifikaten, die jede in 7 Tagen ausgestellt hat; jede CA öffnet ihre Seite' },
          { label: 'Ablaufhorizont', text: 'Die Zähler für ablaufende und abgelaufene Zertifikate, die jeweils ihre Liste öffnen, und die fünf Zertifikate, die als Nächste ablaufen' },
          { label: 'Compliance', text: 'Aktive Zertifikate nach Schlüsselalgorithmus und Schwäche (RSA unter 3072 Bit, schwacher Signatur-Hash, Serverzertifikate über 398 Tage, unvollständige Kette, kein privater Schlüssel); jeder Zähler öffnet die passende Liste' },
          { label: 'Letzte Vorgänge', text: 'Die fünf neuesten Vorgänge; mit der Audit-Berechtigung öffnet ein Link das gesamte Protokoll' },
        ]
      },
    ],
    tips: [
      'Wählen Sie in der Kopfzeile die Voreinstellung Operator, Manager oder Alle Karten, um festzulegen, welche Karten angezeigt werden',
      'Das Layout wird mit Ihrem Konto gespeichert und folgt Ihnen in jeden Browser',
      'In der Zertifikatsliste erscheinen Filter aus der Übersicht als Chips; entfernen Sie einen mit seinem x',
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
