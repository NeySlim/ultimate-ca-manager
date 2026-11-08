export default {
  helpContent: {
    title: 'Microsoft AD CS-Integration',
    subtitle: 'Zertifikate mit Microsoft-Zertifizierungsstelle signieren',
    overview: 'Verbinden Sie UCM mit Microsoft Active Directory Certificate Services (AD CS), um CSRs mit Ihrer Windows-PKI-Infrastruktur zu signieren und den vollständigen Zertifikatslebenszyklus zu verwalten. Unterstützt Zertifikat- (mTLS), Kerberos- und Basic-Authentifizierung sowie einen optionalen WinRM-Admin-Kanal für Widerruf, CRL, Inventar und die Verwaltung ausstehender Anfragen.',
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
          { label: 'Manager-Genehmigung', text: 'Einige Templates erfordern eine Manager-Genehmigung, UCM verfolgt die ausstehende Anfrage' },
          { label: 'Ausstehende Anfragen', text: 'Eine Anfrage, die die CA für ihren Manager zurückhält, bleibt in UCM Ausstehend, und die Seite bietet keine Statusprüfung: Sobald sie auf der CA ausgestellt ist, importieren Sie das Zertifikat, oder lassen Sie den Inventar-Sync über den WinRM-Admin-Kanal die UCM noch unbekannten Zertifikate importieren' },
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
      {
        title: 'Lebenszyklus: Erneuern & Widerrufen',
        items: [
          { label: 'Erneuern', text: 'Die Erneuerung eines von AD CS ausgestellten Zertifikats reicht dessen ursprünglichen CSR erneut bei derselben Verbindung und demselben Template ein, die ausstellende CA signiert, nicht UCM.' },
          { label: 'Widerrufen', text: 'Der Widerruf eines von AD CS ausgestellten Zertifikats gilt nur lokal in UCM, außer der WinRM-Admin-Kanal ist konfiguriert, dann wird er an die Windows-CA weitergegeben.' },
          { label: 'Ausstehende Erneuerung', text: 'Hält die CA die Erneuerung für eine Manager-Genehmigung zurück, verfolgt UCM sie wie jede andere ausstehende Anfrage.' },
        ]
      },
      {
        title: 'WinRM-Admin-Kanal (optional)',
        items: [
          { label: 'Zweck', text: 'Führt Verwaltungsoperationen auf der Windows-CA aus (Widerrufen, Widerruf aufheben, CRL veröffentlichen, Inventar, Genehmigen/Ablehnen) über PowerShell-Remoting + certutil, Dinge, die AD CS Web Enrollment nicht kann.' },
          { label: 'Transport', text: 'NTLM oder Kerberos über HTTP/HTTPS. Kerberos + HTTPS empfohlen; Kerberos verwendet die Keytab der Verbindung wieder.' },
          { label: 'Anmeldedaten', text: 'Verwendet standardmäßig die der Verbindung. mTLS-Verbindungen müssen ein dediziertes WinRM-Konto festlegen (Least-Privilege-Officer „Zertifikate ausstellen und verwalten").' },
          { label: 'Voraussetzung', text: 'WinRM auf der CA aktiviert und das optionale Paket pywinrm installiert. Verwaltungsoperationen erfordern admin:system; die Weitergabe eines Widerrufs oder einer Sperrfreigabe an die CA folgt dem write:certificates des Zertifikats.' },
        ]
      },
      {
        title: 'CRL-Widerrufs-Synchronisierung',
        items: [
          { label: 'Einweg-Sync', text: 'Ruft periodisch die CRL der CA ab und markiert auf der CA widerrufene Zertifikate auch in UCM als widerrufen. Hebt niemals einen Widerruf auf.' },
          { label: 'CRL-Quelle', text: 'Eine explizite CRL-URL oder automatisch erkannt aus dem CRL Distribution Point ausgestellter Zertifikate.' },
          { label: 'Verifiziert', text: 'Die CRL-Signatur wird gegen das CA-Zertifikat geprüft, bevor irgendetwas angewendet wird.' },
        ]
      },
      {
        title: 'CA-Inventar & Kontrollpanel',
        items: [
          { label: 'Inventar-Sync', text: 'Importiert direkt auf der CA ausgestellte Zertifikate, die UCM noch nicht kennt (inkrementell nach Anfrage-ID); der Abgleich ist über die API verfügbar.' },
          { label: 'Ausstehende Anfragen', text: 'Anfragen, die auf CA-Manager-Genehmigung warten, auflisten, genehmigen (erneut einreichen + Auto-Import) oder ablehnen.' },
          { label: 'CA-Zustand', text: 'CA-Dienststatus, Ablauf des CA-Zertifikats, nächste CRL-Aktualisierung und Anzahl ausstehender Anfragen auf einen Blick.' },
        ]
      },
    ],
    tips: [
      'Testen Sie zuerst die Verbindung, um die Authentifizierung zu überprüfen und verfügbare Templates zu ermitteln.',
      'Aktivieren Sie EOBO durch Anklicken des Kontrollkästchens im Signierungsdialog. Felder werden automatisch aus CSR-Daten gefüllt.',
      'Client-Zertifikat-Authentifizierung wird für die Produktion empfohlen: sie erfordert keinen Domänenbeitritt.',
      'Aktivieren Sie den WinRM-Admin-Kanal, um Widerrufe an die CA weiterzugeben und ausstehende Anfragen aus UCM heraus zu verwalten.',
    ],
    warnings: [
      'Kerberos erfordert, dass die Maschine der Domäne beigetreten ist oder eine Keytab konfiguriert ist: nicht verfügbar in Docker.',
      'EOBO erfordert ein auf dem AD CS-Server konfiguriertes Enrollment-Agent-Zertifikat.',
      'Ohne den WinRM-Admin-Kanal markiert der Widerruf eines AD CS-Zertifikats es nur in UCM als widerrufen: die Windows-CA wird nicht benachrichtigt.',
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
4. Geben Sie optional den **CA Common Name** ein (der Server-Hostname wird verwendet, wenn leer)
5. Wählen Sie die **Authentifizierungsmethode**
6. Geben Sie die Anmeldedaten für die gewählte Methode ein
7. Klicken Sie auf **Verbindung testen** zur Überprüfung
8. Legen Sie ein **Standard-Template** fest und klicken Sie auf **Speichern**

## Authentifizierungsmethoden

| Methode | Voraussetzungen | Geeignet für |
|---------|-----------------|--------------|
| **Client-Zertifikat (mTLS)** | Client-Zertifikat/Schlüssel-PEM von der CA | Produktion: kein Domänenbeitritt nötig |
| **Basic Auth** | Benutzername + Passwort, HTTPS | Einfache Setups. Basic Auth in IIS certsrv aktivieren |
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
UCM speichert die Anfrage als **Ausstehend** und verfolgt die MS CA-Anfrage-ID. Die Seite bietet dafür keine Statusprüfung: Sobald es auf der Windows-CA ausgestellt ist, importieren Sie das Zertifikat, oder lassen Sie den **Inventar-Sync** über den WinRM-Admin-Kanal die UCM noch unbekannten Zertifikate importieren.

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
   - **Enrollee DN**: aus dem CSR-Betreff (z.B. CN=Max Mustermann,OU=Benutzer,DC=corp,DC=local)
   - **Enrollee UPN**: aus der CSR-SAN-E-Mail (z.B. max.mustermann@corp.local)
4. Passen Sie die Werte bei Bedarf an
5. Klicken Sie auf **Signieren**

UCM übergibt diese als ADCS-Anforderungsattribute:
- EnrolleeObjectName:<DN>: identifiziert den Zielbenutzer in AD
- EnrolleePrincipalName:<UPN>: der Anmeldename des Benutzers

### EOBO vs direkte Registrierung

| Eigenschaft | Direkte Registrierung | EOBO |
|-------------|----------------------|------|
| Wer signiert | Benutzer selbst | Enrollment-Agent im Auftrag |
| Privater Schlüssel | Benutzermaschine | Kann auf UCM sein (CSR-Modell) |
| Template-Berechtigung | Standard-Registrierung | Erfordert Enrollment-Agent-Rechte |
| Anwendungsfall | Self-Service | Zentralisiertes PKI-Management |

## Zertifikatslebenszyklus

### Ein AD CS-Zertifikat erneuern
Die Erneuerung signiert **nicht** lokal neu (der Ausstellungsschlüssel liegt auf der Windows-CA). UCM reicht den ursprünglichen CSR des Zertifikats: gleicher Schlüssel, gleicher Betreff, gleiche SANs, erneut bei der Verbindung und dem Template ein, die es ausgestellt haben, und aktualisiert das Zertifikat an Ort und Stelle. Hält die CA die Erneuerung für eine Manager-Genehmigung zurück, wird sie als ausstehende Anfrage verfolgt.

### Ein AD CS-Zertifikat widerrufen
AD CS Web Enrollment hat keinen Widerrufs-Endpunkt. Der Widerruf eines von AD CS ausgestellten Zertifikats:
- **Ohne den WinRM-Admin-Kanal**: markiert es nur in UCM als widerrufen; die Windows-CA wird nicht benachrichtigt. Widerrufen Sie es auch auf der CA.
- **Mit dem WinRM-Admin-Kanal**: UCM gibt den Widerruf an die Windows-CA weiter (certutil -revoke + CRL-Veröffentlichung). Das Aufheben eines certificateHold gibt auch die Widerrufsaufhebung weiter.

## WinRM-Admin-Kanal (optional)

Der Admin-Kanal ermöglicht UCM Verwaltungsoperationen auf der Windows-CA, die Web Enrollment nicht kann: Widerrufen/Widerruf aufheben, CRL veröffentlichen, Inventar sowie Genehmigen/Ablehnen ausstehender Anfragen. Er verwendet PowerShell-Remoting + certutil.

### Voraussetzungen
- **WinRM aktiviert** auf der CA (Enable-PSRemoting; HTTPS-Listener auf 5986 empfohlen)
- Das optionale Paket **pywinrm** in UCM installiert (pip install pywinrm)
- Ein Konto mit der Berechtigung, **Zertifikate auf der CA zu verwalten** („Issue and Manage Certificates")

### Konfiguration
1. Bearbeiten Sie die Verbindung und aktivieren Sie den **WinRM-Admin-Kanal**
2. Legen Sie Host (standardmäßig der Verbindungsserver), Port und Transport fest
3. **Transport**: Kerberos (empfohlen, verwendet die Verbindungs-Keytab wieder) oder NTLM, über HTTP oder HTTPS
4. **Anmeldedaten**: leer lassen, um die der Verbindung wiederzuverwenden (Basic/Kerberos). mTLS-Verbindungen haben keine wiederverwendbaren WinRM-Anmeldedaten, legen Sie ein dediziertes Konto fest
5. Klicken Sie auf **Admin-Kanal testen**

| Enrollment-Auth-Modus | Anmeldedaten für WinRM wiederverwendbar? |
|-----------------------|-------------------------------------------|
| Kerberos (Keytab) | Ja: gleiches Principal/Keytab |
| Basic (Benutzer/Passwort) | Ja. Passwort für NTLM/Kerberos |
| Zertifikat (mTLS) | Nein: dediziertes WinRM-Konto festlegen |

## CRL-Widerrufs-Synchronisierung

Aktivieren Sie **Widerrufe aus der CRL der CA synchronisieren** auf der Verbindung, damit UCM periodisch die CRL der CA abruft und auf der CA widerrufene Zertifikate auch in UCM als widerrufen markiert. Dies ist strikt einseitig (CA zu UCM) und hebt niemals den Widerruf eines in UCM widerrufenen Zertifikats auf. Die CRL-URL stammt aus der Verbindung oder wird automatisch aus dem CRL Distribution Point ausgestellter Zertifikate erkannt; ihre Signatur wird gegen das CA-Zertifikat geprüft, bevor irgendetwas angewendet wird. Läuft stündlich, plus eine Aktion **CRL jetzt synchronisieren**.

## CA-Inventar-Synchronisierung

Aktivieren Sie **Direkt auf der CA ausgestellte Zertifikate importieren**, um außerhalb von UCM ausgestellte Zertifikate (native Tools, Autoenrollment oder aus der Zeit vor UCM) in den UCM-Speicher zu holen, damit UCM den gesamten Lebenszyklus verfolgt. Die CA-Datenbank wird mit certutil -view gelesen, UCM unbekannte Zertifikate werden importiert (dedupliziert nach Seriennummer), inkrementell nach Anfrage-ID (mit Option für vollständigen Rescan). Eine **Abgleich**-Ansicht listet Zertifikate, die auf der CA, aber nicht in UCM vorhanden sind, und umgekehrt. Läuft alle 6 Stunden, plus eine Aktion **Jetzt von der CA importieren**. Erfordert den WinRM-Admin-Kanal.

## CA-Kontrollpanel

Das Kontrollpanel (von der Verbindung aus geöffnet, erfordert den Admin-Kanal) verwaltet Anfragen, die auf CA-Manager-Genehmigung warten, und zeigt den CA-Zustand:
- **Ausstehende Anfragen**: auflisten, **Genehmigen** (certutil -resubmit; das ausgestellte Zertifikat wird automatisch importiert) oder **Ablehnen** (certutil -deny)
- **Zustand**: CA-Dienststatus, Ablauf des CA-Zertifikats, nächste CRL-Aktualisierung und Anzahl ausstehender Anfragen

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| Verbindungstest schlägt fehl | Hostname, Port 443 überprüfen und sicherstellen, dass certsrv erreichbar ist |
| Keine Templates gefunden | Prüfen, ob das UCM-Konto Registrierungsberechtigungen auf der CA hat |
| EOBO verweigert | Enrollment-Agent-Zertifikat und Template-Berechtigungen überprüfen |
| Anfrage bleibt ausstehend | Über das CA-Kontrollpanel genehmigen, oder auf der Windows-CA-Konsole und dann Status in UCM aktualisieren |
| Admin-Kanal-Test schlägt fehl | Prüfen, ob WinRM auf der CA aktiviert ist, Port/Transport stimmen und pywinrm installiert ist |
| Widerruf nicht auf der CA | WinRM-Admin-Kanal aktivieren: ohne ihn ist der Widerruf lokal auf UCM beschränkt |
| Ausstehend nicht erkannt (nicht-englische CA) | Behoben in v2.192. UCM erkennt jetzt lokalisierte AD CS-Ausstehend-Seiten |

> 💡 Verwenden Sie den **Verbindung testen**-Button, um Authentifizierung und verfügbare Templates vor dem Signieren zu überprüfen. Aktivieren Sie den **WinRM-Admin-Kanal**, um Widerruf, CRLs, Inventar und ausstehende Anfragen direkt aus UCM zu verwalten.
`
  }
}
