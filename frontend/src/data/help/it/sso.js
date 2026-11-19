export default {
  helpContent: {
    title: 'Single Sign-On',
    subtitle: 'Integrazione SAML, OAuth2 e LDAP',
    overview: 'Configura il Single Sign-On per consentire agli utenti di autenticarsi tramite il provider di identità della propria organizzazione. Supporta i protocolli SAML 2.0, OAuth2/OIDC e LDAP.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Identity Provider', text: 'Configura l\'URL dei metadati IDP o carica il file XML' },
          { label: 'URL metadati SP', text: 'Fornisci questo URL al tuo IDP per configurare automaticamente UCM come service provider' },
          { label: 'Certificato SP', text: 'Il certificato HTTPS UCM incluso nei metadati, deve essere fidato dall\'IDP o i metadati verranno rifiutati' },
          { label: 'Entity ID', text: 'Identificatore del service provider UCM' },
          { label: 'URL ACS', text: 'URL di callback Assertion Consumer Service' },
          { label: 'Mappatura attributi', text: 'Colonna sinistra: il nome dell\'attributo inviato dall\'IdP. Colonna destra: il campo UCM che compila (username, email, fullname o groups). Esempio: user.userprincipalname → username.' },
          { label: 'Gruppi per la mappatura ruoli', text: 'Letti dagli attributi mappati su groups, altrimenti da groups e dai claim di gruppi e ruoli di Microsoft Entra ID / AD FS. Quando Entra ID invia groups.link al posto dei gruppi (utenti in più di 150 gruppi), viene registrato un avviso e si applica il ruolo predefinito: emettere solo i gruppi assegnati all\'applicazione, o i ruoli applicazione.' },
          { label: 'Accesso avviato dall\'IdP', text: 'Accetta gli accessi avviati dal portale dell\'IdP, verificati come qualsiasi altra risposta. Attivo per i provider creati prima della 2.243, disattivato per i nuovi: attivalo solo se gli utenti partono dal portale dell\'IdP.' },
          { label: 'Formato NameID', text: 'Non specificato (predefinito dell\'IdP), Persistente, Indirizzo e-mail o Transitorio: inviato in ogni richiesta di accesso e pubblicato nei metadati SP. Persistente fornisce un identificatore stabile; un NameID transitorio non viene mai usato per riconoscere l\'account.' },
          { label: 'Single Logout', text: 'Una LogoutRequest firmata dall\'IdP e inviata all\'URL SLO dei metadati SP (HTTP-Redirect) chiude la sessione UCM di quel NameID in questo browser, a meno che il suo SessionIndex non indichi un\'altra sessione. Una LogoutResponse torna all\'URL SLO dell\'IdP, firmata con la chiave SP (non firmata quando il certificato SP non è RSA, cosa che un IdP rigoroso rifiuta); senza un URL SLO dell\'IdP il browser torna alla pagina di accesso. Una richiesta non firmata, falsificata, scaduta o riprodotta, o senza Destination, viene rifiutata.' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'URL di autorizzazione', text: 'Endpoint di autorizzazione OAuth2' },
          { label: 'URL del token', text: 'Endpoint del token OAuth2' },
          { label: 'Client ID/Secret', text: 'Credenziali client OAuth2 dal tuo IDP' },
          { label: 'Scope', text: 'Scope OAuth2 da richiedere (openid, profile, email)' },
          { label: 'Creazione automatica utenti', text: 'Crea automaticamente account UCM al primo accesso SSO' },
          { label: 'Gruppi per la mappatura dei ruoli', text: 'I valori dei claim roles e groups, letti insieme dall\'ID token dell\'accesso e dalla risposta UserInfo. Microsoft Entra ID li invia solo nell\'ID token: aggiungi il claim groups nella configurazione del token dell\'applicazione (i suoi valori sono gli object ID dei gruppi, quindi le chiavi di mappatura sono questi ID), oppure usa i ruoli dell\'app. Un utente in più di circa 200 gruppi non riceve il claim groups da Entra ID: viene registrato un avviso e possono corrispondere solo i ruoli dell\'app. Emetti solo i gruppi assegnati all\'applicazione, oppure i ruoli dell\'app. Con Verifica la firma dell\'ID token disattivata, i gruppi dell\'ID token contano solo quando l\'URL del token è HTTPS con verifica TLS attiva e l\'emittente e il client ID sono impostati e corrispondono al token.' },
        ]
      },
      {
        title: 'Provisioning dei ruoli (#81)',
        items: [
          { label: 'Corrispondenza identità', text: 'Un accesso apre l\'account associato all\'identificatore dell\'IdP (sub OIDC, NameID persistente SAML, entryUUID o objectGUID LDAP). Un nome utente o un\'email corrisponde solo a un account dello stesso provider non ancora associato; un account locale, o uno associato a un\'altra identità, viene rifiutato all\'accesso. Collega a SSO in Utenti associa qualsiasi account a un provider (uno locale, uno di un altro provider o uno la cui identità è cambiata): il suo prossimo accesso tramite quel provider associa l\'identificatore.' },
          { label: 'Ruolo predefinito', text: 'Assegnato agli account creati al primo accesso SSO quando il provider non ha regole di mappatura dei ruoli, e come ruolo di base di un nuovo account la cui regola di corrispondenza assegna solo un ruolo personalizzato (viewer se Nessuno). Nessuno: nessuno accede senza una regola. Le modifiche di ruolo effettuate in seguito in UCM vengono preservate.' },
          { label: 'Mappatura ruoli', text: 'Mappa i gruppi esterni (Azure AD, Okta, LDAP) → ruoli UCM (admin / operator / auditor / viewer) o ruoli personalizzati. Con almeno una regola, un utente a cui nessuna regola corrisponde viene rifiutato a ogni accesso SSO (OIDC, SAML, LDAP), account nuovo o esistente; un accesso con passkey o certificato non è controllato. Usata alla creazione dell\'utente e a ogni accesso quando la sincronizzazione dei ruoli è abilitata. Quando più gruppi corrispondono, vince il ruolo con i privilegi più alti (admin > operator > auditor > viewer): l\'ordine delle voci non conta (#221). Ogni gruppo può anche indicare un ruolo personalizzato (scelto tra i ruoli personalizzati esistenti): viene aggiunto al ruolo di base, o usato da solo. Se più gruppi corrispondenti assegnano un ruolo personalizzato, vince il primo dell\'elenco. Con la sincronizzazione dei ruoli attiva, un ruolo personalizzato impostato da SSO viene rimosso quando nessun gruppo ne assegna uno; un ruolo personalizzato assegnato a mano in UCM non viene mai toccato. I ruoli di sistema non possono essere usati come ruolo personalizzato.' },
          { label: 'Sincronizza ruolo a ogni accesso', text: 'OFF (predefinito): SSO non sovrascrive mai i ruoli gestiti in UCM. ON: il ruolo viene risincronizzato da role_mapping a ogni accesso; una regola corrispondente che non assegna un ruolo di base mantiene quello memorizzato (default_role non viene mai riapplicato).' },
          { label: 'Impone 2FA', text: 'Gli utenti di questo provider devono registrare un secondo fattore. Gli accessi LDAP richiedono un codice TOTP registrato o una chiave di sicurezza, come gli accessi locali, con o senza questa opzione; gli accessi OIDC e SAML richiedono solo la registrazione e si affidano all\'identity provider per l\'MFA.' },
          { label: 'Aggiornamento automatico utenti', text: 'Aggiorna email e nome completo a ogni accesso. NON tocca il ruolo.' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Server', text: 'Hostname e porta del server LDAP (389 o 636 per SSL)' },
          { label: 'StartTLS', text: 'Su una porta LDAP semplice, aggiorna la connessione a TLS prima di qualsiasi bind, con la stessa verifica del certificato di LDAPS. Attivo per impostazione predefinita per un nuovo provider senza SSL/TLS. Senza SSL/TLS o StartTLS, il bind e le password degli utenti attraversano la rete in chiaro.' },
          { label: 'Bind DN', text: 'Distinguished name per l\'autenticazione di bind LDAP' },
          { label: 'Base DN', text: 'Base di ricerca per le ricerche utente' },
          { label: 'Filtro utente', text: 'Filtro LDAP per trovare gli utenti (es. (uid={username}))' },
          { label: 'Mappatura attributi', text: 'Mappa gli attributi LDAP a nome utente, email, nome completo' },
          { label: 'Attributo ID univoco', text: 'Id immutabile che riconosce l\'account (entryUUID, objectGUID). Un account associato tramite il suo DN passa a questo id al suo prossimo accesso; passare da un attributo id a un altro rifiuta tutti gli utenti associati finché non si usa Collega a SSO su ciascun account.' },
          { label: 'Gruppi', text: 'Con memberOf, letti dalla voce dell\'utente stesso; con member o uniqueMember, cercati sotto il padre del Base DN quando la directory lo contiene, poi sotto il Base DN se quella ricerca viene rifiutata, altrimenti sotto il Base DN; il filtro dei gruppi è per impostazione predefinita (objectClass=*). Solo appartenenza diretta: i gruppi annidati e il gruppo primario di Active Directory (Domain Users) non vengono visti. I nomi vengono confrontati con regole e gruppi richiesti ignorando maiuscole e minuscole, gli spazi ai bordi e la lunghezza delle sequenze di spazi interni. Quando esistono regole o gruppi richiesti e i gruppi non possono essere letti, l\'accesso viene rifiutato con questo motivo. Testa mappatura legge i gruppi e decide come l\'accesso.' },
        ]
      },
    ],
    tips: [
      'Testa SSO con un account non amministratore prima per evitare blocchi',
      'Mantieni disponibile l\'accesso amministratore locale come fallback',
      'Mappa l\'attributo email dell\'IDP per garantire un\'identificazione utente univoca',
      'Usa l\'URL metadati SP per configurare automaticamente il tuo IDP (SAML)',
      'Il certificato HTTPS UCM deve essere fidato dall\'IDP affinché i metadati SAML vengano accettati',
    ],
    warnings: [
      'Un SSO configurato in modo errato può bloccare tutti gli utenti: mantieni sempre un amministratore locale',
    ],
  },
  helpGuides: {
    title: 'Single Sign-On',
    content: `
## Panoramica

SSO consente agli utenti di autenticarsi utilizzando l'Identity Provider (IDP) della propria organizzazione, eliminando la necessità di credenziali UCM separate. UCM supporta **SAML 2.0**, **OAuth2/OIDC** e **LDAP**.

## SAML 2.0

### URL metadati SP

UCM fornisce un **URL metadati Service Provider (SP)** che puoi fornire al tuo IDP per la configurazione automatica:

\`\`\`
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

Questo URL restituisce un documento XML conforme a SAML 2.0 contenente:
- **Entity ID**: Identificatore del service provider UCM
- **URL ACS**: Endpoint Assertion Consumer Service (HTTP-POST)
- **URL SLO**: Endpoint Single Logout Service
- **Certificato di firma**: Certificato HTTPS UCM per la verifica della firma
- **Formato NameID**: L'impostazione **Formato NameID** del provider (Non specificato, Persistente, Indirizzo e-mail o Transitorio), inviata anche in ogni richiesta di accesso. Persistente fornisce un identificatore stabile; un NameID transitorio non viene mai usato per riconoscere l'account

Copia questo URL nella configurazione "Aggiungi Service Provider" o "Applicazione SAML" del tuo IDP.

> ⚠️ **Importante:** Il certificato HTTPS di UCM deve essere **fidato dall'IDP**. Se l'IDP non può validare il certificato (es. autofirmato o emesso da una CA privata), rifiuterà i metadati come non validi. Importa il certificato CA di UCM nel trust store dell'IDP o usa un certificato firmato da una CA pubblicamente fidata.

### Configurazione
1. Ottieni l'URL dei metadati IDP o il file XML dal tuo identity provider
2. In UCM, vai su **Impostazioni → SSO**
3. Clicca **Aggiungi provider** → SAML
4. Inserisci l'**URL metadati IDP**: UCM compila automaticamente Entity ID, URL SSO/SLO e certificato
5. Oppure incolla direttamente l'XML dei metadati IDP
6. Configura la **mappatura attributi** (nome utente, email, gruppi)
7. Clicca **Salva** e **Abilita**

### Mappatura attributi
Mappa gli attributi SAML dell'IDP ai campi utente UCM:
- \`username\` → nome utente UCM (obbligatorio)
- \`email\` → email UCM (obbligatorio)
- \`groups\` → letto dalle regole di mappatura dei ruoli (opzionale); non rende l'utente membro dei gruppi UCM

### Single Logout
Quando l'IdP termina una sessione, invia una **LogoutRequest** firmata tramite il browser all'URL SLO. UCM controlla la firma dell'IdP, l'emittente, la Destination (obbligatoria), l'IssueInstant (entro la finestra dell'orologio) e che la richiesta non sia già stata usata, chiude la sessione UCM di quel NameID in questo browser (quando la richiesta porta valori SessionIndex, solo una sessione da essi indicata), poi invia una **LogoutResponse** all'URL SLO dell'IdP, firmata con la chiave SP; un certificato SP non RSA la invia non firmata, cosa che un IdP rigoroso come AD FS rifiuta. Senza un URL SLO dell'IdP, il browser torna alla pagina di accesso di UCM. Una LogoutRequest non firmata o falsificata viene rifiutata e la sessione resta aperta.

### Accesso avviato dall'IdP
Un accesso avviato dal portale dell'IdP arriva a UCM senza una richiesta di UCM. **Consenti l'accesso avviato dall'IdP** lo accetta, con gli stessi controlli di firma, audience, Destination, validità e riutilizzo. I provider creati prima della 2.243 lo mantengono attivo; i nuovi lo hanno disattivato. Attivalo solo se gli utenti partono dal portale dell'IdP.

## OAuth2 / OIDC

### Configurazione
1. Registra UCM come client nel tuo provider OAuth2/OIDC
2. Imposta l'**URI di reindirizzamento** a: \`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Copia **Client ID** e **Client Secret**
4. In UCM, vai su **Impostazioni → SSO**
5. Clicca **Aggiungi provider** → OAuth2
6. Inserisci l'**URL di autorizzazione** e l'**URL del token**
7. Inserisci l'**URL info utente** (per recuperare gli attributi utente dopo l'accesso)
8. Inserisci Client ID e Secret
9. Configura gli scope (openid, profile, email)
10. Clicca **Salva** e **Abilita**

### Creazione automatica utenti
Quando abilitata, un nuovo account utente UCM viene creato automaticamente al primo accesso SSO, utilizzando gli attributi forniti dall'IDP, con il ruolo assegnato dalla sua regola di mappatura, altrimenti con il ruolo predefinito.

### Gruppi per la mappatura dei ruoli
Le regole di mappatura dei ruoli confrontano le loro chiavi con i valori dei claim **roles** e **groups**, letti insieme dall'ID token dell'accesso e dalla risposta UserInfo. Microsoft Entra ID invia gruppi e ruoli dell'app solo nell'ID token: nella registrazione dell'applicazione aggiungi il claim groups in **Configurazione token** (i valori sono gli object ID dei gruppi, quindi le chiavi di mappatura sono questi ID), oppure definisci i ruoli dell'app e mappane i valori. Un utente in più di circa 200 gruppi non riceve il claim groups da Entra ID: UCM registra un avviso e possono corrispondere solo i ruoli dell'app. Emetti solo i gruppi assegnati all'applicazione, oppure i ruoli dell'app. Con **Verifica la firma dell'ID token** disattivata, i gruppi dell'ID token contano solo quando l'URL del token è HTTPS con verifica TLS attiva e l'emittente e il client ID sono impostati e corrispondono al token.

## Chi può accedere

### Corrispondenza identità
Un accesso apre l'account associato all'identificatore dell'IdP: \`sub\` OIDC, NameID persistente SAML, \`entryUUID\` o \`objectGUID\` LDAP. Un nome utente o un'email corrisponde solo a un account dello stesso provider non ancora associato (creato prima degli identificatori stabili, o collegato da un amministratore); un'email che l'IdP OIDC segna come non verificata (\`email_verified\` false) non corrisponde a nessuno. Un account locale, o uno associato a un'altra identità, non viene mai aperto da un accesso SSO: l'accesso è rifiutato e registrato nel log di audit. Quando nessun account corrisponde, un accesso la cui email appartiene a un account di un altro provider o rimasto senza provider per un altro IdP o un IdP sconosciuto (dopo un ripristino, per esempio), oppure, finché l'email non è verificata, a uno collegato a questo provider e non ancora associato, viene rifiutato invece di ricevere un secondo account. Per associare un account a un provider, usa **Collega a SSO** su quell'utente (**Cambia provider o reimposta l'identità SSO** su uno già collegato): accetta un account locale, uno di un altro provider, che sposta, e uno la cui identità è cambiata presso l'IdP, che reimposta. Il suo prossimo accesso tramite quel provider associa l'identificatore dell'IdP, e a un account senza password locale non ne viene chiesta una.

Quando un provider viene eliminato, i suoi utenti sono conservati: un provider creato di nuovo per lo stesso IdP (stesso emittente, entity ID, o server LDAP e base DN) li riprende al loro prossimo accesso. Altrimenti, e per gli utenti che un ripristino ha lasciato senza provider, usa **Collega a SSO** su ogni account.

### Regole di mappatura dei ruoli
- **Almeno una regola**: un utente a cui nessuna regola corrisponde viene rifiutato a ogni accesso SSO (OIDC, SAML, LDAP), che l'account sia nuovo o già esistente; un accesso con passkey o certificato non è controllato
- **Nessuna regola**: ogni utente autenticato dal provider può accedere; i nuovi account ricevono il **Ruolo predefinito**
- Una regola che assegna solo un ruolo personalizzato: un nuovo account riceve il **Ruolo predefinito** come ruolo di base (viewer se Nessuno)
- **Ruolo predefinito: Nessuno** senza regole: nessuno può accedere tramite il provider

La sezione **Provisioning utenti** si apre da sola e mostra un avviso quando il provider non ha regole.

## LDAP

### Configurazione
1. In UCM, vai su **Impostazioni → SSO**
2. Clicca **Aggiungi provider** → LDAP
3. Inserisci l'**hostname del server LDAP** e la **porta** (389 per LDAP, 636 per LDAPS)
4. Abilita **Usa SSL** per connessioni crittografate
5. Inserisci il **Bind DN** e la **password di bind** (credenziali dell'account di servizio)
6. Inserisci il **Base DN** (base di ricerca per le ricerche utente)
7. Configura il **filtro utente** (es. \`(uid={username})\` o \`(sAMAccountName={username})\` per AD)
8. Mappa gli attributi LDAP: **nome utente**, **email**, **nome completo** e l'**attributo ID univoco** (\`entryUUID\`, \`objectGUID\`). Un account associato tramite il suo DN passa a questo id al suo prossimo accesso; passare da un attributo id a un altro rifiuta tutti gli utenti associati finché non si usa **Collega a SSO** su ciascun account
9. Clicca **Testa connessione** per verificare, poi **Salva** e **Abilita**

### Gruppi
- **memberOf**: letto dalla voce dell'utente stesso (una ricerca di base sul suo DN); il filtro dei gruppi non viene usato
- **member / uniqueMember**: cercati sotto il padre del Base DN quando la directory lo contiene, poi sotto il Base DN se quella ricerca fallisce, con il filtro dei gruppi (\`(objectClass=*)\` se vuoto); i gruppi accanto agli utenti (\`ou=groups\` accanto a \`ou=people\`) vengono trovati
- **Solo appartenenza diretta**: i gruppi annidati e il gruppo primario di Active Directory (Domain Users) non vengono visti
- **Confronto**: i nomi dei gruppi vengono confrontati con regole e gruppi richiesti ignorando maiuscole e minuscole e gli spazi ai bordi, una sequenza di spazi interni valendo come uno solo
- **Gruppi non leggibili**: con regole o gruppi richiesti, un accesso i cui gruppi non possono essere letti viene rifiutato con «i tuoi gruppi non hanno potuto essere letti dalla directory»
- **Testa mappatura** legge i gruppi e decide come l'accesso, senza la password; mostra un ruolo solo per un utente ammesso

### Active Directory
Per Microsoft Active Directory, usa:
- Porta: **389** (o 636 con SSL)
- Filtro utente: \`(sAMAccountName={username})\`
- Attributo nome utente: \`sAMAccountName\`
- Attributo email: \`mail\`
- Attributo nome completo: \`displayName\`

## Flusso di accesso
1. L'utente clicca **Accedi con SSO** nella pagina di login UCM (o inserisce le credenziali LDAP)
2. Per SAML/OAuth2: l'utente viene reindirizzato all'IDP, si autentica e viene reindirizzato indietro
3. Per LDAP: le credenziali vengono verificate direttamente sul server LDAP
4. UCM crea o aggiorna l'account utente
5. L'utente è autenticato

> ⚠ Mantieni sempre almeno un account amministratore locale come fallback in caso di configurazione SSO errata che blocca tutti.

> 💡 Testa SSO con un account non amministratore prima di renderlo il metodo di autenticazione principale.

> 💡 Usa il pulsante **Testa connessione** per verificare la configurazione prima di abilitare un provider.
`
  }
}
