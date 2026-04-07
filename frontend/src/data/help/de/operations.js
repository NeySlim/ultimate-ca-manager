export default {
  helpContent: {
    title: 'Operationen',
    subtitle: 'Import, Export & Massenaktionen',
    overview: 'Zentrales Operationszentrum. Importieren Sie Zertifikate aus Dateien oder OPNsense, exportieren Sie Bündel in PEM/P7B-Formaten und führen Sie Massenaktionen über alle Ressourcentypen mit Inline-Suche und Filtern durch.',
    sections: [
      {
        title: 'Seitenleisten-Tabs',
        items: [
          { label: 'Import', text: 'Smart Import mit automatischer Formaterkennung, plus OPNsense-Sync zum Abrufen von Zertifikaten von Firewalls' },
          { label: 'Export', text: 'Zertifikatsbündel pro Ressourcentyp im PEM- oder P7B-Format über Aktionskarten herunterladen' },
          { label: 'Massenaktionen', text: 'Einen Ressourcentyp auswählen und Stapelvorgänge auf mehrere Elemente durchführen' },
        ]
      },
      {
        title: 'Massenaktionen',
        items: [
          { label: 'Zertifikate', text: 'Widerrufen, erneuern, löschen oder exportieren — filtern nach Status und ausstellender CA' },
          { label: 'CAs', text: 'Zertifizierungsstellen löschen oder exportieren' },
          { label: 'CSRs', text: 'Mit einer CA signieren oder ausstehende Anfragen löschen' },
          { label: 'Templates', text: 'Zertifikatstemplates löschen' },
          { label: 'Benutzer', text: 'Benutzerkonten löschen' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie die Ressourcen-Chips, um schnell zwischen Ressourcentypen zu wechseln',
      'Die Inline-Suche und Filter (Status, CA) ermöglichen es, Elemente einzugrenzen, ohne die Symbolleiste zu verlassen',
      'Wechseln Sie zwischen Tabellen- und Korb-Ansicht (Transferpanel) auf dem Desktop',
      'Überprüfen Sie Änderungen vor der Bestätigung von Massenoperationen',
    ],
    warnings: [
      'Massenlöschung ist unwiderruflich — erstellen Sie vorher immer eine Sicherung',
      'Massenwiderruf veröffentlicht aktualisierte CRLs für alle betroffenen CAs',
    ],
  },
  helpGuides: {
    title: 'Operationen',
    content: `
## Übersicht

Massenoperationen und Datenverwaltung. Führen Sie Stapelaktionen über mehrere Ressourcen gleichzeitig durch.

## Import/Export-Tab

Identisch mit der Import/Export-Seite — Smart-Import-Assistent und Massenexport-Funktionalität.

## OPNsense-Tab

Identisch mit der Import/Export OPNsense-Integration — verbinden, durchsuchen und von OPNsense importieren.

## Massenaktionen

Führen Sie Stapeloperationen auf mehreren Ressourcen gleichzeitig durch.

### Funktionsweise
1. Wählen Sie den **Ressourcentyp** (Zertifikate, CAs, CSRs, Templates, Benutzer)
2. Durchsuchen Sie verfügbare Elemente im **linken Panel**
3. Verschieben Sie Elemente mit den Transferpfeilen in das **rechte Panel** (ausgewählt)
4. Wählen Sie die auszuführende **Aktion**
5. Bestätigen und ausführen

### Verfügbare Aktionen nach Ressource

#### Zertifikate
- **Massenwiderruf** — Mehrere Zertifikate auf einmal widerrufen
- **Massenerneuerung** — Mehrere Zertifikate erneuern
- **Massenexport** — Ausgewählte Zertifikate als Bündel herunterladen
- **Massenlöschung** — Ausgewählte Zertifikate dauerhaft entfernen

#### CAs
- **Massenexport** — Ausgewählte CAs herunterladen
- **Massenlöschung** — Ausgewählte CAs entfernen (dürfen keine untergeordneten CAs haben)

#### CSRs
- **Massensignierung** — Mehrere CSRs mit einer ausgewählten CA signieren
- **Massenlöschung** — Ausgewählte CSRs entfernen

#### Templates
- **Massenexport** — Als JSON exportieren
- **Massenlöschung** — Ausgewählte Templates entfernen

#### Benutzer
- **Massendeaktivierung** — Ausgewählte Benutzerkonten deaktivieren
- **Massenlöschung** — Ausgewählte Benutzer dauerhaft entfernen

> ⚠ Massenoperationen sind unwiderruflich. Erstellen Sie immer eine Sicherung, bevor Sie Massenlöschungen oder -widerrufe durchführen.

> 💡 Verwenden Sie die Suche und den Filter im linken Panel, um bestimmte Elemente schnell zu finden.
`
  }
}
