export default {
  helpContent: {
    title: 'Single Sign-On',
    subtitle: 'SAML-, OAuth2- und LDAP-Integration',
    overview: 'Konfigurieren Sie Single Sign-On, damit Benutzer sich über den Identitätsanbieter ihrer Organisation authentifizieren können. Unterstützt SAML 2.0, OAuth2/OIDC und LDAP-Protokolle.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Identitätsanbieter', text: 'IDP-Metadaten-URL konfigurieren oder XML hochladen' },
          { label: 'SP-Metadaten-URL', text: 'Geben Sie diese URL Ihrem IDP zur automatischen Konfiguration von UCM als Service Provider' },
          { label: 'SP-Zertifikat', text: 'UCM-HTTPS-Zertifikat in Metadaten enthalten — muss vom IDP vertraut werden, sonst werden die Metadaten abgelehnt' },
          { label: 'Entity ID', text: 'UCM Service Provider Entity-Kennung' },
          { label: 'ACS-URL', text: 'Assertion Consumer Service Callback-URL' },
          { label: 'Attributzuordnung', text: 'IDP-Attribute UCM-Benutzerfeldern zuordnen' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'Autorisierungs-URL', text: 'OAuth2-Autorisierungsendpunkt' },
          { label: 'Token-URL', text: 'OAuth2-Token-Endpunkt' },
          { label: 'Client-ID/Geheimnis', text: 'OAuth2-Client-Anmeldedaten von Ihrem IDP' },
          { label: 'Scopes', text: 'Anzufordernde OAuth2-Scopes (openid, profile, email)' },
          { label: 'Benutzer automatisch erstellen', text: 'UCM-Konten bei der ersten SSO-Anmeldung automatisch erstellen' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Server', text: 'LDAP-Server-Hostname und Port (389 oder 636 für SSL)' },
          { label: 'Bind-DN', text: 'Distinguished Name für LDAP-Bind-Authentifizierung' },
          { label: 'Basis-DN', text: 'Suchbasis für Benutzersuchen' },
          { label: 'Benutzerfilter', text: 'LDAP-Filter zum Abgleich von Benutzern (z.B. (uid={username}))' },
          { label: 'Attributzuordnung', text: 'LDAP-Attribute Benutzername, E-Mail, vollständigem Namen zuordnen' },
        ]
      },
    ],
    tips: [
      'Testen Sie SSO zuerst mit einem Nicht-Admin-Konto, um Aussperrungen zu vermeiden',
      'Halten Sie die lokale Admin-Anmeldung als Fallback bereit',
      'Ordnen Sie das IDP-E-Mail-Attribut zu, um eine eindeutige Benutzeridentifikation sicherzustellen',
      'Verwenden Sie die SP-Metadaten-URL zur automatischen Konfiguration Ihres IDP (SAML)',
      'Das UCM-HTTPS-Zertifikat muss vom IDP vertraut werden, damit SAML-Metadaten akzeptiert werden',
    ],
    warnings: [
      'Falsch konfiguriertes SSO kann alle Benutzer aussperren — behalten Sie immer einen lokalen Admin',
    ],
  },
  helpGuides: {
    title: 'Single Sign-On',
    content: `
## Übersicht

SSO ermöglicht Benutzern die Authentifizierung über den Identitätsanbieter (IDP) ihrer Organisation, sodass separate UCM-Anmeldedaten nicht mehr erforderlich sind. UCM unterstützt **SAML 2.0**, **OAuth2/OIDC** und **LDAP**.

## SAML 2.0

### SP-Metadaten-URL

UCM stellt eine **Service Provider (SP) Metadaten-URL** bereit, die Sie Ihrem IDP zur automatischen Konfiguration geben können:

\`\`\`
https://ihr-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

Diese URL gibt ein SAML 2.0-konformes XML-Dokument zurück mit:
- **Entity ID** — UCMs Service-Provider-Kennung
- **ACS-URL** — Assertion Consumer Service-Endpunkt (HTTP-POST)
- **SLO-URL** — Single Logout Service-Endpunkt
- **Signaturzertifikat** — UCMs HTTPS-Zertifikat zur Signaturverifizierung
- **NameID-Format** — Angefordertes Namenskennung-Format

Kopieren Sie diese URL in die „Service Provider hinzufügen"- oder „SAML-Anwendung"-Konfiguration Ihres IDP.

> ⚠️ **Wichtig:** Das HTTPS-Zertifikat von UCM muss **vom IDP vertraut werden**. Wenn der IDP das Zertifikat nicht validieren kann (z.B. selbstsigniert oder von einer privaten CA ausgestellt), werden die Metadaten als ungültig abgelehnt. Importieren Sie das CA-Zertifikat von UCM in den Vertrauensspeicher des IDP oder verwenden Sie ein von einer öffentlich vertrauenswürdigen CA signiertes Zertifikat.

### Konfiguration
1. Erhalten Sie die IDP-Metadaten-URL oder XML-Datei von Ihrem Identitätsanbieter
2. Gehen Sie in UCM zu **Einstellungen → SSO**
3. Klicken Sie auf **Anbieter hinzufügen** → SAML
4. Geben Sie die **IDP-Metadaten-URL** ein — UCM füllt automatisch Entity ID, SSO/SLO-URLs und Zertifikat
5. Oder fügen Sie das IDP-Metadaten-XML direkt ein
6. Konfigurieren Sie die **Attributzuordnung** (Benutzername, E-Mail, Gruppen)
7. Klicken Sie auf **Speichern** und **Aktivieren**

### Attributzuordnung
Ordnen Sie IDP-SAML-Attribute UCM-Benutzerfeldern zu:
- \`username\` → UCM-Benutzername (erforderlich)
- \`email\` → UCM-E-Mail (erforderlich)
- \`groups\` → UCM-Gruppenmitgliedschaft (optional)

## OAuth2 / OIDC

### Konfiguration
1. Registrieren Sie UCM als Client bei Ihrem OAuth2/OIDC-Anbieter
2. Setzen Sie die **Redirect-URI** auf: \`https://ihr-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Kopieren Sie die **Client-ID** und das **Client-Geheimnis**
4. Gehen Sie in UCM zu **Einstellungen → SSO**
5. Klicken Sie auf **Anbieter hinzufügen** → OAuth2
6. Geben Sie die **Autorisierungs-URL** und **Token-URL** ein
7. Geben Sie die **Benutzerinfo-URL** ein (zum Abrufen von Benutzerattributen nach der Anmeldung)
8. Geben Sie Client-ID und Geheimnis ein
9. Konfigurieren Sie Scopes (openid, profile, email)
10. Klicken Sie auf **Speichern** und **Aktivieren**

### Benutzer automatisch erstellen
Wenn aktiviert, wird bei der ersten SSO-Anmeldung automatisch ein neues UCM-Benutzerkonto erstellt, wobei die vom IDP bereitgestellten Attribute verwendet werden. Die Standardrolle wird zugewiesen.

## LDAP

### Konfiguration
1. Gehen Sie in UCM zu **Einstellungen → SSO**
2. Klicken Sie auf **Anbieter hinzufügen** → LDAP
3. Geben Sie den **LDAP-Server**-Hostnamen und **Port** ein (389 für LDAP, 636 für LDAPS)
4. Aktivieren Sie **SSL verwenden** für verschlüsselte Verbindungen
5. Geben Sie **Bind-DN** und **Bind-Passwort** ein (Dienstkonto-Anmeldedaten)
6. Geben Sie den **Basis-DN** ein (Suchbasis für Benutzersuchen)
7. Konfigurieren Sie den **Benutzerfilter** (z.B. \`(uid={username})\` oder \`(sAMAccountName={username})\` für AD)
8. Ordnen Sie LDAP-Attribute zu: **Benutzername**, **E-Mail**, **vollständiger Name**
9. Klicken Sie auf **Verbindung testen** zur Überprüfung, dann **Speichern** und **Aktivieren**

### Active Directory
Für Microsoft Active Directory verwenden Sie:
- Port: **389** (oder 636 mit SSL)
- Benutzerfilter: \`(sAMAccountName={username})\`
- Benutzername-Attr.: \`sAMAccountName\`
- E-Mail-Attr.: \`mail\`
- Vollständiger-Name-Attr.: \`displayName\`

## Anmeldeablauf
1. Benutzer klickt auf **Mit SSO anmelden** auf der UCM-Anmeldeseite (oder gibt LDAP-Anmeldedaten ein)
2. Für SAML/OAuth2: Benutzer wird zum IDP weitergeleitet, authentifiziert sich, dann zurückgeleitet
3. Für LDAP: Anmeldedaten werden direkt gegen den LDAP-Server verifiziert
4. UCM erstellt oder aktualisiert das Benutzerkonto
5. Benutzer ist angemeldet

> ⚠ Behalten Sie immer mindestens ein lokales Admin-Konto als Fallback, falls eine SSO-Fehlkonfiguration alle aussperrt.

> 💡 Testen Sie SSO zuerst mit einem Nicht-Admin-Konto, bevor Sie es zur primären Authentifizierungsmethode machen.

> 💡 Verwenden Sie den **Verbindung testen**-Button, um Ihre Konfiguration vor dem Aktivieren eines Anbieters zu überprüfen.
`
  }
}
