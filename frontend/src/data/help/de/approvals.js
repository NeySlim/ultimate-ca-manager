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
          { label: 'Abgelaufen', text: 'Die Anfrage wurde nicht vor der Frist geprüft' },
        ]
      },
    ],
    tips: [
      'Jede einzelne Ablehnung stoppt die Genehmigung sofort — dies ist aus Sicherheitsgründen beabsichtigt.',
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
Die Anfrage wurde nicht vor der Frist geprüft. Abgelaufene Anfragen müssen erneut eingereicht werden.

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
