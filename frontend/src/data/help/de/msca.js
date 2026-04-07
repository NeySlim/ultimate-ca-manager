export default {
  helpContent: {
    title: 'Microsoft AD CS-Integration',
    subtitle: 'Zertifikate mit Microsoft-Zertifizierungsstelle signieren',
    overview: 'Verbinden Sie UCM mit Microsoft Active Directory Certificate Services (AD CS), um CSRs mit Ihrer Windows-PKI-Infrastruktur zu signieren. Unterstützt Zertifikat- (mTLS), Kerberos- und Basic-Authentifizierungsmethoden.',
    sections: [
      {
        title: 'Authentifizierungsmethoden',
        items: [
          { label: 'Client-Zertifikat (mTLS)', text: 'Am sichersten. Generieren Sie ein Client-Zertifikat auf Ihrer MS CA, exportieren Sie als PFX, laden Sie Zertifikat- und Schlüssel-PEM hoch.' },
          { label: 'Basic Auth', text: 'Benutzername/Passwort über HTTPS. Funktioniert ohne Domänenbeitritt. Aktivieren Sie Basic Auth in IIS certsrv.' },
          { label: 'Kerberos', text: 'Erfordert das Paket requests-kerberos und eine domänenverbundene Maschine oder konfigurierte Keytab.' },
        ]
      },
      {
        title: 'CSRs signieren',
        items: [
          { label: 'Template-Auswahl', text: 'Aus verfügbaren Zertifikatstemplates der MS CA auswählen' },
          { label: 'Auto-genehmigt', text: 'Templates mit Autoenroll geben das Zertifikat sofort zurück' },
          { label: 'Manager-Genehmigung', text: 'Einige Templates erfordern eine Manager-Genehmigung — UCM verfolgt die ausstehende Anfrage' },
          { label: 'Status-Abfrage', text: 'Status ausstehender Anfragen über das CSR-Detailpanel prüfen' },
        ]
      },
      {
        title: 'Enroll on Behalf Of (EOBO)',
        items: [
          { label: 'Übersicht', text: 'CSR im Namen eines anderen Benutzers mit Enrollment-Agent-Zertifikaten einreichen' },
          { label: 'Enrollee DN', text: 'Distinguished Name des Zielbenutzers (automatisch aus CSR-Betreff gefüllt)' },
          { label: 'Enrollee UPN', text: 'User Principal Name des Zielbenutzers (automatisch aus CSR-SAN-E-Mail gefüllt)' },
          { label: 'Voraussetzungen', text: 'CA-Template muss Registrierung im Namen anderer erlauben. UCM-Dienstkonto benötigt ein Enrollment-Agent-Zertifikat.' },
        ]
      },
    ],
    tips: [
      'Testen Sie zuerst die Verbindung, um die Authentifizierung zu überprüfen und verfügbare Templates zu ermitteln.',
      'Aktivieren Sie EOBO durch Anklicken des Kontrollkästchens im Signierungsdialog — Felder werden automatisch aus CSR-Daten gefüllt.',
      'Client-Zertifikat-Authentifizierung wird für die Produktion empfohlen — sie erfordert keinen Domänenbeitritt.',
    ],
    warnings: [
      'Kerberos erfordert, dass die Maschine der Domäne beigetreten ist oder eine Keytab konfiguriert ist — nicht verfügbar in Docker.',
      'EOBO erfordert ein auf dem AD CS-Server konfiguriertes Enrollment-Agent-Zertifikat.',
    ],
  },
  helpGuides: {
    title: 'Microsoft AD CS-Integration',
    content: `
## Übersicht

UCM integriert sich mit Microsoft Active Directory Certificate Services (AD CS), um CSRs mit Ihrer bestehenden Windows-PKI-Infrastruktur zu signieren. Dies verbindet Ihre interne CA mit dem Zertifikatslebenszyklus-Management von UCM.

## Verbindung einrichten

1. Gehen Sie zu **Einstellungen → Microsoft CA**
2. Klicken Sie auf **Verbindung hinzufügen**
3. Geben Sie den **Verbindungsnamen** und den **CA-Server-Hostnamen** ein
4. Geben Sie optional den **CA Common Name** ein (automatisch erkannt, wenn leer)
5. Wählen Sie die **Authentifizierungsmethode**
6. Geben Sie die Anmeldedaten für die gewählte Methode ein
7. Klicken Sie auf **Verbindung testen** zur Überprüfung
8. Legen Sie ein **Standard-Template** fest und klicken Sie auf **Speichern**

## Authentifizierungsmethoden

| Methode | Voraussetzungen | Geeignet für |
|---------|-----------------|--------------|
| **Client-Zertifikat (mTLS)** | Client-Zertifikat/Schlüssel-PEM von der CA | Produktion — kein Domänenbeitritt nötig |
| **Basic Auth** | Benutzername + Passwort, HTTPS | Einfache Setups — Basic Auth in IIS certsrv aktivieren |
| **Kerberos** | Domänenverbundene Maschine + Keytab | Enterprise-AD-Umgebungen |

### Client-Zertifikat-Einrichtung (empfohlen)

1. Erstellen Sie auf Ihrer Windows-CA ein Zertifikat für das UCM-Dienstkonto
2. Exportieren Sie als PFX, dann konvertieren Sie zu PEM:
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Fügen Sie den Zertifikats- und Schlüssel-PEM-Inhalt in das UCM-Verbindungsformular ein

## CSRs über Microsoft CA signieren

1. Navigieren Sie zu **CSRs → Ausstehend**
2. Wählen Sie einen CSR und klicken Sie auf **Signieren**
3. Wechseln Sie zum **Microsoft CA**-Tab
4. Wählen Sie die Verbindung und das Zertifikatstemplate
5. Klicken Sie auf **Signieren**

### Auto-genehmigte Templates
Das Zertifikat wird sofort zurückgegeben und in UCM importiert.

### Manager-Genehmigungs-Templates
UCM speichert die Anfrage als **Ausstehend** und verfolgt die MS CA-Anfrage-ID. Sobald die Genehmigung auf der Windows-CA erfolgt ist, prüfen Sie den Status über das CSR-Detailpanel, um das Zertifikat zu importieren.

## Enroll on Behalf Of (EOBO)

EOBO ermöglicht es einem Enrollment-Agenten, Zertifikate im Namen anderer Benutzer anzufordern. Dies ist in Enterprise-Umgebungen üblich, in denen ein PKI-Administrator Zertifikate für Endbenutzer verwaltet.

### Voraussetzungen

- Das UCM-Dienstkonto benötigt ein von der CA ausgestelltes **Enrollment-Agent-Zertifikat**
- Das Zertifikatstemplate muss die Berechtigung **„Im Namen anderer Benutzer registrieren"** aktiviert haben
- Die Sicherheitsregisterkarte des Templates muss dem Enrollment-Agenten das Registrierungsrecht gewähren

### EOBO in UCM verwenden

1. Wählen Sie im Signierungsdialog die Microsoft CA-Verbindung und das Template
2. Aktivieren Sie das Kontrollkästchen **Enroll on Behalf Of (EOBO)**
3. Die Felder werden automatisch aus dem CSR gefüllt:
   - **Enrollee DN** — aus dem CSR-Betreff (z.B. CN=Max Mustermann,OU=Benutzer,DC=corp,DC=local)
   - **Enrollee UPN** — aus der CSR-SAN-E-Mail (z.B. max.mustermann@corp.local)
4. Passen Sie die Werte bei Bedarf an
5. Klicken Sie auf **Signieren**

UCM übergibt diese als ADCS-Anforderungsattribute:
- EnrolleeObjectName:<DN> — identifiziert den Zielbenutzer in AD
- EnrolleePrincipalName:<UPN> — der Anmeldename des Benutzers

### EOBO vs direkte Registrierung

| Eigenschaft | Direkte Registrierung | EOBO |
|-------------|----------------------|------|
| Wer signiert | Benutzer selbst | Enrollment-Agent im Auftrag |
| Privater Schlüssel | Benutzermaschine | Kann auf UCM sein (CSR-Modell) |
| Template-Berechtigung | Standard-Registrierung | Erfordert Enrollment-Agent-Rechte |
| Anwendungsfall | Self-Service | Zentralisiertes PKI-Management |

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| Verbindungstest schlägt fehl | Hostname, Port 443 überprüfen und sicherstellen, dass certsrv erreichbar ist |
| Keine Templates gefunden | Prüfen, ob das UCM-Konto Registrierungsberechtigungen auf der CA hat |
| EOBO verweigert | Enrollment-Agent-Zertifikat und Template-Berechtigungen überprüfen |
| Anfrage bleibt ausstehend | Auf der Windows-CA-Konsole genehmigen, dann Status in UCM aktualisieren |

> 💡 Verwenden Sie den **Verbindung testen**-Button, um Authentifizierung und verfügbare Templates vor dem Signieren zu überprüfen.
`
  }
}
