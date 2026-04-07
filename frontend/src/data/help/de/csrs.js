export default {
  helpContent: {
    title: 'Zertifikatsignierungsanfragen',
    subtitle: 'CSR-Workflow verwalten',
    overview: 'Laden Sie Certificate Signing Requests hoch, prüfen und signieren Sie diese. CSRs ermöglichen es externen Systemen, Zertifikate von Ihren CAs anzufordern, ohne private Schlüssel offenzulegen.',
    sections: [
      {
        title: 'Workflow',
        items: [
          { label: 'CSR generieren', text: 'Einen neuen CSR mit Schlüsselpaar direkt in UCM erstellen' },
          { label: 'CSR hochladen', text: 'PEM-kodierte CSR-Dateien akzeptieren oder PEM-Text einfügen' },
          { label: 'Prüfen', text: 'Betreff, SANs, Schlüsseltyp und Signatur vor dem Signieren überprüfen' },
          { label: 'Signieren', text: 'Eine CA auswählen, Zertifikatstyp festlegen, Gültigkeitsdauer einstellen und Zertifikat ausstellen' },
          { label: 'Herunterladen', text: 'Den Original-CSR im PEM-Format herunterladen' },
        ]
      },
      {
        title: 'Tabs',
        items: [
          { label: 'Ausstehend', text: 'CSRs, die auf Prüfung und Signierung warten' },
          { label: 'Verlauf', text: 'Zuvor signierte oder abgelehnte CSRs' },
        ]
      },
    ],
    tips: [
      'CSRs bewahren den privaten Schlüssel des Antragstellers — er verlässt nie dessen System',
      'Sie können nach dem Signieren einen privaten Schlüssel zu einem CSR hinzufügen, wenn er für den PKCS#12-Export benötigt wird',
      'Verwenden Sie den Microsoft CA-Modus, um CSRs über AD CS zu signieren, wenn eine Verbindung zu einer Windows-PKI besteht',
    ],
  },
  helpGuides: {
    title: 'Zertifikatsignierungsanfragen',
    content: `
## Übersicht

Certificate Signing Requests (CSRs) ermöglichen es externen Systemen, Zertifikate anzufordern, ohne ihre privaten Schlüssel offenzulegen. Der CSR enthält den öffentlichen Schlüssel und Betreffsinformationen; der private Schlüssel bleibt beim Antragsteller.

## Tabs

### Ausstehend
CSRs, die auf Prüfung und Signierung warten. Neue CSRs erscheinen hier nach dem Hochladen.

### Verlauf
Zuvor signierte oder abgelehnte CSRs, mit Links zu den resultierenden Zertifikaten.

## CSR generieren

UCM kann einen CSR und ein Schlüsselpaar direkt generieren:

1. Klicken Sie auf **CSR generieren**
2. Füllen Sie die Betreffsfelder aus (CN erforderlich)
3. Fügen Sie bei Bedarf Subject Alternative Names hinzu
4. Wählen Sie Schlüsseltyp und -größe (RSA 2048/4096, ECDSA P-256/P-384)
5. Klicken Sie auf **Generieren**

CSR und privater Schlüssel werden erstellt und in UCM gespeichert. Der CSR erscheint im Tab „Ausstehend" bereit zum Signieren.

> 💡 Dies ist praktisch, wenn UCM den gesamten Lebenszyklus verwalten soll — CSR, Signierung und Schlüsselspeicherung.

## CSR hochladen

1. Klicken Sie auf **CSR hochladen**
2. Fügen Sie entweder PEM-Text ein oder laden Sie eine PEM/DER-Datei hoch
3. UCM validiert die CSR-Signatur und zeigt die Details an
4. Der CSR erscheint im Tab „Ausstehend"

## CSR prüfen

Klicken Sie auf einen CSR, um zu sehen:
- **Betreff** — CN, O, OU, C, usw.
- **SANs** — DNS-Namen, IP-Adressen, E-Mails
- **Schlüsselinfo** — Algorithmus, Größe, öffentlicher Schlüssel-Fingerabdruck
- **Signatur** — Algorithmus und Gültigkeit

## CSR signieren

### Lokale CA-Signierung

1. Wählen Sie einen ausstehenden CSR
2. Klicken Sie auf **Signieren**
3. Wählen Sie die **signierende CA** (muss einen privaten Schlüssel haben)
4. Wählen Sie den **Zertifikatstyp** (Server, Client, Code-Signierung, E-Mail)
5. Legen Sie die **Gültigkeitsdauer** in Tagen fest
5. Wenden Sie optional ein Template für Key Usage und Erweiterungen an
6. Klicken Sie auf **Signieren**

Das resultierende Zertifikat erscheint auf der Zertifikatsseite.

### Microsoft CA-Signierung

Wenn Microsoft CA-Verbindungen konfiguriert sind, erscheint ein **Microsoft CA**-Tab im Signierungsdialog:

1. Wählen Sie einen ausstehenden CSR und klicken Sie auf **Signieren**
2. Wechseln Sie zum **Microsoft CA**-Tab
3. Wählen Sie die **MS CA-Verbindung**
4. Wählen Sie das **Zertifikatstemplate** (automatisch von der CA geladen)
5. Klicken Sie auf **Signieren**

Wenn das Template eine Manager-Genehmigung erfordert, verfolgt UCM die ausstehende Anfrage. Überprüfen Sie den Status über das CSR-Detailpanel.

### Enroll on Behalf Of (EOBO)

Beim Signieren über Microsoft CA können Sie im Namen eines anderen Benutzers registrieren:

1. Wählen Sie die MS CA-Verbindung und das Template
2. Aktivieren Sie **Enroll on Behalf Of (EOBO)**
3. Die Felder **Enrollee DN** und **Enrollee UPN** werden automatisch aus dem CSR-Betreff und der SAN-E-Mail gefüllt
4. Passen Sie die Werte bei Bedarf an und klicken Sie auf **Signieren**

> ⚠️ EOBO erfordert ein auf dem AD CS-Server konfiguriertes Enrollment-Agent-Zertifikat, und das Template muss die Registrierung im Namen anderer Benutzer erlauben.

## Privaten Schlüssel hinzufügen

Nach dem Signieren können Sie dem Zertifikat einen privaten Schlüssel für den PKCS#12-Export hinzufügen. Klicken Sie auf **Schlüssel hinzufügen** am signierten Zertifikat.

> 💡 Dies ist nützlich, wenn der Antragsteller sowohl den CSR als auch den Schlüssel sicher sendet.

## CSRs löschen

Löschen entfernt den CSR aus UCM. Wenn der CSR bereits signiert wurde, ist das resultierende Zertifikat nicht betroffen.
`
  }
}
