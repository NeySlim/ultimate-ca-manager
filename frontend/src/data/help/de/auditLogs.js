export default {
  helpContent: {
    title: 'Audit-Protokolle',
    subtitle: 'Aktivitätsverfolgung und Compliance',
    overview: 'Vollständiger Audit-Trail aller in UCM durchgeführten Vorgänge. Verfolgen Sie, wer was, wann und von wo aus getan hat. Unterstützt Filterung, Suche, Export und Integritätsüberprüfung.',
    sections: [
      {
        title: 'Filter',
        items: [
          { label: 'Aktionstyp', text: 'Nach Vorgangstyp filtern (Erstellen, Aktualisieren, Löschen, Anmelden, usw.)' },
          { label: 'Benutzer', text: 'Nach dem Benutzer filtern, der die Aktion ausgeführt hat' },
          { label: 'Status', text: 'Nur erfolgreiche oder fehlgeschlagene Vorgänge anzeigen' },
          { label: 'Datumsbereich', text: 'Von/Bis-Daten festlegen, um den Zeitraum einzugrenzen' },
          { label: 'Suche', text: 'Freitextsuche über alle Protokolleinträge' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Exportieren', text: 'Protokolle im JSON- oder CSV-Format herunterladen' },
          { label: 'Bereinigen', text: 'Alte Protokolle mit konfigurierbarer Aufbewahrungsfrist (Tage) löschen' },
          { label: 'Integrität prüfen', text: 'Protokollkettenintegrität überprüfen, um Manipulationen zu erkennen' },
        ]
      },
    ],
    tips: [
      'Exportieren Sie Protokolle regelmäßig für Compliance- und Archivierungszwecke',
      'Fehlgeschlagene Anmeldeversuche werden mit Quell-IP für die Sicherheitsüberwachung protokolliert',
      'Protokolleinträge enthalten den User Agent zur Identifizierung von Client-Anwendungen',
    ],
    warnings: [
      'Protokollbereinigung ist unwiderruflich: exportierte Daten können nicht wieder importiert werden',
    ],
  },
  helpGuides: {
    title: 'Audit-Protokolle',
    content: `
## Übersicht

Vollständiger Audit-Trail aller Vorgänge in UCM. Jede Aktion. Zertifikatsausstellung, Widerruf, Benutzeranmeldung, Einstellungsänderung: wird mit Details darüber protokolliert, wer, was, wann und wo.

## Protokolleintrag-Details

Jeder Protokolleintrag erfasst:
- **Zeitstempel**: Wann die Aktion stattfand
- **Benutzer**: Wer die Aktion ausgeführt hat
- **Aktion**: Was getan wurde (Erstellen, Aktualisieren, Löschen, Anmelden, usw.)
- **Ressource**: Was betroffen war (Zertifikat, CA, Benutzer, usw.)
- **Status**: Erfolg oder Fehlschlag
- **IP-Adresse**: Quell-IP der Anfrage
- **User Agent**: Kennung der Client-Anwendung
- **Details**: Zusätzlicher Kontext (Fehlermeldungen, geänderte Werte)

## Filterung

### Nach Aktion
Eine oder mehrere Aktionsnamen auswählen, zum Beispiel \`certificate_issued\` oder \`login_success\`.

### Nach Benutzer
Nur Aktionen eines bestimmten Benutzers anzeigen.

### Nach Status
- **Erfolg**: Vorgänge, die erfolgreich abgeschlossen wurden
- **Fehlgeschlagen**: Vorgänge, die fehlschlugen (Authentifizierungsfehler, Zugriff verweigert, Fehler)

### Nach Datumsbereich
Legen Sie **Von**- und **Bis**-Daten fest, um den Zeitraum einzugrenzen.

### Textsuche
Freitextsuche in Benutzername, Aktion, Details, Ressourcentyp und IP-Adresse; Ressourcenname und ID werden nicht durchsucht.

## Export

Gefilterte Protokolle exportieren in:
- **JSON**: Maschinenlesbar, enthält alle Felder
- **CSV**: Tabellenkalkulationskompatibel, enthält die wichtigsten Felder

Exporte wenden nur den Datumsbereich an, bis zu 10.000 Einträge: Die übrigen Filter werden nicht angewendet.

## Bereinigung

Alte Protokolle basierend auf der Aufbewahrungsfrist löschen:
1. Klicken Sie auf **Bereinigen**
2. Legen Sie die Aufbewahrungsfrist in Tagen fest
3. Bestätigen Sie die Bereinigung

> ⚠ Protokollbereinigung ist unwiderruflich. Exportieren Sie wichtige Protokolle vor dem Löschen.

## Integritätsüberprüfung

Klicken Sie auf **Integrität prüfen**, um die Audit-Protokollkette zu überprüfen. UCM verwendet Hash-Verkettung, um einen innerhalb der Kette geänderten oder entfernten Eintrag zu erkennen; das Entfernen der letzten Einträge hinterlässt in der Kette selbst keine Spur, weshalb die Syslog-Weiterleitung eine Kopie andernorts aufbewahrt.

## Syslog-Weiterleitung

Konfigurieren Sie die Remote-Syslog-Weiterleitung unter **Einstellungen → Audit**, um Protokollereignisse in Echtzeit an einen externen SIEM- oder Syslog-Server zu senden.
`
  }
}
