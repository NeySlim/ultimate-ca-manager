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
          { label: 'Kettenreparatur', text: 'Unterbrochene Eltern-Kind-Beziehungen automatisch reparieren' },
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
    ],
    tips: [
      'CAs mit einem Schlüsselsymbol (🔑) haben einen privaten Schlüssel und können Zertifikate signieren',
      'Verwenden Sie Intermediate-CAs für die tägliche Signierung, halten Sie die Root-CA wenn möglich offline',
      'PKCS#12-Export enthält die vollständige Kette und ist ideal für Sicherungen',
    ],
    warnings: [
      'Das Löschen einer CA widerruft NICHT die von ihr ausgestellten Zertifikate — widerrufen Sie diese zuerst',
      'Private Schlüssel werden verschlüsselt gespeichert; der Verlust der Datenbank bedeutet den Verlust der Schlüssel',
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
`
  }
}
