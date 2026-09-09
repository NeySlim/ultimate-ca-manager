export default {
  helpContent: {
    title: 'Zertifizierungsstellen',
    subtitle: 'Ihre PKI-Hierarchie verwalten',
    overview: 'Erstellen und verwalten Sie Root- und Intermediate-Zertifizierungsstellen. Bauen Sie eine vollständige Vertrauenskette für Ihre Organisation auf. CAs mit privaten Schlüsseln können Zertifikate direkt signieren.',
    sections: [
      {
        title: 'Ansichten',
        items: [
          { label: 'Baumansicht', text: 'Hierarchische Darstellung der Eltern-Kind-CA-Beziehungen' },
          { label: 'Listenansicht', text: 'Flache Tabellenansicht mit Sortierung und Filterung' },
          { label: 'Organisationsansicht', text: 'Gruppiert nach Organisation für Multi-Mandanten-Setups' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Root-CA erstellen', text: 'Selbstsignierte Zertifizierungsstelle der obersten Ebene' },
          { label: 'Intermediate erstellen', text: 'CA, die von einer übergeordneten CA in der Kette signiert wird' },
          { label: 'CA importieren', text: 'Vorhandenes CA-Zertifikat importieren (mit oder ohne privaten Schlüssel)' },
          { label: 'Exportieren', text: 'PEM, DER oder PKCS#12 (P12/PFX) mit Passwortschutz' },
          { label: 'CA erneuern', text: 'Das CA-Zertifikat mit einer neuen Gültigkeitsdauer erneut ausstellen' },
          { label: 'Widerrufen', text: 'Eine Intermediate-CA bei ihrer übergeordneten CA widerrufen: Veröffentlichung in CRL und OCSP der übergeordneten CA, und die CA kann nicht mehr signieren (dauerhaft)' },
          { label: 'Kettenreparatur', text: 'Unterbrochene Eltern-Kind-Beziehungen automatisch reparieren' },
        ]
      },
      {
        title: 'Extern signierte CAs (CSR-Modus, v2.214)',
        content: 'Der Erstellungstyp „Von externer CA signiert (CSR)" deckt das Offline-Root-Muster ab: Das Schlüsselpaar liegt in UCM, das Zertifikat wird extern signiert. Der private Schlüssel verlässt UCM nie.',
        items: [
          { label: 'Erstellen', text: 'UCM generiert das Schlüsselpaar (lokal oder HSM) und einen CSR vom Typ CA — der CSR wird automatisch heruntergeladen' },
          { label: 'Warten auf Zertifikat', text: 'Die wartende CA kann nicht signieren, exportiert werden, übergeordnete CA sein oder offline gehen, bis ihr Zertifikat installiert ist' },
          { label: 'Zertifikat hochladen', text: 'Das extern signierte Zertifikat einfügen oder hochladen (PEM/DER). Sein öffentlicher Schlüssel muss zum gespeicherten privaten Schlüssel passen; CA-Constraints werden erzwungen' },
          { label: 'Kette', text: 'Automatische Verknüpfung, wenn der Aussteller UCM bekannt ist — importieren Sie die externe Root (nur Zertifikat) für eine vollständige Kette' },
          { label: 'Erneuern via CSR', text: 'Stellt einen CSR aus demselben Schlüssel erneut aus (stabile SKI); extern signieren und das neue Zertifikat hochladen' },
          { label: 'Nach der Erneuerung', text: 'Das abgelöste Zertifikat bleibt bis zu seinem notAfter gültig — UCM zeigt seine Seriennummer nach dem Hochladen an; widerrufen Sie es bei der externen Root, wenn ihm nicht mehr vertraut werden soll' },
        ]
      },
      {
        title: 'HSM-gesicherte CAs',
        items: [
          { label: 'Schlüsselspeicher', text: 'Bei der CA-Erstellung Lokal (in DB verschlüsselt) oder HSM wählen' },
          { label: 'Neuen Schlüssel generieren', text: 'Neuen Signaturschlüssel auf dem ausgewählten HSM-Anbieter erstellen' },
          { label: 'Vorhandenen Schlüssel verwenden', text: 'CA an einen ungenutzten Signaturschlüssel auf dem HSM binden' },
          { label: 'Kein privater Schlüssel-Export', text: 'HSM-gesicherte Schlüssel verlassen das HSM nicht — PKCS#12-, JKS- und Nur-Schlüssel-Exporte sind deaktiviert' },
          { label: 'Voraussetzung', text: 'Zuerst einen HSM-Anbieter in der HSM-Verwaltung konfigurieren und verbinden' },
        ]
      },
      {
        title: 'Offline-Modus',
        items: [
          { label: 'Zweck', text: 'Privaten Schlüssel einer CA (typischerweise einer Root) vor Runtime-Nutzung schützen, während Zertifikat, Kette, CRL und OCSP verfügbar bleiben' },
          { label: 'Passwortgeschützt', text: 'Schlüssel wird mit einem benutzerdefinierten Passwort (PKCS#8) verschlüsselt und bleibt in der Datenbank. Wiederherstellung durch Passworteingabe.' },
          { label: 'Datei-exportiert', text: 'Schlüssel wird als passwortgeschützte PEM-Datei einmalig heruntergeladen und aus der Datenbank entfernt. Wiederherstellung durch erneutes Hochladen mit Passwort.' },
          { label: 'Passwort-Richtlinie', text: 'Das Passwort folgt der UCM-Komplexitätsrichtlinie (Länge und Zeichenklassen). Bei Verlust ist der Schlüssel unwiederbringlich.' },
          { label: 'Auswirkung auf Signaturen', text: 'CSR-Signierung, Zertifikatausstellung und CA-Erneuerung sind offline blockiert. CRL und OCSP funktionieren weiter aus zwischengespeicherten Signaturen.' },
          { label: 'Sub-CAs', text: 'Root- und Intermediate-CAs können unabhängig offline genommen werden' },
        ]
      },
      {
        title: 'Externe CRLs für CAs ohne Schlüssel (v2.215)',
        content: 'Eine CA, deren Schlüssel UCM nicht verwenden kann (Offline-CA, Nur-Zertifikat-Import), kann ihre eigene CRL nicht signieren — laden Sie stattdessen eine hoch, die neben dem Offline-Schlüssel erzeugt wurde.',
        items: [
          { label: 'Wo', text: 'CA-Detailansicht › Widerrufsliste (CRL): zeigt die Nummer der ausgelieferten CRL, die Anzahl der Einträge, thisUpdate/nextUpdate sowie eine Warnung, sobald nextUpdate überschritten ist' },
          { label: 'Hochladen', text: 'PEM oder DER, nur vollständige CRLs (keine Delta-CRLs). Die Signatur muss sich gegen das CA-Zertifikat verifizieren lassen und der Aussteller muss zu dessen Subject passen' },
          { label: 'Monotonie', text: 'Ein Upload, der älter ist als die aktuell ausgelieferte CRL (CRL-Nummer oder thisUpdate), wird abgelehnt — stellen Sie sie mit einer höheren CRL-Nummer aus' },
          { label: 'Auslieferung', text: 'Die hochgeladene CRL wird unter dem bestehenden CDP-Pfad der CA ausgeliefert, und OCSP antwortet für die darin aufgeführten Seriennummern mit „widerrufen"' },
          { label: 'Ablauf', text: 'Widerrufen Sie an der Offline-Root, erzeugen Sie die Root-CRL in der Air-Gap-Umgebung und laden Sie sie hier hoch — der Root-Schlüssel geht nie online' },
        ]
      },
    ],
    tips: [
      'CAs mit einem Schlüsselsymbol (🔑) haben einen privaten Schlüssel und können Zertifikate signieren',
      'Nehmen Sie die Root-CA offline, sobald Ihre Intermediates betriebsbereit sind',
      'Verwenden Sie „Datei-exportiert" für stärkste Air-Gap-Isolation; „Passwortgeschützt" für schnelle In-Place-Wiederherstellung',
      'PKCS#12-Export enthält die vollständige Kette und ist ideal für Sicherungen',
    ],
    warnings: [
      'Das Löschen einer CA widerruft NICHT die von ihr ausgestellten Zertifikate — widerrufen Sie diese zuerst',
      'Private Schlüssel werden verschlüsselt gespeichert; der Verlust der Datenbank bedeutet den Verlust der Schlüssel',
      'Offline-Modus-Passwörter sind NICHT wiederherstellbar — bewahren Sie sie vor der Bestätigung in Ihrem Passwortmanager / Vault auf',
    ],
  },
  helpGuides: {
    title: 'Zertifizierungsstellen',
    content: `
## Übersicht

Zertifizierungsstellen (CAs) bilden das Fundament Ihrer PKI. UCM unterstützt mehrstufige CA-Hierarchien mit Root-CAs, Intermediate-CAs und Sub-CAs.

## CA-Typen

### Root-CA
Ein selbstsigniertes Zertifikat, das als Vertrauensanker dient. Root-CAs sollten in Produktionsumgebungen idealerweise offline gehalten werden. In UCM hat eine Root-CA kein übergeordnetes Element.

### Intermediate-CA
Von einer Root-CA oder einer anderen Intermediate-CA signiert. Wird für die tägliche Zertifikatssignierung verwendet. Intermediate-CAs begrenzen den Schadensradius bei einer Kompromittierung.

### Sub-CA
Jede CA, die von einer Intermediate-CA signiert wird und tiefere Hierarchieebenen erstellt.

## Ansichten

### Baumansicht
Zeigt die vollständige CA-Hierarchie als aufklappbaren Baum. Eltern-Kind-Beziehungen werden durch Einrückung und Verbindungslinien visualisiert.

### Listenansicht
Flache Tabelle mit sortierbaren Spalten: Name, Typ, Status, ausgestellte Zertifikate, Ablaufdatum.

### Organisationsansicht
Gruppiert CAs nach ihrem Organisation-Feld (O). Nützlich für Multi-Mandanten-Setups, bei denen verschiedene Abteilungen separate CA-Bäume verwalten.

## Eine CA erstellen

### Root-CA erstellen
1. Klicken Sie auf **Erstellen** → **Root-CA**
2. Füllen Sie die Betreffsfelder aus (CN, O, OU, C, ST, L)
3. Wählen Sie den Schlüsselalgorithmus (RSA 2048/4096, ECDSA P-256/P-384)
4. Legen Sie die Gültigkeitsdauer fest (typischerweise 10-20 Jahre für Root-CAs)
5. Wählen Sie optional ein Zertifikatstemplate
6. Klicken Sie auf **Erstellen**

### Intermediate-CA erstellen
1. Klicken Sie auf **Erstellen** → **Intermediate-CA**
2. Wählen Sie die **übergeordnete CA** (muss einen privaten Schlüssel haben)
3. Füllen Sie die Betreffsfelder aus
4. Legen Sie die Gültigkeitsdauer fest (typischerweise 5-10 Jahre)
5. Klicken Sie auf **Erstellen**

> ⚠ Die Gültigkeit der Intermediate-CA kann die Gültigkeit der übergeordneten CA nicht überschreiten.

### Eine extern signierte CA erstellen (CSR-Modus, v2.214)
Für das Offline-Root-Muster — der Schlüssel der ausstellenden CA liegt in UCM, ihr Zertifikat wird extern signiert:
1. Klicken Sie auf **Erstellen** → Typ **Von externer CA signiert (CSR)**
2. Füllen Sie Subject und Schlüsseleinstellungen aus (lokal oder HSM) — die Gültigkeit bestimmt der externe Signierer
3. Absenden: UCM generiert das Schlüsselpaar und einen CSR vom Typ CA (wird automatisch heruntergeladen)
4. Lassen Sie den CSR von Ihrer externen/Offline-Root-CA signieren
5. Zurück auf der CA (Badge **Warten auf Zertifikat**) klicken Sie auf **Zertifikat hochladen** und stellen das signierte Zertifikat bereit (PEM oder DER)

UCM aktiviert die CA nur, wenn der öffentliche Schlüssel des Zertifikats zum gespeicherten privaten Schlüssel passt und die CA-Constraints erfüllt sind. Die Kette wird automatisch verknüpft, wenn der Aussteller UCM bekannt ist — importieren Sie die externe Root (nur Zertifikat) für eine vollständige Kette. Bis zur Aktivierung kann die wartende CA nicht signieren, exportiert werden, übergeordnete CA sein oder offline gehen.

Zum Erneuern verwenden Sie **Erneuern via CSR**: Ein neuer CSR wird **aus demselben Schlüssel** ausgestellt (die SKI bleibt stabil), extern signiert und über denselben Ablauf hochgeladen.

## Eine CA importieren

Importieren Sie vorhandene CA-Zertifikate über:
- **PEM-Datei** — Zertifikat im PEM-Format
- **DER-Datei** — Binäres DER-Format
- **PKCS#12** — Zertifikat + privater Schlüssel (erfordert Passwort)

Beim Import ohne privaten Schlüssel kann die CA Zertifikate verifizieren, aber keine neuen signieren.

## Eine CA exportieren

Exportformate:
- **PEM** — Base64-kodiertes Zertifikat
- **DER** — Binärformat
- **PKCS#12 (P12/PFX)** — Zertifikat + privater Schlüssel + Kette, passwortgeschützt

> 💡 PKCS#12-Export enthält die vollständige Zertifikatskette und ist ideal für Sicherungen.

## Private Schlüssel

CAs mit einem **Schlüsselsymbol** (🔑) haben einen in UCM gespeicherten privaten Schlüssel und können Zertifikate signieren. CAs ohne Schlüssel dienen nur der Vertrauensvalidierung — sie validieren Ketten, können aber nicht ausstellen.

### Schlüsselspeicherung
Private Schlüssel werden in der UCM-Datenbank verschlüsselt gespeichert. Für höhere Sicherheit erwägen Sie die Verwendung eines HSM-Anbieters (siehe HSM-Seite).

## Kettenreparatur

Wenn Eltern-Kind-Beziehungen unterbrochen sind (z.B. nach einem Import), verwenden Sie **Kettenreparatur**, um die Hierarchie automatisch basierend auf Issuer/Subject-Abgleich wiederherzustellen.

## Eine CA erneuern

Die Erneuerung stellt das CA-Zertifikat mit folgenden Eigenschaften erneut aus:
- Gleicher Betreff und Schlüssel
- Neue Gültigkeitsdauer
- Neue Seriennummer

Vorhandene von der CA signierte Zertifikate bleiben gültig.

## Eine Intermediate-CA widerrufen

Eine Intermediate-CA, deren Schlüssel kompromittiert ist oder die außer Betrieb genommen wird, wird bei ihrer übergeordneten CA widerrufen, wie ein Zertifikat:

1. Wählen Sie die Intermediate-CA aus und klicken Sie auf **CA widerrufen**
2. Wählen Sie den Grund nach RFC 5280 (Schlüsselkompromittierung, CA-Kompromittierung, Betriebseinstellung, ...)
3. Bestätigen Sie: Der Widerruf ist dauerhaft

Was danach passiert:
- Die Seriennummer der CA wird in der **CRL der übergeordneten CA** veröffentlicht (sofort neu erzeugt) und der **OCSP-Responder** der übergeordneten CA antwortet mit \`revoked\` und dem Grund
- Die widerrufene CA **kann nichts mehr signieren**: Zertifikate, CSRs, Erneuerungen, Sub-CAs, und ebenso wenig die CAs unterhalb von ihr
- Von ihr ausgestellte Zertifikate werden von Clients, die die Kette validieren, nicht mehr als vertrauenswürdig eingestuft; ihre eigene CRL und ihr OCSP werden weiter ausgeliefert, bis die CA gelöscht wird
- Das Löschen der widerrufenen CA behält ihren Eintrag in der CRL der übergeordneten CA bis zum ursprünglichen Ablauf des Zertifikats bei

> ⚠ Eine Root-CA kann in UCM nicht widerrufen werden (selbstsigniert: die vertrauenden Parteien entfernen sie aus ihren Trust Stores), und eine von einer externen Root signierte Intermediate wird bei dieser Root widerrufen. Ihre CRL kann dann von UCM ausgeliefert werden (siehe Offline-Modus).

## Eine CA löschen

> ⚠ Das Löschen einer CA entfernt sie aus UCM, widerruft aber NICHT die von ihr ausgestellten Zertifikate. Widerrufen Sie Zertifikate bei Bedarf zuerst.

Das Löschen wird blockiert, wenn die CA untergeordnete CAs hat. Löschen oder übertragen Sie untergeordnete CAs zuerst.

## HSM-gesicherte CAs

UCM kann den Signaturschlüssel einer CA auf einem externen Hardware-Sicherheitsmodul anstelle der lokal verschlüsselten Datenbank speichern. Dies ist die empfohlene Option für Produktions-Root- und -Intermediate-CAs.

### Wann verwenden
- Compliance-Anforderungen (FIPS 140-2/3, eIDAS, Common Criteria)
- Verteidigung in der Tiefe: Schlüssel können nicht exfiltriert werden, selbst wenn der UCM-Host kompromittiert ist
- Zentralisierte Schlüsselverwahrung über mehrere PKI-Tools hinweg

### Voraussetzungen
1. Öffnen Sie **HSM-Verwaltung** und konfigurieren Sie einen Anbieter (PKCS#11 / OpenBao / etc.)
2. Stellen Sie sicher, dass der Anbieter **Aktiv** und **Verbunden** ist

### Schritt für Schritt
1. Öffnen Sie **CA erstellen**
2. Füllen Sie wie üblich Subject und Gültigkeit aus
3. Wechseln Sie unter **Schlüsselspeicher** von *Lokal* zu **HSM**
4. Wählen Sie den HSM-Anbieter
5. Wählen Sie einen Schlüsselmodus:
   - **Neuen Schlüssel generieren** — Bezeichnung angeben (Buchstaben/Ziffern/_/-) und Algorithmus wählen (RSA-2048/3072/4096 oder EC-P256/P384/P521)
   - **Vorhandenen Schlüssel verwenden** — einen ungenutzten Signaturschlüssel auf dem HSM auswählen
6. Absenden. UCM erstellt das CA-Zertifikat und bindet es an den HSM-Schlüssel.

### Einschränkungen
- HSM-gesicherte private Schlüssel **können nicht exportiert werden**. PKCS#12-, JKS- und Nur-Schlüssel-Exportoptionen werden für HSM-CAs ausgeblendet. Nur das Zertifikat (PEM/DER/P7B) kann exportiert werden.
- Es gibt **keine In-Place-Migration** zwischen Lokal und HSM. Um eine bestehende lokale CA auf ein HSM zu „verschieben", erstellen Sie eine neue CA auf dem HSM und stellen Sie Zertifikate neu aus.
- Die in *Vorhandenen Schlüssel verwenden* angebotenen Schlüssel sind auf signaturfähige asymmetrische Schlüssel beschränkt, die noch keiner anderen CA zugeordnet sind.

## Offline-Modus

Nehmen Sie den Signierschlüssel einer CA aus der Laufzeitnutzung, ohne die CA zu löschen. Zertifikat, Kette, CRL und OCSP funktionieren weiter — nur Signieroperationen (CSR signieren, Zertifikat ausstellen, CA erneuern) sind blockiert.

Dies ist der Standardweg, eine Root-CA zwischen seltenen Zeremonien zu schützen und gleichzeitig ihren Trust-Anchor und ihre Widerrufsinfrastruktur online zu halten.

### Zwei Modi

**Passwortgeschützt** — der private Schlüssel bleibt in der UCM-Datenbank, mit einem von Ihnen gewählten Passwort gewrappt (PKCS#8). Klicken Sie zum Reaktivieren auf **Wiederherstellen** und geben Sie das Passwort erneut ein. Schnell und bequem; die Sicherheit hängt von der Passwortstärke und davon ab, dass UCM nicht kompromittiert ist.

**Datei-exportiert** — der private Schlüssel wird als passwortverschlüsselte PEM-Datei einmalig heruntergeladen. Der Schlüssel wird dann **aus der Datenbank entfernt**. Klicken Sie zum Reaktivieren auf **Wiederherstellen**, laden Sie die Datei hoch und geben Sie das Passwort ein. Dies ist die stärkste Option (echtes Air-Gap), aber Sie sind voll für die Datei verantwortlich: bei Verlust ist der Schlüssel unwiederbringlich.

### Passwort-Regeln
Das Passwort folgt der Standard-UCM-Komplexitätsrichtlinie: Mindestlänge, Mischung der Zeichenklassen, keine trivialen Sequenzen. Dieselben Regeln wie für Benutzerpasswörter.

### Schritt für Schritt — Offline nehmen
1. CA-Detailansicht öffnen
2. Auf **Offline nehmen** klicken
3. Erklärung lesen, **Weiter** klicken
4. Modus wählen (*Passwortgeschützt* oder *Datei-exportiert*)
5. Passwort zweimal eingeben
6. Bestätigen. Bei *Datei-exportiert* wird der verschlüsselte Schlüssel sofort heruntergeladen — sicher aufbewahren.

### Schritt für Schritt — Wiederherstellen
1. Detailansicht der offline CA öffnen
2. Auf **Wiederherstellen** klicken
3. Passwort eingeben
4. Bei *Datei-exportiert*: zusätzlich die zuvor heruntergeladene Schlüsseldatei auswählen
5. Bestätigen. Signieroperationen werden sofort wieder verfügbar.

### Auswirkung auf Operationen
| Operation | Online | Offline |
|---|---|---|
| Zertifikat ausstellen | Erlaubt | **Blockiert** |
| CSR signieren | Erlaubt | **Blockiert** |
| CA erneuern | Erlaubt | **Blockiert** |
| Ausgestelltes Zertifikat erneuern | Erlaubt | **Blockiert** |
| CRL / OCSP bereitstellen | Erlaubt | Erlaubt (zwischengespeicherte Signatur) |
| Zertifikat / Kette exportieren | Erlaubt | Erlaubt |
| CA löschen | Erlaubt | Erlaubt |

> ⚠ Offline-Modus-Passwörter sind **nicht wiederherstellbar**. Bewahren Sie sie vor der Bestätigung in Ihrem Passwortmanager / Vault auf. Verlorenes Passwort = unbrauchbare CA = vollständige Neuausstellung der untergeordneten Hierarchie.
`
  }
}