export default {
  helpContent: {
    title: 'Zertifikate',
    subtitle: 'Zertifikate ausstellen, verwalten und überwachen',
    overview: 'Zentrale Verwaltung aller X.509-Zertifikate. Stellen Sie neue Zertifikate von Ihren CAs aus, importieren Sie vorhandene, verfolgen Sie Ablaufdaten und verwalten Sie Erneuerungen und Widerrufe.',
    sections: [
      {
        title: 'Zertifikatsstatus',
        definitions: [
          { term: 'Gültig', description: 'Innerhalb des Gültigkeitszeitraums und nicht widerrufen' },
          { term: 'Ablaufend', description: 'Läuft innerhalb von 30 Tagen ab' },
          { term: 'Abgelaufen', description: 'Nach dem „Nicht nach"-Datum' },
          { term: 'Widerrufen', description: 'Explizit widerrufen (in CRL veröffentlicht)' },
          { term: 'Verwaist', description: 'Die ausstellende CA existiert nicht mehr im System' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Ausstellen', text: 'Ein neues Zertifikat erstellen, das von einer Ihrer CAs signiert wird' },
          { label: 'Importieren', text: 'Ein vorhandenes Zertifikat importieren (PEM, DER oder PKCS#12)' },
          { label: 'Erneuern', text: 'Mit demselben Betreff und einer neuen Gültigkeitsdauer erneut ausstellen' },
          { label: 'Widerrufen', text: 'Als widerrufen markieren mit einem Grund — erscheint in der CRL' },
          { label: 'Sperre aufheben', text: 'Ein mit dem Grund „Zertifikat gesperrt" widerrufenes Zertifikat entsperren — stellt den gültigen Status wieder her' },
          { label: 'Widerrufen & Ersetzen', text: 'Widerrufen und sofort ein Ersatzzertifikat ausstellen' },
          { label: 'Exportieren', text: 'Im PEM-, DER- oder PKCS#12-Format herunterladen' },
          { label: 'Vergleichen', text: 'Zwei Zertifikate nebeneinander vergleichen' },
        ]
      },
    ],
    tips: [
      'Markieren Sie ⭐ wichtige Zertifikate, um sie zu Ihrer Favoritenliste hinzuzufügen',
      'Verwenden Sie Filter, um Zertifikate schnell nach Status, CA oder Suchtext zu finden',
      'Beim Erneuern wird derselbe Betreff beibehalten, aber ein neues Schlüsselpaar generiert',
    ],
    warnings: [
      'Widerruf ist grundsätzlich dauerhaft — außer bei „Zertifikat gesperrt", das aufgehoben werden kann (Sperre aufheben)',
      'Das Löschen eines Zertifikats entfernt es aus UCM, widerruft es aber nicht',
    ],
  },
  helpGuides: {
    title: 'Zertifikate',
    content: `
## Übersicht

Zentrale Verwaltung aller X.509-Zertifikate. Stellen Sie neue Zertifikate aus, importieren Sie vorhandene, verfolgen Sie Ablaufdaten, verwalten Sie Erneuerungen und Widerrufe.

## Zertifikatsstatus

- **Gültig** — Innerhalb des Gültigkeitszeitraums und nicht widerrufen
- **Ablaufend** — Läuft innerhalb von 30 Tagen ab (konfigurierbar)
- **Abgelaufen** — Nach dem „Nicht nach"-Datum
- **Widerrufen** — Explizit widerrufen, in CRL veröffentlicht
- **Verwaist** — Ausstellende CA existiert nicht mehr in UCM

## Zertifikat ausstellen

1. Klicken Sie auf **Zertifikat ausstellen**
2. Wählen Sie die **signierende CA** (muss einen privaten Schlüssel haben)
3. Füllen Sie den Betreff aus (CN ist erforderlich, andere Felder optional)
4. Fügen Sie Subject Alternative Names (SANs) hinzu: DNS-Namen, IPs, E-Mails
5. Wählen Sie Schlüsseltyp und -größe
6. Legen Sie die Gültigkeitsdauer fest
7. Wenden Sie optional ein **Template** an, um Einstellungen vorzufüllen
8. Klicken Sie auf **Ausstellen**

### Templates verwenden
Templates füllen Key Usage, Extended Key Usage, Betreffsstandards und Gültigkeit vor. Wählen Sie ein Template vor dem Ausfüllen des Formulars, um Zeit zu sparen.

## Zertifikate importieren

Unterstützte Formate:
- **PEM** — Einzelne oder gebündelte Zertifikate
- **DER** — Binärformat
- **PKCS#12 (P12/PFX)** — Zertifikat + Schlüssel + Kette (Passwort erforderlich)
- **PKCS#7 (P7B)** — Zertifikatskette ohne Schlüssel

## Zertifikat erneuern

Eine Erneuerung erstellt ein neues Zertifikat mit:
- Gleichem Betreff und SANs
- Neuem Schlüsselpaar (automatisch generiert)
- Neuer Gültigkeitsdauer
- Neuer Seriennummer

Das Originalzertifikat bleibt gültig, bis es abläuft oder widerrufen wird.

## Zertifikat widerrufen

1. Wählen Sie das Zertifikat → **Widerrufen**
2. Wählen Sie einen Widerrufsgrund (Schlüsselkompromittierung, CA-Kompromittierung, Zugehörigkeitsänderung, Ersetzt, Betriebseinstellung, Zertifikat gesperrt, usw.)
3. Bestätigen Sie den Widerruf

Widerrufene Zertifikate werden bei der nächsten Regenerierung in der CRL veröffentlicht.

> ⚠ Widerruf ist grundsätzlich dauerhaft — außer bei **Zertifikat gesperrt**, das aufgehoben werden kann.

### Sperre aufheben

Wenn ein Zertifikat mit dem Grund **Zertifikat gesperrt** widerrufen wurde, kann es auf den gültigen Status zurückgesetzt werden:

1. Öffnen Sie die Details des widerrufenen Zertifikats
2. Die Schaltfläche **Sperre aufheben** erscheint in der Aktionsleiste (nur für Widerrufe mit Zertifikat gesperrt)
3. Klicken Sie auf **Sperre aufheben**, um das Zertifikat wiederherzustellen
4. Das Zertifikat kehrt zum gültigen Status zurück, die CRL wird regeneriert und der OCSP-Cache aktualisiert

> 💡 Zertifikat gesperrt ist nützlich für vorübergehende Sperrungen (z.B. verlorenes Gerät, laufende Untersuchung).

### Widerrufen & Ersetzen
Kombiniert Widerruf mit sofortiger Neuausstellung. Das neue Zertifikat übernimmt denselben Betreff und dieselben SANs.

## Zertifikate exportieren

Exportformate:
- **PEM** — Nur Zertifikat
- **PEM + Kette** — Zertifikat mit vollständiger Ausstellerkette
- **DER** — Binärformat
- **PKCS#12** — Zertifikat + Schlüssel + Kette, passwortgeschützt

## Favoriten

Markieren Sie ⭐ wichtige Zertifikate als Lesezeichen. Favoriten erscheinen in gefilterten Ansichten zuerst und sind über den Favoriten-Filter zugänglich.

## Zertifikate vergleichen

Wählen Sie zwei Zertifikate aus und klicken Sie auf **Vergleichen**, um einen Vergleich von Betreff, SANs, Key Usage, Gültigkeit und Erweiterungen nebeneinander zu sehen.

## Filtern & Suchen

- **Statusfilter** — Gültig, Ablaufend, Abgelaufen, Widerrufen, Verwaist
- **CA-Filter** — Zertifikate einer bestimmten CA anzeigen
- **Textsuche** — Nach CN, Seriennummer oder SAN suchen
- **Sortierung** — Nach Name, Ablaufdatum, Erstellungsdatum, Status
`
  }
}
