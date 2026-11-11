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
    title: 'Übersicht',
    content: `
## Überblick

Die Übersicht ist die Startseite: sechs voneinander unabhängige Karten über den Live-Daten Ihrer PKI. Jede Karte lädt für sich und zeigt ihren eigenen Zustand für Laden, Leer, Fehler oder fehlende Berechtigung.

## Karten

### Zu bearbeiten
Die sechs dringendsten Einträge, kritische zuerst, jeweils mit Link zum Datensatz. Eine eingeklappte Ebene zeigt die Summe je Art; die vier Erneuerungsarten öffnen die Zertifikatsliste.

### Automatisierungsstatus
Je Protokoll (ACME, SCEP, EST) die täglichen Erfolge und Fehler und der letzte Vorgang, dazu der Zustand des Planers.

### Hierarchie
Die Zertifizierungsstellen als Baum unter ihrer übergeordneten CA, mit CRL- und OCSP-Status, einer Offline- oder Cross-signed-Markierung und den Zertifikaten, die jede in 7 Tagen ausgestellt hat. Jede CA öffnet ihre Seite.

### Ablaufhorizont
Die Zähler für ablaufende und abgelaufene Zertifikate, die jeweils ihre Liste öffnen, und die fünf Zertifikate, die als Nächste ablaufen.

### Compliance
Aktive Zertifikate nach Schlüsselalgorithmus und Schwäche: RSA unter 3072 Bit, schwacher Signatur-Hash, Serverzertifikate über 398 Tage, unvollständige Kette, kein privater Schlüssel. Jeder Zähler öffnet die passende Liste.

### Letzte Vorgänge
Die fünf neuesten Vorgänge. Ohne **read:audit** sehen Sie nur Ihre eigenen Ereignisse; mit dieser Berechtigung öffnet ein Link das gesamte Protokoll auf der Seite Audit-Protokolle.

## Gefilterte Liste öffnen
Jeder Zähler mit einer Liste öffnet die Seite Zertifikate, gefiltert auf genau die Zertifikate, die er zählt. Der Filter erscheint als Chip über der Tabelle; entfernen Sie ihn mit seinem x.

## Karten auswählen
Wählen Sie in der Seitenkopfzeile die Voreinstellung **Operator**, **Manager** oder **Alle Karten**, um festzulegen, welche Karten angezeigt werden. Das Layout wird mit Ihrem Konto gespeichert und folgt Ihnen in jeden Browser.

## Aktualisieren
Die Karten laden beim Öffnen der Seite; eine Karte mit Fehler bietet **Erneut versuchen**. Das Verbindungssymbol in der oberen Leiste zeigt den Zustand der Live-Verbindung, und die Statusleiste unten zeigt die Version und ob der Dienst antwortet.
`
  }
}
