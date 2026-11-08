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
          { label: 'SP-Zertifikat', text: 'UCM-HTTPS-Zertifikat in Metadaten enthalten, muss vom IDP vertraut werden, sonst werden die Metadaten abgelehnt' },
          { label: 'Entity ID', text: 'UCM Service Provider Entity-Kennung' },
          { label: 'ACS-URL', text: 'Assertion Consumer Service Callback-URL' },
          { label: 'Attributzuordnung', text: 'Linke Spalte: der vom IdP gesendete Attributname. Rechte Spalte: das UCM-Feld, das damit befüllt wird (username, email, fullname oder groups). Beispiel: user.userprincipalname → username.' },
          { label: 'Gruppen für die Rollenzuordnung', text: 'Gelesen aus den Attributen, die groups zugeordnet sind, sonst aus groups und den Gruppen- und Rollen-Claims von Microsoft Entra ID / AD FS. Sendet Entra ID groups.link statt der Gruppen (Benutzer in mehr als 150 Gruppen), wird eine Warnung protokolliert und die Standardrolle gilt: nur die der Anwendung zugewiesenen Gruppen oder App-Rollen ausgeben.' },
          { label: 'IdP-initiierte Anmeldung', text: 'Akzeptiert Anmeldungen aus dem IdP-Portal, geprüft wie jede andere Antwort. Aktiv für Provider, die vor 2.243 angelegt wurden, aus für neue: nur aktivieren, wenn Benutzer im IdP-Portal starten.' },
          { label: 'NameID-Format', text: 'Nicht angegeben (IdP-Standard), Persistent, E-Mail-Adresse oder Transient: wird in jeder Anmeldeanfrage gesendet und in den SP-Metadaten veröffentlicht. Persistent liefert eine stabile Kennung; eine transiente NameID dient nie zur Wiedererkennung des Kontos.' },
          { label: 'Single Logout', text: 'Ein vom IdP signiertes LogoutRequest, das an die SLO-URL der SP-Metadaten gesendet wird (HTTP-Redirect), schließt die UCM-Sitzung dieser NameID in diesem Browser, es sei denn, seine SessionIndex nennt eine andere Sitzung. Eine LogoutResponse geht an die SLO-URL des IdP zurück, mit dem SP-Schlüssel signiert (unsigniert, wenn das SP-Zertifikat nicht RSA ist, was ein strenger IdP ablehnt); ohne SLO-URL des IdP kehrt der Browser zur Anmeldeseite zurück. Eine unsignierte, gefälschte, veraltete oder wiederholte Anfrage oder eine ohne Destination wird abgelehnt.' },
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
        title: 'Rollen-Provisionierung (#81)',
        items: [
          { label: 'Identitätszuordnung', text: 'Eine Anmeldung öffnet das Konto, das an die IdP-Kennung gebunden ist (OIDC sub, persistente SAML-NameID, LDAP entryUUID oder objectGUID). Ein Benutzername oder eine E-Mail passt nur zu einem noch nicht gebundenen Konto desselben Providers; ein lokales Konto oder eines, das an eine andere Identität gebunden ist, wird bei der Anmeldung abgelehnt. Um ein lokales Konto zusammenzuführen, verwenden Sie zuerst In Benutzer die Aktion Mit SSO verknüpfen: Die nächste Anmeldung über diesen Provider bindet die Kennung.' },
          { label: 'Standardrolle', text: 'Wird Konten gegeben, die bei der ersten SSO-Anmeldung angelegt werden, wenn der Provider keine Rollenzuordnungsregel hat, und als Basisrolle eines neuen Kontos, dessen passende Regel nur eine benutzerdefinierte Rolle vergibt (Viewer bei Keine). Keine: Ohne Regel meldet sich niemand an. Später in UCM vorgenommene Rollenänderungen bleiben erhalten.' },
          { label: 'Rollenzuordnung', text: 'Externe Gruppen (Azure AD, Okta, LDAP) → UCM-Rollen (admin / operator / auditor / viewer) oder benutzerdefinierte Rollen zuordnen. Mit mindestens einer Regel wird ein Benutzer, auf den keine Regel passt, bei jeder SSO-Anmeldung (OIDC, SAML, LDAP) abgelehnt, neues Konto oder bestehendes; eine Anmeldung per Passkey oder Zertifikat wird nicht geprüft. Wird bei der Benutzererstellung verwendet und bei jedem Login, wenn die Rollensynchronisierung aktiviert ist. Wenn mehrere Gruppen passen, gewinnt die Rolle mit den höchsten Rechten (admin > operator > auditor > viewer): die Reihenfolge der Einträge spielt keine Rolle (#221). Jede Gruppe kann zusätzlich eine benutzerdefinierte Rolle nennen (aus den vorhandenen benutzerdefinierten Rollen gewählt): Sie wird zur Basisrolle hinzugefügt oder allein verwendet. Liefern mehrere passende Gruppen eine benutzerdefinierte Rolle, gewinnt die erste in der Liste. Bei aktiver Rollensynchronisierung wird eine per SSO gesetzte benutzerdefinierte Rolle entfernt, wenn keine Gruppe eine vergibt; eine in UCM von Hand zugewiesene wird nie angetastet. Systemrollen können nicht als benutzerdefinierte Rolle verwendet werden.' },
          { label: 'Rolle bei jedem Login synchronisieren', text: 'AUS (Standard): SSO überschreibt nie von UCM verwaltete Rollen. EIN: Die Rolle wird bei jedem Login aus role_mapping neu synchronisiert; eine passende Regel ohne Basisrolle behält die gespeicherte (default_role wird nie erneut angewendet).' },
          { label: '2FA erzwingen', text: 'Benutzer dieses Providers müssen einen zweiten Faktor einrichten. LDAP-Anmeldungen verlangen einen eingerichteten TOTP-Code oder Sicherheitsschlüssel, wie lokale Anmeldungen, mit oder ohne diese Option; OIDC- und SAML-Anmeldungen verlangen nur die Einrichtung und verlassen sich für MFA auf den Identitätsanbieter.' },
          { label: 'Benutzer automatisch aktualisieren', text: 'Aktualisiert E-Mail und vollständigen Namen bei jedem Login. Verändert die Rolle NICHT.' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Server', text: 'LDAP-Server-Hostname und Port (389 oder 636 für SSL)' },
          { label: 'StartTLS', text: 'Auf einem Klartext-LDAP-Port wird die Verbindung vor jedem Bind auf TLS angehoben, mit derselben Zertifikatsprüfung wie bei LDAPS. Für einen neuen Provider ohne SSL/TLS standardmäßig an. Ohne SSL/TLS oder StartTLS laufen Bind- und Benutzerpasswörter im Klartext durchs Netz.' },
          { label: 'Bind-DN', text: 'Distinguished Name für LDAP-Bind-Authentifizierung' },
          { label: 'Basis-DN', text: 'Suchbasis für Benutzersuchen' },
          { label: 'Benutzerfilter', text: 'LDAP-Filter zum Abgleich von Benutzern (z.B. (uid={username}))' },
          { label: 'Attributzuordnung', text: 'LDAP-Attribute dem Benutzernamen, der E-Mail und dem vollständigen Namen zuordnen' },
          { label: 'Eindeutiges ID-Attribut', text: 'Unveränderliche Kennung, die das Konto erkennt (entryUUID, objectGUID). Ein über seinen DN gebundenes Konto wechselt bei der nächsten Anmeldung zu dieser Kennung; der Wechsel von einem ID-Attribut zu einem anderen lehnt jeden gebundenen Benutzer ab, bis Verknüpfung lösen und dann Mit SSO verknüpfen erfolgt.' },
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
      'Falsch konfiguriertes SSO kann alle Benutzer aussperren: behalten Sie immer einen lokalen Admin',
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
- **Entity ID**: UCMs Service-Provider-Kennung
- **ACS-URL**: Assertion Consumer Service-Endpunkt (HTTP-POST)
- **SLO-URL**: IdP-Endpunkt, der die LogoutResponse per HTTP-Redirect entgegennimmt; der Metadatenimport behält die ResponseLocation des HTTP-Redirect-Single-Logout-Dienstes, sonst dessen Location. Siehe Single Logout weiter unten
- **Signaturzertifikat**: UCMs HTTPS-Zertifikat zur Signaturverifizierung
- **NameID-Format**: Die Einstellung **NameID-Format** des Providers (Nicht angegeben, Persistent, E-Mail-Adresse oder Transient), auch in jeder Anmeldeanfrage gesendet. Persistent liefert eine stabile Kennung; eine transiente NameID dient nie zur Wiedererkennung des Kontos

Kopieren Sie diese URL in die „Service Provider hinzufügen"- oder „SAML-Anwendung"-Konfiguration Ihres IDP.

> ⚠️ **Wichtig:** Das HTTPS-Zertifikat von UCM muss **vom IDP vertraut werden**. Wenn der IDP das Zertifikat nicht validieren kann (z.B. selbstsigniert oder von einer privaten CA ausgestellt), werden die Metadaten als ungültig abgelehnt. Importieren Sie das CA-Zertifikat von UCM in den Vertrauensspeicher des IDP oder verwenden Sie ein von einer öffentlich vertrauenswürdigen CA signiertes Zertifikat.

### Konfiguration
1. Erhalten Sie die IDP-Metadaten-URL oder XML-Datei von Ihrem Identitätsanbieter
2. Gehen Sie in UCM zu **Einstellungen → SSO**
3. Klicken Sie auf **Anbieter hinzufügen** → SAML
4. Geben Sie die **IDP-Metadaten-URL** ein. UCM füllt automatisch Entity ID, SSO/SLO-URLs und Zertifikat
5. Oder fügen Sie das IDP-Metadaten-XML direkt ein
6. Konfigurieren Sie die **Attributzuordnung** (Benutzername, E-Mail, Gruppen)
7. Klicken Sie auf **Speichern** und **Aktivieren**

### Attributzuordnung
Ordnen Sie IDP-SAML-Attribute UCM-Benutzerfeldern zu:
- \`username\` → UCM-Benutzername (erforderlich)
- \`email\` → UCM-E-Mail (erforderlich)
- \`groups\` → wird von den Rollenzuordnungsregeln gelesen (optional); es macht den Benutzer nicht zum Mitglied von UCM-Gruppen

### Single Logout
Beendet der IdP eine Sitzung, sendet er ein signiertes **LogoutRequest** über den Browser an die SLO-URL. UCM prüft die IdP-Signatur, den Aussteller, Destination (erforderlich), IssueInstant (innerhalb des Zeitfensters) und dass die Anfrage nicht bereits verwendet wurde, schließt die UCM-Sitzung dieser NameID in diesem Browser (trägt die Anfrage SessionIndex-Werte, nur eine von ihnen genannte Sitzung) und sendet dann eine **LogoutResponse** an die SLO-URL des IdP, mit dem SP-Schlüssel signiert; ein SP-Zertifikat, das nicht RSA ist, sendet sie unsigniert, was ein strenger IdP wie AD FS ablehnt. Ohne SLO-URL des IdP kehrt der Browser zur UCM-Anmeldeseite zurück. Ein unsigniertes oder gefälschtes LogoutRequest wird abgelehnt, und die Sitzung bleibt offen.

### IdP-initiierte Anmeldung
Eine im IdP-Portal gestartete Anmeldung erreicht UCM ohne Anfrage von UCM. **IdP-initiierte Anmeldung zulassen** akzeptiert sie, mit denselben Prüfungen von Signatur, Zielgruppe, Destination, Gültigkeit und Wiederholung. Vor 2.243 angelegte Provider behalten die Option aktiv; neue haben sie aus. Aktivieren Sie sie nur, wenn Benutzer im IdP-Portal starten.

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
Wenn aktiviert, wird bei der ersten SSO-Anmeldung automatisch ein neues UCM-Benutzerkonto erstellt, wobei die vom IDP bereitgestellten Attribute verwendet werden, mit der Rolle, die seine Zuordnungsregel vergibt, sonst der Standardrolle.

## Wer sich anmelden darf

### Identitätszuordnung
Eine Anmeldung öffnet das Konto, das an die IdP-Kennung gebunden ist: OIDC \`sub\`, persistente SAML-NameID, LDAP \`entryUUID\` oder \`objectGUID\`. Ein Benutzername oder eine E-Mail passt nur zu einem noch nicht gebundenen Konto desselben Providers (vor den stabilen Kennungen angelegt oder von einem Administrator verknüpft); eine E-Mail, die der OIDC-IdP als unverifiziert markiert (\`email_verified\` false), passt zu keinem. Ein lokales Konto oder eines, das an eine andere Identität gebunden ist, wird durch eine SSO-Anmeldung nie geöffnet: Die Anmeldung wird abgelehnt und im Audit-Protokoll erfasst. Um ein lokales Konto in eine SSO-Identität zusammenzuführen, verwenden Sie zuerst **Mit SSO verknüpfen** bei diesem Benutzer; die nächste Anmeldung über diesen Provider bindet die IdP-Kennung.

Wird ein Provider gelöscht, bleiben seine Benutzer erhalten: Ein erneut angelegter Provider für denselben IdP (gleicher Aussteller, gleiche Entity ID oder gleicher LDAP-Server und Basis-DN) übernimmt sie bei ihrer nächsten Anmeldung. Andernfalls, und für Benutzer, die eine Wiederherstellung ohne Provider hinterlassen hat, verwenden Sie bei jedem Konto **Verknüpfung lösen** und dann **Mit SSO verknüpfen**.

### Rollenzuordnungsregeln
- **Mindestens eine Regel**: Ein Benutzer, auf den keine Regel passt, wird bei jeder SSO-Anmeldung (OIDC, SAML, LDAP) abgelehnt, ob das Konto neu ist oder schon existiert; eine Anmeldung per Passkey oder Zertifikat wird nicht geprüft
- **Keine Regel**: Jeder vom Provider authentifizierte Benutzer kann sich anmelden; neue Konten erhalten die **Standardrolle**
- Eine Regel, die nur eine benutzerdefinierte Rolle vergibt: Ein neues Konto erhält die **Standardrolle** als Basisrolle (Viewer bei Keine)
- **Standardrolle: Keine** ohne Regel: Niemand kann sich über den Provider anmelden

Der Abschnitt **Benutzerbereitstellung** öffnet sich von selbst und zeigt eine Warnung, wenn der Provider keine Regel hat.

## LDAP

### Konfiguration
1. Gehen Sie in UCM zu **Einstellungen → SSO**
2. Klicken Sie auf **Anbieter hinzufügen** → LDAP
3. Geben Sie den **LDAP-Server**-Hostnamen und **Port** ein (389 für LDAP, 636 für LDAPS)
4. Aktivieren Sie **SSL/TLS verwenden** (LDAPS, Port 636) oder, auf Port 389, **StartTLS verwenden**: Die Verbindung wechselt vor jedem Bind zu TLS, mit derselben Zertifikatsprüfung. Ohne beides laufen Bind- und Benutzerpasswörter im Klartext durchs Netz
5. Geben Sie **Bind-DN** und **Bind-Passwort** ein (Dienstkonto-Anmeldedaten)
6. Geben Sie den **Basis-DN** ein (Suchbasis für Benutzersuchen)
7. Konfigurieren Sie den **Benutzerfilter** (z.B. \`(uid={username})\` oder \`(sAMAccountName={username})\` für AD)
8. Ordnen Sie LDAP-Attribute zu: **Benutzername**, **E-Mail**, **vollständiger Name** und das **eindeutige ID-Attribut** (\`entryUUID\`, \`objectGUID\`). Ein über seinen DN gebundenes Konto wechselt bei der nächsten Anmeldung zu dieser Kennung; der Wechsel von einem ID-Attribut zu einem anderen lehnt jeden gebundenen Benutzer ab, bis **Verknüpfung lösen** und dann **Mit SSO verknüpfen** erfolgt
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
