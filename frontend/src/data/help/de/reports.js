export default {
  helpContent: {
    title: 'Berichte',
    subtitle: 'PKI-Compliance- und Inventarberichte',
    overview: 'Erstellen, herunterladen und planen Sie Berichte für die Compliance-Prüfung. Berichte umfassen Zertifikatsinventar, ablaufende Zertifikate, CA-Hierarchie, Audit-Aktivität und Richtlinien-Compliance-Status. Laden Sie einen PDF-Managementbericht für die Unternehmensführung herunter.',
    sections: [
      {
        title: 'Berichtstypen',
        items: [
          { label: 'Zertifikatsinventar', text: 'Vollständige Liste aller Zertifikate mit Status' },
          { label: 'Ablaufende Zertifikate', text: 'Zertifikate, die innerhalb eines bestimmten Zeitfensters ablaufen' },
          { label: 'CA-Hierarchie', text: 'Struktur der Zertifizierungsstellen und Statistiken' },
          { label: 'Audit-Zusammenfassung', text: 'Sicherheitsereignisse und Benutzeraktivitätsübersicht' },
          { label: 'Compliance-Status', text: 'Richtlinien-Compliance und Verstöße' },
          { label: 'Widerrufene Zertifikate', text: 'Im Zeitraum widerrufene Zertifikate mit Datum und Grund' },
        ]
      },
      {
        title: 'PDF-Managementbericht',
        items: [
          { label: 'PDF herunterladen', text: 'Professioneller PDF-Bericht mit einem Klick für Management und Auditoren' },
          { label: 'Inhalt', text: 'Zusammenfassung, Risikobewertung, Zertifikatsinventar, Compliance-Bewertungen, CA-Infrastruktur, Audit-Aktivität und Empfehlungen' },
          { label: 'Diagramme & Visualisierungen', text: 'Enthält Risikoanzeige, Statusverteilung, Ablaufzeitachse und Compliance-Aufschlüsselung' },
        ]
      },
      {
        title: 'Planung',
        items: [
          { label: 'Tab Zeitplan', text: 'Haken Sie einen beliebigen Datenbericht oder eine PDF-Vorlage an und legen Sie dann Häufigkeit (täglich, wöchentlich oder monatlich), Uhrzeit (UTC), Format und Empfänger fest' },
          { label: 'Anhang', text: 'Der Bericht wird der E-Mail in seinem Format angehängt: CSV oder JSON für Datenberichte, PDF für die PDF-Vorlagen' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie den PDF-Managementbericht für Managementprüfungen und Compliance-Audits.',
      'Laden Sie Berichte als CSV für Tabellenkalkulationsanalyse oder JSON für Automatisierung herunter.',
      'Verwenden Sie die Testversand-Funktion, um die E-Mail-Zustellung vor der Aktivierung von Zeitplänen zu überprüfen.',
    ],
  },
  helpGuides: {
    title: 'Berichte',
    content: `
## Übersicht

Erstellen, herunterladen und planen Sie PKI-Compliance-Berichte. Berichte bieten Einblick in Ihre Zertifikatsinfrastruktur für Auditing, Compliance und Betriebsplanung.

## Berichtstypen

### Zertifikatsinventar
Vollständige Liste aller von UCM verwalteten Zertifikate. Enthält Betreff, Aussteller, Seriennummer, Gültigkeitsdaten, Schlüsseltyp und aktuellen Status. Verwenden Sie diesen für Compliance-Audits und Infrastrukturdokumentation.

### Ablaufende Zertifikate
Zertifikate, die innerhalb eines bestimmten Zeitfensters ablaufen (Standard: 30 Tage). Kritisch zur Vermeidung von Ausfällen, überprüfen Sie diesen Bericht regelmäßig oder planen Sie ihn für die tägliche Zustellung.

### CA-Hierarchie
Struktur der Zertifizierungsstellen mit Eltern-Kind-Beziehungen, Zertifikatsanzahl pro CA und CA-Status. Nützlich zum Verständnis Ihrer PKI-Topologie.

### Audit-Zusammenfassung
Sicherheitsereignisse und Benutzeraktivitätsübersicht. Enthält Anmeldeversuche, Zertifikatsvorgänge, Richtlinienverstöße und Konfigurationsänderungen. Unverzichtbar für Sicherheitsaudits.

### Compliance-Status
Richtlinien-Compliance und Verstöße. Zeigt, welche Zertifikate Ihren Richtlinien entsprechen und welche dagegen verstoßen. Erforderlich für die regulatorische Compliance.

### Widerrufene Zertifikate
Im gewählten Zeitraum (Standard: 30 Tage) widerrufene Zertifikate mit Widerrufsdatum und Grund. Nutzen Sie ihn, um Widerrufe und ihre Ursachen zu verfolgen.

## PDF-Managementbericht

Öffnen Sie den Tab **PDF-Berichte** und klicken Sie bei der Vorlage **Zusammenfassung** auf **PDF herunterladen**, um einen professionellen Managementbericht zu erstellen, der für Managementprüfungen, Vorstandspräsentationen und Compliance-Audits geeignet ist.

### Inhalt
Der PDF-Bericht enthält 9 Abschnitte:
1. **Deckblatt**: Schlüsselkennzahlen, Risikoanzeige und wichtige Erkenntnisse auf einen Blick
2. **Inhaltsverzeichnis**: Schnelle Navigation
3. **Zusammenfassung**: Gesamter PKI-Zustand, Zertifikatsverteilung und Risikostufe
4. **Risikobewertung**: Kritische Befunde, ablaufende Zertifikate, schwache Algorithmen
5. **Zertifikatsinventar**: Aufschlüsselung nach Status, Schlüsseltyp und ausstellender CA
6. **Compliance-Analyse**: Bewertungsverteilung, Notenaufschlüsselung, Kategoriebewertungen
7. **Zertifikatslebenszyklus**: Ablaufzeitachse und Automatisierungsrate
8. **CA-Infrastruktur**: Root- und Intermediate-CA-Details, Hierarchie
9. **Empfehlungen**: Handlungsempfehlungen basierend auf dem aktuellen PKI-Zustand

### Diagramme & Visualisierungen
Der Bericht enthält visuelle Elemente: Risikoanzeige, Statusverteilung, Compliance-Notenaufschlüsselung und Ablaufzeitachse, konzipiert für nicht-technische Stakeholder.

> 💡 Der PDF-Bericht wird aus Live-Daten generiert. Laden Sie ihn vor Meetings herunter, um den aktuellsten Stand zu erhalten.

## Berichte erstellen

1. Finden Sie den gewünschten Bericht in der Liste
2. Klicken Sie auf **▶ Generieren**, um eine Vorschau zu erstellen
3. Die Vorschau erscheint unten als formatierte Tabelle
4. Klicken Sie auf **Schließen**, um die Vorschau zu verwerfen

## Berichte herunterladen

Jede Berichtszeile hat Download-Schaltflächen:
- **CSV**: Tabellenformat für Excel, Google Sheets oder LibreOffice
- **JSON**: Strukturierte Daten für Automatisierung und Integration

> 💡 CSV-Berichte sind einfacher für nicht-technische Stakeholder. JSON eignet sich besser für Skripte und API-Integrationen.

## Berichte planen

### Was planbar ist
Jeder Datenbericht und jede PDF-Vorlage kann geplant werden, jeweils mit eigener Häufigkeit, Uhrzeit und eigenen Empfängern. Planen Sie **Ablaufende Zertifikate** täglich, um ablaufende Zertifikate zu erkennen, bevor sie Ausfälle verursachen.

### Häufigkeit
**Täglich**, **Wöchentlich** (Wochentag wählen) oder **Monatlich** (Tag des Monats wählen), zu einer in UTC angegebenen Uhrzeit.

### Konfiguration
1. Öffnen Sie den Tab **Zeitplan**
2. Haken Sie die Berichte an, die Sie planen möchten
3. Legen Sie Häufigkeit, Uhrzeit und, bei Datenberichten, das Format (CSV oder JSON) fest
4. Fügen Sie Empfänger-E-Mail-Adressen hinzu (Eingabetaste drücken oder auf Hinzufügen klicken)
5. Klicken Sie auf Speichern

Jeder geplante Bericht wird der E-Mail in seinem Format angehängt: CSV oder JSON für Datenberichte, PDF für die PDF-Vorlagen.

### Testversand
Bevor Sie Zeitpläne aktivieren, verwenden Sie den ✈️-Button in jeder Berichtszeile, um einen Testbericht an eine bestimmte E-Mail-Adresse zu senden. Dies überprüft, ob SMTP korrekt konfiguriert ist und das Berichtsformat Ihren Anforderungen entspricht.

> ⚠ Geplante Berichte erfordern eine SMTP-Konfiguration unter **Einstellungen → E-Mail**. Der Testversand schlägt fehl, wenn SMTP nicht eingerichtet ist.

## Berechtigungen

- **read:reports**: Berichte erstellen und herunterladen
- **read:audit + export:audit**: PDF-Managementbericht herunterladen
- **write:settings**: Berichtzeitpläne konfigurieren

> 💡 Planen Sie zuerst den Bericht Ablaufende Zertifikate: er ist betrieblich am wertvollsten und hilft, zertifikatsbezogene Ausfälle zu vermeiden.
`
  }
}
