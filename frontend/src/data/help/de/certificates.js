export default {
  helpContent: {
    title: 'Zertifikate',
    subtitle: 'Zertifikate ausstellen, verwalten und überwachen',
    overview: 'Zentrale Verwaltung aller X.509-Zertifikate. Stellen Sie neue Zertifikate von Ihren CAs aus, importieren Sie vorhandene, verfolgen Sie Ablaufdaten und verwalten Sie Erneuerungen und Widerrufe.',
    sections: [
      {
        title: "Konformitätsprüfung",
        content: "Die Aktion „Prüfen“ in den Zertifikatdetails führt das Zertifikat durch Standard-Linter und zeigt die Befunde. Nur informativ — blockiert nie die Ausstellung.",
        items: [
          { label: "Profile", text: "RFC 5280 (immer relevant) und CA/Browser Forum Baseline Requirements (TLS-Serverzertifikate)" },
          { label: "Schweregrade", text: "Befunde werden eingestuft: fatal, error, warning, notice, info" },
          { label: "Engine", text: "Angetrieben von pkilint (und zlint, falls dessen Binary vorhanden) — optionale Serverabhängigkeit" },
          { label: "Interne PKI", text: "CA/Browser-Forum-Regeln gelten für öffentliche Zertifikate; bei interner PKI sind nicht zutreffende Befunde zu erwarten" },
        ]
      },
      {
        title: 'Zertifikatsstatus',
        definitions: [
          { term: 'Gültig', description: 'Innerhalb des Gültigkeitszeitraums und nicht widerrufen' },
          { term: 'Ablaufend', description: 'Läuft innerhalb von 30 Tagen ab' },
          { term: 'Abgelaufen', description: 'Nach dem „Nicht nach"-Datum' },
          { term: 'Widerrufen', description: 'Explizit widerrufen (in CRL veröffentlicht)' },
          { term: 'Verwaist', description: 'Die ausstellende CA existiert nicht mehr im System' },
          { term: 'Archiviert', description: 'Durch eine Erneuerung oder erneute Registrierung ersetzt, die den alten Datensatz zur Historie aufbewahrt hat (SCEP, EST, WSTEP, ACME, OCSP-Responder); wird mit dem Statusfilter „Archiviert" aufgelistet' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Ausstellen', text: 'Ein neues Zertifikat erstellen, das von einer Ihrer CAs signiert wird' },
          { label: 'Importieren', text: 'Ein vorhandenes Zertifikat importieren (PEM, DER oder PKCS#12)' },
          { label: 'Erneuern', text: 'In-place seit v2.214: gleiche id/refid, neue Seriennummer und Gültigkeit — die ersetzte Seriennummer bleibt bis zum alten Ablaufdatum auf der CRL. Ein widerrufenes Zertifikat kann nicht erneuert werden' },
          { label: 'Umbenennen', text: 'Einen vom CN unabhängigen Anzeigenamen festlegen (Standard: CN oder erster SAN-DNS-Name bei Zertifikaten ohne CN)' },
          { label: 'Widerrufen', text: 'Als widerrufen markieren mit einem Grund — erscheint in der CRL' },
          { label: 'Sperre aufheben', text: 'Ein mit dem Grund „Zertifikat gesperrt" widerrufenes Zertifikat entsperren — stellt den gültigen Status wieder her' },
          { label: 'Widerrufen & Ersetzen', text: 'Widerrufen und sofort ein Ersatzzertifikat ausstellen' },
          { label: 'Exportieren', text: 'Im PEM-, DER- oder PKCS#12-Format herunterladen' },
          { label: 'PKCS#12-Kompatibilitätsmodus (v2.222)', text: 'Die Exportdialoge bieten ein 3DES/SHA-1-Profil für Importer, die das AES-256-Standardarchiv als falsches Passwort ablehnen: Android 15 und älter, macOS 14 und älter, Windows Server 2016 und älter, altes Java. Standardmäßig aus, schützt die Datei schwächer' },
          { label: 'Vergleichen', text: 'Zwei Zertifikate nebeneinander vergleichen' },
        ]
      },
      {
        title: 'Benutzerdefinierte Extra-EKUs (RFC 5280 §4.2.1.12)',
        content: 'Das Zertifikatsausstellungsformular und der Sign-CSR-Dialog bieten eine "Extra EKUs"-Mehrfachauswahl, mit der Sie Extended-Key-Usage-OIDs zusätzlich zu den Standardwerten des Zertifikatstyps hinzufügen können:',
        items: [
          { label: 'Katalog', text: '18 bekannte EKUs (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, Smartcard-Anmeldung, Dokumentsignierung, IPsec, Kerberos PKINIT usw.)' },
          { label: 'Freitext-OID', text: 'Jede wohlgeformte gepunktete OID, die ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$ entspricht' },
          { label: 'Limit', text: 'Bis zu 16 OIDs insgesamt pro Zertifikat' },
          { label: 'Zusammengeführt, nie ersetzt', text: 'Die Standard-EKUs des Zertifikatstyps (z. B. serverAuth) bleiben fest verankert — Extras kommen oben drauf' },
          { label: 'Abgelehnt', text: 'anyExtendedKeyUsage (2.5.29.37.0) ist explizit verboten' },
        ]
      },
      {
        title: 'Zertifikatsdateien auf Disk (v2.140)',
        items: [
          { label: 'Automatisch materialisiert', text: '.crt-/.key-Dateien werden bei jedem Erstellungspfad unter data/certs/ geschrieben (UI, CSR-Signierung, ACME, SCEP, Import)' },
          { label: 'CAs ebenfalls', text: 'CA-.crt-/.key-Dateien werden über denselben Mechanismus unter data/cas/ geschrieben' },
          { label: 'Sicherheitsnetz', text: 'Ein Datei-Regenerierungs-Scan beim Start baut fehlende Dateien aus der Datenbank wieder auf' },
          { label: 'Nicht blockierend', text: 'Schreibfehler werden geloggt, brechen aber nie die DB-Transaktion ab' },
        ]
      },
      {
        title: 'Bereitstellung (v2.215)',
        content: 'Dieses Zertifikat per SSH/SFTP auf entfernte Hosts übertragen — nur für Admins, Ziele werden unter Einstellungen › Bereitstellung verwaltet.',
        items: [
          { label: 'Ziel verknüpfen', text: 'Aus der Zertifikat-Detailansicht: ein Deploy-Ziel wählen und absolute Zielpfade für Zertifikat, privaten Schlüssel und/oder vollständige Kette festlegen (mindestens einen)' },
          { label: 'Derselbe Host', text: 'Für eine Bereitstellung auf dem UCM-Host selbst ein SFTP-Ziel unter 127.0.0.1 mit einem dedizierten SSH-Konto verwenden; der Sandbox-Dienst kann nicht außerhalb seines Datenverzeichnisses schreiben' },
          { label: 'Automatisch', text: 'Bei Ausstellung und Erneuerung werden die verknüpften Dateien erneut übertragen und der Reload-Befehl des Ziels ausgeführt — Zustellungen werden mit Wiederholungen in die Warteschlange gestellt' },
          { label: 'Dateien', text: 'Werden atomar an den exakt konfigurierten Pfaden geschrieben (übergeordnetes Verzeichnis muss existieren): Schlüssel 0600, Zertifikat/Kette 0644' },
          { label: 'Jetzt bereitstellen', text: 'Manuelle Übertragung aus der Detailansicht, mit Zustellstatus und letztem Fehler pro Ziel' },
        ]
      },

    ],
    tips: [
      'Markieren Sie ⭐ wichtige Zertifikate, um sie zu Ihrer Favoritenliste hinzuzufügen',
      'Verwenden Sie Filter, um Zertifikate schnell nach Status, CA oder Suchtext zu finden — Ihre Auswahl wird über Reloads hinweg gespeichert',
      'Beim Erneuern bleibt derselbe Datensatz erhalten (id, refid, Erstellungsdatum) — von UCM gehaltene Schlüssel werden neu generiert, per Protokoll ausgestellte Zertifikate (SCEP/EST/ACME) behalten ihren clientseitigen Schlüssel',
      'Brauchen Sie eine nicht-standardisierte EKU (Microsoft RDP, Smartcard-Anmeldung, Dokumentsignierung)? Fügen Sie sie über "Extra EKUs" hinzu, statt Templates zu bearbeiten',
    ],
    warnings: [
      'Widerruf ist grundsätzlich dauerhaft — außer bei „Zertifikat gesperrt", das aufgehoben werden kann (Sperre aufheben)',
      'Ein gültiges, nicht widerrufenes Zertifikat kann nicht gelöscht werden (409) — widerrufen Sie es zuerst, damit der Widerruf CRL/OCSP erreicht; Widerrufe überleben das Löschen',
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
- **Archiviert** — Durch eine Erneuerung oder erneute Registrierung ersetzt, die den alten Datensatz zur Historie aufbewahrt hat (SCEP, EST, WSTEP, ACME, OCSP-Responder)

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

Seit v2.214 wird das Zertifikat bei der Erneuerung **in place** aktualisiert:
- Gleicher Datensatz: **id, refid und Erstellungsdatum ändern sich nie** — Integrationen behalten ihre Referenzen
- Gleicher Betreff und gleiche SANs; neue Seriennummer und neue Gültigkeitsdauer
- Zertifikate, deren Schlüssel UCM hält, erhalten ein **neues Schlüsselpaar**; per Protokoll ausgestellte Zertifikate (SCEP/EST/ACME) werden mit ihrem vorhandenen öffentlichen Schlüssel erneut signiert
- Die **ersetzte Seriennummer bleibt auf der CRL veröffentlicht** (Grund \`superseded\`) und antwortet über OCSP mit \`revoked\`, bis das ursprüngliche Ablaufdatum des alten Zertifikats erreicht ist
- \`renewed_at\` / \`renewed_times\` protokollieren die Erneuerungshistorie
- Ein widerrufenes Zertifikat kann nicht erneuert werden (409) — stellen Sie stattdessen ein neues aus

**Löschen**: Ein gültiges, nicht widerrufenes Zertifikat kann nicht gelöscht werden (409) — widerrufen Sie es zuerst, damit Relying Parties die Änderung sehen. Widerrufe werden unabhängig vom Zertifikatsdatensatz gespeichert und überleben das Löschen.

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

- **Statusfilter** — Gültig, Ablaufend, Abgelaufen, Widerrufen, Verwaist, Archiviert
- **CA-Filter** — Zertifikate einer bestimmten CA anzeigen
- **Quellenfilter** — Nach der Art filtern, wie das Zertifikat in UCM gelangt ist (ausgestellt, importiert, ACME, SCEP usw.)
- **Vorlagenfilter** — Zertifikate finden, die **von der Vorlage abweichen**: aus einer Vorlage ausgestellt, aber mit bei der Anfrage explizit überschriebenem Schlüsseltyp, Gültigkeit oder Digest. Die abweichenden Felder werden in den Zertifikatdetails aufgelistet; der Datensatz ist ab der Ausstellung eingefroren
- **Textsuche** — Nach CN, Seriennummer oder SAN suchen
- **Sortierung** — Nach Name, Ablaufdatum, Erstellungsdatum, Status
## Konformitätsprüfung

Die Aktion **Prüfen** (Zertifikatdetails) prüft die Konformität mit X.509-Standards. Nur informativ.

- **RFC 5280** — IETF-X.509-Profil, immer relevant
- **CA/Browser Forum** — Baseline Requirements für öffentliche TLS-Zertifikate (Rauschen bei interner PKI zu erwarten)
- Schweregrade: fatal / error / warning / notice / info
- Engine: pkilint (+ zlint falls vorhanden) — optionale Serverabhängigkeit, sanfte Degradierung wenn nicht vorhanden

`
  }
}
