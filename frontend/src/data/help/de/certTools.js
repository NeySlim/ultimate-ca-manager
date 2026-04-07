export default {
  helpContent: {
    title: 'Zertifikats-Tools',
    subtitle: 'Zertifikate dekodieren, konvertieren und verifizieren',
    overview: 'Eine Sammlung von Werkzeugen für die Arbeit mit Zertifikaten, CSRs und Schlüsseln. Dekodieren Sie Zertifikate, um ihren Inhalt zu prüfen, konvertieren Sie zwischen Formaten, überprüfen Sie Remote-SSL-Endpunkte und verifizieren Sie Schlüsselübereinstimmungen.',
    sections: [
      {
        title: 'Verfügbare Werkzeuge',
        items: [
          { label: 'SSL-Checker', text: 'Verbindung zu einem Remote-Host herstellen und dessen SSL/TLS-Zertifikatskette prüfen' },
          { label: 'CSR-Decoder', text: 'Einen CSR im PEM-Format einfügen, um Betreff, SANs und Schlüsselinformationen anzuzeigen' },
          { label: 'Zertifikats-Decoder', text: 'Ein Zertifikat im PEM-Format einfügen, um alle Felder zu prüfen' },
          { label: 'Schlüsselabgleich', text: 'Überprüfen, ob Zertifikat, CSR und privater Schlüssel zusammengehören' },
          { label: 'Konverter', text: 'Zwischen PEM, DER, PKCS#12 und PKCS#7 konvertieren' },
        ]
      },
      {
        title: 'Konverter-Details',
        items: [
          'PEM ↔ DER-Konvertierung',
          'PEM → PKCS#12 mit Passwort und vollständiger Kette',
          'PKCS#12 → PEM-Extraktion',
          'PEM → PKCS#7 (P7B)-Kettenbündelung',
        ]
      },
    ],
    tips: [
      'Der SSL-Checker unterstützt benutzerdefinierte Ports — verwenden Sie ihn, um jeden TLS-Dienst zu prüfen',
      'Der Schlüsselabgleich vergleicht Modulus-Hashes, um übereinstimmende Paare zu verifizieren',
      'Der Konverter bewahrt die vollständige Zertifikatskette beim Erstellen von PKCS#12',
    ],
  },
  helpGuides: {
    title: 'Zertifikats-Tools',
    content: `
## Übersicht

Ein Werkzeugkasten zum Prüfen, Konvertieren und Verifizieren von Zertifikaten, ohne UCM zu verlassen.

## SSL-Checker

SSL/TLS-Zertifikat eines Remote-Servers prüfen:

1. Geben Sie den **Hostnamen** ein (z.B. \`google.com\`)
2. Ändern Sie optional den **Port** (Standard: 443)
3. Klicken Sie auf **Prüfen**

Die Ergebnisse umfassen:
- Zertifikatsbetreff und Aussteller
- Gültigkeitsdaten
- SANs (Subject Alternative Names)
- Schlüsseltyp und -größe
- Vollständige Zertifikatskette
- TLS-Protokollversion

## CSR-Decoder

CSR-Inhalte analysieren und anzeigen:

1. Fügen Sie einen CSR im PEM-Format ein
2. Klicken Sie auf **Dekodieren**

Zeigt: Betreff, SANs, Schlüsselalgorithmus, Schlüsselgröße, Signaturalgorithmus.

## Zertifikats-Decoder

Zertifikatsdetails analysieren und anzeigen:

1. Fügen Sie ein Zertifikat im PEM-Format ein
2. Klicken Sie auf **Dekodieren**

Zeigt: Betreff, Aussteller, SANs, Gültigkeit, Seriennummer, Key Usage, Erweiterungen, Fingerabdrücke.

## Schlüsselabgleich

Überprüfen, ob Zertifikat, CSR und privater Schlüssel zusammengehören:

1. Fügen Sie das **Zertifikat**-PEM ein
2. Fügen Sie den **privaten Schlüssel**-PEM ein (optional verschlüsselt — Passwort angeben)
3. Fügen Sie optional einen **CSR**-PEM ein
4. Klicken Sie auf **Abgleichen**

UCM vergleicht die Modulus- (RSA) oder Public-Key-Hashes (EC). Eine Übereinstimmung bestätigt ein gültiges Paar.

## Konverter

Zwischen Zertifikats- und Schlüsselformaten konvertieren:

### PEM → DER
Konvertiert ein Base64-kodiertes PEM in das binäre DER-Format.

### PEM → PKCS#12
Erstellt eine passwortgeschützte P12/PFX-Datei aus:
- Zertifikat-PEM
- Privater-Schlüssel-PEM
- Optionale Kettenzertifikate
- Passwort für die P12-Datei

### PKCS#12 → PEM
Extrahiert Zertifikat, Schlüssel und Kette aus einer P12-Datei:
- P12-Datei hochladen
- Passwort eingeben
- Extrahierte PEM-Komponenten herunterladen

### PEM → PKCS#7
Bündelt mehrere Zertifikate in einer einzelnen P7B-Datei (ohne Schlüssel).

> 💡 Der Konverter bewahrt die vollständige Zertifikatskette beim Erstellen von PKCS#12-Dateien.
`
  }
}
