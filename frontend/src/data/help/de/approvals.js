export default {
  helpContent: {
    title: 'Genehmigungsanfragen',
    subtitle: 'Verwaltung des Zertifikatsgenehmigungsworkflows',
    overview: 'Überprüfen und verwalten Sie Zertifikatsgenehmigungsanfragen. Wenn eine Richtlinie eine Genehmigung erfordert, wird die Zertifikatsausstellung pausiert, bis die erforderliche Anzahl von Genehmigern die Anfrage geprüft und genehmigt hat.',
    sections: [
      {
        title: 'Anfragelebenszyklus',
        items: [
          { label: 'Ausstehend', text: 'Wartet auf Prüfung — Zertifikat kann noch nicht ausgestellt werden' },
          { label: 'Genehmigt', text: 'Alle erforderlichen Genehmigungen erhalten — Zertifikat kann ausgestellt werden' },
          { label: 'Abgelehnt', text: 'Jede Ablehnung stoppt die Anfrage sofort' },
          { label: 'Abgelaufen', text: 'Nicht innerhalb von sieben Tagen entschieden; als abgelaufen geschlossen und nie als ausstehend gezählt' },
        ]
      },
      {
        title: 'Woher Anfragen kommen',
        items: [
          { label: 'Ausstellungsformular', text: 'Eine Zertifikatsanfrage, die einer Richtlinie mit Genehmigungspflicht entspricht' },
          { label: 'CSR signieren und Massensignierung', text: 'Das Signieren einer gespeicherten Anfrage, einzeln oder aus Operationen, wird auf dieselbe Weise eingereiht; die Genehmigung führt die Signierung aus' },
          { label: 'Erneuerung', text: 'Das Erneuern eines Zertifikats, einzeln oder in Masse, wird ebenfalls eingereiht; eine Erneuerung, die nicht ausgeführt werden könnte (widerrufen, Schlüssel nicht vom Server gehalten), wird sofort abgelehnt' },
          { label: 'Administratoren', text: 'Umgehen die Warteschlange auf jedem Pfad, wie im Ausstellungsformular' },
        ]
      },
      {
        title: 'Für Sie geschlossene Anfragen',
        items: [
          { label: 'Direkt signiert oder erneuert', text: 'Eine eingereihte Anfrage, deren Ziel ein Administrator inzwischen signiert oder erneuert hat, wird durch diese Aktion als genehmigt geschlossen und mit dem Zertifikat verknüpft' },
          { label: 'Gelöscht oder widerrufen', text: 'Eine Anfrage, deren Ziel gelöscht oder widerrufen wurde, wird als abgelehnt geschlossen; bei „Zertifikat gesperrt" wartet die Erneuerungsanfrage, bis die Sperre aufgehoben wird' },
          { label: 'Bereits erfüllt', text: 'Das Genehmigen einer bereits erfüllten Anfrage schließt sie auf dem vorhandenen Zertifikat; das Genehmigen einer von mehreren Anfragen für dasselbe Ziel schließt die anderen als von Ihnen genehmigt' },
          { label: 'Ziel nicht mehr vorhanden', text: 'Das Genehmigen einer Anfrage, deren gespeicherte Anfrage, Zertifikat oder CA nicht mehr existiert, schließt sie als abgelehnt' },
          { label: 'Frist', text: 'Eine Anfrage wartet sieben Tage; danach wird sie als abgelaufen geschlossen, nie als ausstehend gezählt, und der Erneuerungsplaner nimmt die Arbeit für ihr Zertifikat wieder auf' },
        ]
      },
    ],
    tips: [
      'Jede einzelne Ablehnung stoppt die Genehmigung sofort — dies ist aus Sicherheitsgründen beabsichtigt.',
      'Während eine Erneuerung auf Genehmigung wartet, überlässt der Planer das Zertifikat dieser Entscheidung, solange sie vor dem Ablauf des Zertifikats fallen kann.',
      'Genehmigungskommentare werden im Audit-Trail für die Compliance protokolliert.',
    ],
  },
  helpGuides: {
    title: 'Genehmigungsanfragen',
    content: `
## Übersicht

Die Genehmigungsseite zeigt alle Zertifikatsanfragen, die vor der Ausstellung eine manuelle Genehmigung erfordern. Genehmigungsworkflows werden in **Richtlinien** konfiguriert — wenn bei einer Richtlinie „Genehmigung erforderlich" aktiviert ist, erstellt jede übereinstimmende Zertifikatsanfrage hier eine Genehmigungsanfrage.

## Anfragelebenszyklus

### Ausstehend
Die Anfrage wartet auf Prüfung. Das Zertifikat kann nicht ausgestellt werden, bis die erforderliche Anzahl von Genehmigern zugestimmt hat. Ausstehende Anfragen werden standardmäßig zuerst angezeigt.

### Genehmigt
Alle erforderlichen Genehmigungen wurden erhalten. Das Zertifikat wird nach der Genehmigung automatisch ausgestellt.

### Abgelehnt
Jede einzelne Ablehnung stoppt die Anfrage sofort. Das Zertifikat wird nicht ausgestellt. Ein Ablehnungskommentar ist erforderlich, um den Grund zu erläutern.

### Abgelaufen
Die Anfrage wurde nicht innerhalb von sieben Tagen entschieden. Abgelaufene Anfragen müssen erneut eingereicht werden.

## Woher Anfragen kommen
Neben dem Ausstellungsformular reiht eine Richtlinie mit Genehmigungspflicht auch ein:
- **CSR signieren** und **Massensignierung** aus Operationen: die Genehmigung führt die Signierung aus
- **Erneuern** und **Massenerneuerung**: die Genehmigung führt die Erneuerung aus; eine Erneuerung, die nicht ausgeführt werden könnte (widerrufenes Zertifikat, Schlüssel nicht vom Server gehalten), wird sofort abgelehnt statt eingereiht

Administratoren umgehen die Warteschlange auf jedem Pfad.

## Für Sie geschlossene Anfragen
- Eine eingereihte Anfrage, deren Ziel ein Administrator inzwischen **direkt signiert oder erneuert** hat, wird durch diese Aktion als genehmigt geschlossen und mit dem Zertifikat verknüpft
- Eine Anfrage, deren Ziel **gelöscht oder widerrufen** wurde, wird als abgelehnt geschlossen; bei „Zertifikat gesperrt" wartet die Erneuerungsanfrage, bis die Sperre aufgehoben wird
- Das Genehmigen einer **bereits erfüllten** Anfrage schließt sie auf dem vorhandenen Zertifikat; das Genehmigen einer von mehreren Anfragen für dasselbe Ziel schließt die anderen als von Ihnen genehmigt
- Das Genehmigen einer Anfrage, deren gespeicherte Anfrage, Zertifikat oder CA **nicht mehr existiert**, schließt sie als abgelehnt

Webhooks werden über diese Schließungen wie über eine Ablehnung informiert.

## Frist
Eine Anfrage wartet **sieben Tage** auf eine Entscheidung. Danach wird sie als abgelaufen geschlossen, nie als ausstehend gezählt, und der Erneuerungsplaner nimmt die Arbeit für ihr Zertifikat wieder auf. Während eine Erneuerung auf Genehmigung wartet, überlässt der Planer das Zertifikat dieser Entscheidung, solange sie vor dem Ablauf des Zertifikats fallen kann.

## Eine Anfrage genehmigen

1. Klicken Sie auf eine ausstehende Anfrage, um ihre Details anzuzeigen
2. Prüfen Sie die Zertifikatsdetails, den Antragsteller und die zugehörige Richtlinie
3. Klicken Sie auf **Genehmigen** und fügen Sie optional einen Kommentar hinzu
4. Die Genehmigung wird mit Ihrem Benutzernamen und Zeitstempel aufgezeichnet

## Eine Anfrage ablehnen

1. Klicken Sie auf eine ausstehende Anfrage, um ihre Details anzuzeigen
2. Klicken Sie auf **Ablehnen**
3. Geben Sie einen **Ablehnungsgrund** ein (erforderlich) — dieser wird für die Audit-Compliance protokolliert
4. Die Anfrage wird sofort gestoppt

> ⚠ Jede einzelne Ablehnung stoppt die gesamte Anfrage. Dies ist beabsichtigt — wenn ein Prüfer ein Problem feststellt, sollte die Ausstellung nicht fortgesetzt werden.

## Genehmigungsverlauf

Jede Anfrage enthält eine vollständige Genehmigungszeitleiste mit:
- Wer genehmigt oder abgelehnt hat (Benutzername)
- Wann die Aktion durchgeführt wurde (Zeitstempel)
- Bereitgestellter Kommentar (falls vorhanden)

Dieser Verlauf ist unveränderlich und Teil des Audit-Trails.

## Filterung

Verwenden Sie die Statusfilterleiste oben, um anzuzeigen:
- **Ausstehend** — Anfragen, die auf Ihre Prüfung warten
- **Genehmigt** — Kürzlich genehmigte Anfragen
- **Abgelehnt** — Abgelehnte Anfragen mit Gründen
- **Gesamt** — Alle Anfragen unabhängig vom Status

## Berechtigungen

- **read:approvals** — Genehmigungsanfragen anzeigen
- **write:approvals** — Anfragen genehmigen oder ablehnen

> 💡 Richten Sie E-Mail-Benachrichtigungen in Richtlinien ein, damit Genehmiger benachrichtigt werden, wenn neue Anfragen eingehen.
`
  }
}
