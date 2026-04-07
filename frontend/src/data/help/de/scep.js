export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP ermöglicht es Netzwerkgeräten (Router, Switches, Firewalls) und MDM-Lösungen, automatisch Zertifikate anzufordern und zu erhalten. Geräte authentifizieren sich über ein Challenge-Passwort.',
    sections: [
      {
        title: 'Tabs',
        items: [
          { label: 'Anfragen', text: 'Ausstehende, genehmigte und abgelehnte SCEP-Registrierungsanfragen' },
          { label: 'Konfiguration', text: 'SCEP-Servereinstellungen: CA-Auswahl, CA-Kennung, Auto-Genehmigung' },
          { label: 'Challenge-Passwörter', text: 'Pro-CA-Challenge-Passwörter für die Geräteregistrierung verwalten' },
          { label: 'Information', text: 'SCEP-Endpunkt-URLs und Integrationsanweisungen' },
        ]
      },
      {
        title: 'Konfiguration',
        items: [
          { label: 'Signierende CA', text: 'Auswählen, welche CA SCEP-registrierte Zertifikate signiert' },
          { label: 'Auto-Genehmigung', text: 'Anfragen mit gültigem Challenge-Passwort automatisch genehmigen' },
          { label: 'Challenge-Passwort', text: 'Gemeinsames Geheimnis, das Geräte zur Authentifizierung der Registrierung verwenden' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie eindeutige Challenge-Passwörter pro CA für bessere Sicherheitsüberwachung',
      'Auto-Genehmigung ist praktisch, aber überprüfen Sie Anfragen in Hochsicherheitsumgebungen manuell',
      'SCEP-URL-Format: https://ihr-server:port/scep',
    ],
    warnings: [
      'Challenge-Passwörter werden in der SCEP-Anfrage übertragen — verwenden Sie HTTPS für Transportsicherheit',
    ],
  },
  helpGuides: {
    title: 'SCEP-Server',
    content: `
## Übersicht

Das Simple Certificate Enrollment Protocol (SCEP) ermöglicht es Netzwerkgeräten — Routern, Switches, Firewalls, MDM-verwalteten Endpunkten — automatisch Zertifikate anzufordern und zu erhalten.

## Tabs

### Anfragen
Alle SCEP-Registrierungsanfragen anzeigen:
- **Ausstehend** — Warten auf manuelle Genehmigung (wenn Auto-Genehmigung deaktiviert ist)
- **Genehmigt** — Erfolgreich ausgestellt
- **Abgelehnt** — Von einem Administrator abgelehnt

### Konfiguration
Den SCEP-Server konfigurieren:
- **Aktivieren/Deaktivieren** — Den SCEP-Dienst umschalten
- **Signierende CA** — Auswählen, welche CA SCEP-registrierte Zertifikate signiert
- **CA-Kennung** — Die Kennung, die Geräte verwenden, um die richtige CA zu finden
- **Auto-Genehmigung** — Anfragen mit gültigem Challenge-Passwort automatisch genehmigen

### Challenge-Passwörter
Pro-CA-Challenge-Passwörter verwalten. Geräte müssen ein gültiges Challenge-Passwort in ihrer Registrierungsanfrage zur Authentifizierung angeben.

- **Passwort anzeigen** — Das aktuelle Challenge für eine CA anzeigen
- **Regenerieren** — Ein neues Challenge-Passwort erstellen (macht das alte ungültig)

### Information
Zeigt die SCEP-Endpunkt-URL und Integrationsanweisungen an.

## SCEP-Registrierungsablauf

1. Gerät sendet eine **GetCACert**-Anfrage, um das CA-Zertifikat zu erhalten
2. Gerät generiert ein Schlüsselpaar und erstellt einen CSR
3. Gerät verpackt den CSR mit dem **Challenge-Passwort** und sendet eine **PKCSReq**
4. UCM validiert das Challenge-Passwort
5. Wenn Auto-Genehmigung aktiv ist, signiert UCM das Zertifikat und gibt es zurück
6. Wenn Auto-Genehmigung deaktiviert ist, prüft ein Admin die Anfrage und genehmigt/lehnt ab

## SCEP-URL

\`\`\`
https://ihr-server:8443/scep
\`\`\`

Geräte benötigen diese URL plus die CA-Kennung für die Registrierung.

## Anfragen genehmigen/ablehnen

Für ausstehende Anfragen (Auto-Genehmigung deaktiviert):
1. Prüfen Sie die Anfragedetails (Betreff, Schlüsseltyp, Challenge)
2. Klicken Sie auf **Genehmigen**, um das Zertifikat zu signieren und auszustellen
3. Oder klicken Sie auf **Ablehnen** mit einem Grund

> ⚠ Challenge-Passwörter werden in der SCEP-Anfrage übertragen. Verwenden Sie immer HTTPS für den SCEP-Endpunkt.

## Geräteintegration

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://ihr-server:8443/scep
  password <challenge-passwort>
\`\`\`

### Microsoft Intune / JAMF
Konfigurieren Sie das SCEP-Profil mit:
- Server-URL: \`https://ihr-server:8443/scep\`
- Challenge: das Passwort von UCM
`
  }
}
