export default {
  helpContent: {
    title: 'Impostazioni',
    subtitle: 'Configurazione del sistema',
    overview: 'Configura tutti gli aspetti del sistema UCM. Le impostazioni sono organizzate per categoria: generale, aspetto, email, sicurezza, SSO, backup, audit, database, HTTPS, aggiornamenti e webhook.',
    sections: [
      {
        title: "Metriche Prometheus",
        content: "Endpoint /metrics opzionale che espone contatori (certificati, CA, scheduler, webhook, ACME) in formato Prometheus.",
        items: [
          { label: "Attivazione", text: "Imposta un token metriche in Impostazioni › Generale; senza token l'endpoint restituisce 404 (disattivato)" },
          { label: "Autenticazione", text: "Esegui lo scrape con Authorization: Bearer <token>" },
          { label: "Contatori", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Vhost ACME pubblico",
        content: "Impostazioni › Generale: hostname e porta pubblici per gli URL del directory ACME dietro un reverse proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com — GUI e API (mTLS secondo policy)" },
          { label: "ACME", text: "acme.ucm.example.com — /acme/* e /acme/proxy/* (senza mTLS client)" },
          { label: "TLS wildcard", text: "Hostname concreto (es. acme.ucm.example.com). Un SAN *.ucm.example.com sul certificato copre TLS admin e ACME — non inserire *.ucm.example.com come vhost" },
          { label: "Prima di salvare", text: "DNS e TLS pronti per il vhost ACME — i client cambiano subito le URL del directory" },
          { label: "ID certificato TLS", text: "Metadati del certificato sul vhost ACME (es. wildcard)" },
        ]
      },
      {
        title: "Cronologia di consegna dei webhook",
        content: "Ogni endpoint webhook mantiene un registro di consegna con stato, tentativi e nuovo tentativo manuale.",
        items: [
          { label: "Stati", text: "pending / delivered / failed, con l'ultimo codice HTTP ed errore" },
          { label: "Riprova", text: "Rimetti manualmente in coda un evento fallito o già consegnato" },
          { label: "Asincrono", text: "Le consegne partono da una coda durevole con backoff esponenziale (fino a 5 tentativi)" },
        ]
      },
      {
        title: "Vista dello scheduler",
        content: "Impostazioni › Sistema elenca le attività in background con il loro stato e l'ultima esecuzione.",
        items: [
          { label: "Attività", text: "Controlli di scadenza, aggiornamento CRL, consegna webhook, backup pianificati, rinnovo automatico, ecc." },
          { label: "Esegui ora", text: "Avviare qualsiasi attività su richiesta" },
          { label: "Visibilità", text: "Ultima esecuzione, ultima durata e numero di errori per attività" },
        ]
      },
      {
        title: "Backup pianificati",
        content: "Backup automatici e cifrati del database, con cadenza configurabile e ritenzione.",
        items: [
          { label: "Cadenza", text: "Giornaliera / settimanale / mensile" },
          { label: "Ritenzione", text: "Conservare i N backup più recenti; quelli più vecchi vengono eliminati" },
          { label: "Cifratura", text: "I backup sono cifrati con la password di backup configurata" },
        ]
      },
      {
        title: 'Aggiornamenti automatici (v2.215)',
        content: 'Impostazioni › Aggiornamenti: un controllo giornaliero in background delle nuove versioni e un\'installazione non presidiata opzionale.',
        items: [
          { label: "Canale", text: "Versioni stabili segue solo i rilasci finali; Release candidate accetta in più soltanto le versioni rcN — mai alpha/beta" },
          { label: 'Notifica', text: 'Una nuova versione disponibile attiva l\'evento webhook/email system.update_available, una volta per versione' },
          { label: 'Installazione automatica', text: 'Disattivata per impostazione predefinita. Se abilitata, UCM scarica, verifica e installa l\'aggiornamento all\'ora scelta, poi si riavvia — solo installazioni DEB/RPM' },
          { label: 'Checksum', text: 'Un\'installazione non presidiata richiede lo SHA256 pubblicato del rilascio per la verifica; anche un\'installazione manuale verifica ogni volta che un checksum è pubblicato' },
          { label: 'Docker', text: 'I container non possono aggiornarsi da soli — il controllo e la notifica funzionano comunque; esegui il pull della nuova immagine per aggiornare' },
          { label: 'Popup post-aggiornamento', text: 'Opzionale (v2.217): mostra una volta le note di versione dopo l\'installazione di un aggiornamento, per utente. Disattivato per impostazione predefinita' },
        ]
      },
      {
        title: "HSTS (Strict Transport Security)",
        content: "Policy HSTS configurabile dall'operatore affinché le istanze con certificati autofirmati durante la configurazione iniziale possano escludersi del tutto.",
        items: [
          { label: "Predefinito", text: "HSTS attivo, includeSubDomains, max-age 1 anno (retrocompatibile)" },
          { label: "Disabilita", text: "Disabilita per istanze con certificati autofirmati durante la configurazione iniziale (evita il blocco del browser)" },
          { label: "Variabile d'ambiente", text: "UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE in /etc/ucm/ucm.env prevalgono sul DB" },
          { label: "Sottodomini", text: "Rimuovi includeSubDomains quando i sottodomini ospitano servizi separati con certificati propri" },
        ]
      },
      {
        title: 'Categorie',
        items: [
          { label: 'Generale', text: 'Nome dell\'istanza, hostname e impostazioni predefinite di sistema' },
          { label: 'Aspetto', text: 'Selezione tema (chiaro/scuro/sistema), colore principale, modalità desktop' },
          { label: 'Email (SMTP)', text: 'Server SMTP, credenziali, editor template email e notifiche avvisi scadenza' },
          { label: 'Sicurezza', text: 'Politiche password, timeout sessione, limitazione frequenza, restrizioni IP' },
          { label: 'SSO', text: 'Integrazione single sign-on SAML 2.0, OAuth2/OIDC e LDAP' },
          { label: 'Backup', text: 'Backup del database manuali e pianificati' },
          { label: 'Audit', text: 'Conservazione log, inoltro syslog, verifica dell\'integrità' },
          { label: 'Database', text: 'Backend attivo (SQLite o PostgreSQL), dimensione, numero di tabelle, testare/cambiare/migrare tra backend' },
          { label: 'HTTPS', text: 'Certificato TLS per l\'interfaccia web UCM. Il certificato applicato viene ricordato e riapplicato al suo rinnovo (v2.217); il certificato associato è mostrato con un pulsante di dissociazione per smettere di seguire i rinnovi (v2.218)' },
          { label: 'Aggiornamenti', text: 'Verifica nuove versioni, visualizza changelog, controllo giornaliero pianificato con installazione non presidiata opt-in (DEB/RPM)' },
          { label: 'Webhook', text: 'Webhook HTTP per eventi certificato (emissione, revoca, scadenza). Autenticazione in uscita opzionale: Bearer, Basic, API key o intestazione personalizzata' },
          { label: 'Distribuzione', text: 'Destinazioni di distribuzione: host remoti a cui i certificati vengono inviati via SSH/SFTP all\'emissione e al rinnovo, con un comando di ricarica fisso (solo admin, v2.215)' },
          { label: 'Active Directory', text: 'Connessione AD/LDAP propria di UCM per le ricerche relative ai certificati (risoluzione principal Kerberos, soggetti derivati da AD)' },
          { label: 'Iscrizione automatica Windows', text: 'Iscrizione Windows nativa MS-XCEP/MS-WSTEP: rilevamento dei criteri, emissione dei certificati e associazione Kerberos/SPNEGO' },
        ]
      },
      {
        title: 'Hook di distribuzione (v2.215)',
        content: 'Impostazioni › Distribuzione (solo admin): host remoti a cui UCM invia i certificati via SFTP, per poi eseguire un unico comando di ricarica fisso via SSH.',
        items: [
          { label: 'Destinazione', text: 'Host, porta, utente SSH. UCM genera una chiave ed25519 (installa la chiave pubblica mostrata sulla destinazione) o accetta una chiave privata importata — archiviata cifrata' },
          { label: 'Host key', text: 'Registrata alla prima connessione riuscita (trust-on-first-use); qualsiasi cambiamento successivo blocca la connessione. Cambiare l\'host la registra di nuovo' },
          { label: 'Comando di ricarica', text: 'Un solo comando fisso definito dall\'admin, eseguito dopo un invio riuscito (es. systemctl reload nginx) — exit 0 = successo, senza templating' },
          { label: 'Associazioni', text: 'I certificati vengono associati alle destinazioni dalla vista di dettaglio del certificato, con percorsi di destinazione per ogni file' },
          { label: 'Consegna', text: 'Gli invii avvengono in modo asincrono tramite una coda durevole con tentativi e backoff; stato per consegna, distribuzione e riprova manuali, tracciato di audit completo' },
          { label: 'Privilegi minimi', text: 'Usa un account SSH dedicato su ogni destinazione: accesso in scrittura ai percorsi dei certificati e permesso di ricaricare il servizio, nient\'altro' },
        ]
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content: 'Autenticazione OAuth2 moderna per la posta in uscita, in sostituzione dei vecchi flussi app-password che Microsoft e Google stanno dismettendo:',
        items: [
          { label: 'Gmail', text: 'Configurare un client OAuth2 Google Cloud con scope https://mail.google.com/' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Registrare un\'app Azure AD con permesso delegato SMTP.Send' },
          { label: 'Refresh token', text: 'UCM memorizza il refresh token e rinnova gli access token automaticamente prima di ogni invio' },
          { label: 'Fallback', text: 'L\'autenticazione a password resta supportata se OAuth2 non è configurato' },
        ]
      },
      {
        title: 'Connettore Active Directory',
        content: 'Connessione LDAP propria di UCM ad Active Directory, indipendente da qualsiasi provider LDAP configurato in SSO -- quello serve per accedere a UCM, questo per le ricerche AD relative ai certificati.',
        items: [
          { label: 'Scopo', text: 'Risolve un account macchina o utente Kerberos nel relativo oggetto AD, in modo che UCM possa derivare un soggetto/SAN del certificato, proprio come farebbe una vera CA Windows' },
          { label: 'Campi', text: 'Server, porta, LDAPS con verifica CA facoltativa, DN Base, DN Bind/password' },
          { label: 'Verifica connessione', text: 'Verificare la connettività e le credenziali prima di salvare' },
          { label: 'URL di iscrizione GPO', text: 'URL dei criteri di iscrizione dei certificati Kerberos e Nome utente/Password da registrare nei Criteri di gruppo' },
        ]
      },
      {
        title: 'Iscrizione automatica Windows (XCEP/WSTEP)',
        content: "Iscrizione dei certificati Windows nativa tramite il rilevamento dei criteri MS-XCEP e l'emissione MS-WSTEP -- supporta l'iscrizione manuale MMC/certreq e l'iscrizione automatica GPO non presidiata.",
        items: [
          { label: 'XCEP', text: "Consente ai client Windows di scoprire i modelli di certificato disponibili prima dell'iscrizione" },
          { label: 'WSTEP', text: 'Gestisce la richiesta e il rinnovo del certificato una volta scoperto il criterio' },
          { label: 'Kerberos/SPNEGO', text: "Associa gli endpoint autenticati tramite Kerberos utilizzati per l'iscrizione automatica GPO silenziosa (richiede uno SPN e un keytab dal controller di dominio)" },
          { label: 'Elenco di controllo per la configurazione', text: "La scheda mostra un elenco di controllo in tempo reale di ciò che è configurato rispetto a ciò che manca ancora, sia per l'iscrizione manuale sia per quella non presidiata" },
          { label: 'Soggetti derivati da AD', text: "I modelli possono scegliere di derivare il proprio soggetto/SAN da Active Directory (tramite il connettore AD) per l'iscrizione non presidiata" },
        ]
      },
      {
        title: 'Rinnovo automatico',
        items: [
          { label: 'Origini', text: 'Lo scheduler rinnova i certificati la cui chiave privata è detenuta dal server: per impostazione predefinita quelli emessi dal modulo o da una richiesta firmata ("manual"), e le iscrizioni SCEP, ACME ed EST con chiave generata dal server. I dispositivi che detengono la propria chiave si rinnovano tramite il loro protocollo' },
          { label: 'In attesa di approvazione', text: 'Un certificato il cui rinnovo è in coda per l\'approvazione viene lasciato a quella decisione, purché possa arrivare prima della scadenza del certificato' },
          { label: 'Rinnovato nel frattempo', text: 'Un certificato rinnovato da un operatore durante il batch non viene rinnovato una seconda volta; uno eliminato durante il batch viene saltato' },
        ]
      },

    ],
    tips: [
      'Usa il widget Stato del sistema in alto per controllare rapidamente lo stato dei servizi',
      'Testa le impostazioni SMTP prima di fare affidamento sulle notifiche email',
      'Personalizza il template email con il tuo branding utilizzando l\'editor HTML/Testo integrato',
      'Pianifica backup automatici per gli ambienti di produzione',
      'Il passaggio SQLite ↔ PostgreSQL è bidirezionale — la UI esegue controlli di sicurezza (driver caricato, destinazione raggiungibile, destinazione vuota) prima della migrazione',
    ],
    warnings: [
      'La modifica del certificato HTTPS richiede un riavvio del servizio',
      'La modifica delle impostazioni di sicurezza potrebbe bloccare gli utenti — verifica l\'accesso prima di salvare',
    ],
  },
  helpGuides: {
    title: 'Impostazioni',
    content: `
## Panoramica

Configurazione a livello di sistema organizzata in schede. Le modifiche hanno effetto immediato salvo diversa indicazione.

## Generale

- **Nome istanza** — Visualizzato nel titolo del browser e nelle email
- **Hostname** — Il nome di dominio completo del server
- **Validità predefinita** — Periodo di validità predefinito del certificato in giorni
- **Soglia avviso scadenza** — Giorni prima della scadenza per attivare gli avvisi
- **Vhost ACME pubblico** — Hostname concreto negli URL del directory ACME (es. \`acme.ucm.example.com\` — non \`*.ucm.example.com\`). Un **SAN del certificato TLS** wildcard \`*.ucm.example.com\` copre sia \`admin.ucm.example.com\` sia \`acme.ucm.example.com\`. Configura DNS e TLS per il vhost ACME **prima** di salvare — i client che rileggono il directory cambiano subito gli URL.

## Aspetto

- **Tema** — Chiaro, Scuro o Sistema (segue la preferenza del sistema operativo)
- **Colore principale** — Colore primario usato per pulsanti, link ed evidenziazioni
- **Forza modalità desktop** — Disabilita il layout mobile responsivo
- **Comportamento barra laterale** — Compressa o espansa per impostazione predefinita

## Email (SMTP)

Configura SMTP per le notifiche email (avvisi scadenza, inviti utente):
- **Host SMTP** e **Porta**
- **Nome utente** e **Password**
- **Crittografia** — Nessuna, STARTTLS o SSL/TLS
- **Indirizzo mittente** — Indirizzo email del mittente
- **Tipo contenuto** — HTML, Testo semplice o Entrambi
- **Destinatari avvisi** — Aggiungi più destinatari usando l'input a tag

Clicca **Test** per inviare un'email di test e verificare la configurazione.

### Editor template email

Clicca **Modifica template** per aprire l'editor template a pannello diviso in una finestra mobile:
- **Scheda HTML** — Modifica il template email HTML con anteprima in tempo reale sulla destra
- **Scheda testo semplice** — Modifica la versione in testo semplice per i client email che non supportano HTML
- Variabili disponibili: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Clicca **Ripristina predefinito** per ripristinare il template con branding UCM integrato
- La finestra è ridimensionabile e trascinabile per una modifica confortevole

### Avvisi scadenza

Quando SMTP è configurato, abilita gli avvisi automatici di scadenza certificati:
- Attiva/disattiva gli avvisi
- Seleziona le soglie di avviso (90gg, 60gg, 30gg, 14gg, 7gg, 3gg, 1gg)
- Esegui **Verifica ora** per attivare una scansione immediata

## Sicurezza

### Politica password
- Lunghezza minima (8-32 caratteri)
- Richiedi maiuscole, minuscole, numeri, caratteri speciali
- Scadenza password (giorni)
- Cronologia password (impedisci riutilizzo)

### Gestione sessioni
- Timeout sessione (minuti di inattività)
- Sessioni simultanee massime per utente

### Limitazione frequenza
- Limite tentativi di accesso per IP
- Durata del blocco dopo il superamento del limite

### Restrizioni IP
Consenti o nega l'accesso da indirizzi IP o intervalli CIDR specifici.

### Imposizione 2FA
Richiedi a tutti gli utenti di abilitare l'autenticazione a due fattori.

### Cifratura delle chiavi private
Cifra tutte le chiavi private memorizzate nel database con AES-256, protette da un file di chiave master. La sezione mostra lo stato della cifratura e i contatori delle chiavi **cifrate / non cifrate**. Due variabili d'ambiente opt-in rendono fatale all'avvio l'assenza delle chiavi: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (cifratura dei segreti delle integrazioni) e \`UCM_REQUIRE_KEY_ENCRYPTION\` (cifratura delle chiavi private).

> 💡 Le impostazioni sensibili alla sicurezza (sessione, blocco, HSTS, URL pubblico, politica password) richiedono il permesso **admin:settings** — i campi sono bloccati per gli operatori.

> ⚠ Testa attentamente le restrizioni IP prima di applicarle. Regole errate possono bloccare tutti gli utenti.

## SSO (Single Sign-On)

### SAML 2.0
- Fornisci al tuo IDP l'**URL metadati SP**: \`/api/v2/sso/saml/metadata\`
- Oppure configura manualmente: carica/collega il file XML dei metadati IDP, configura Entity ID e URL ACS
- Mappa gli attributi IDP ai campi utente UCM (nome utente, email, ruolo)

### OAuth2 / OIDC
- URL di autorizzazione e URL del token
- Client ID e Client Secret
- URL info utente (per il recupero degli attributi)
- Scope (openid, profile, email)
- Creazione automatica utenti al primo accesso SSO

### LDAP
- Hostname del server, porta (389/636), toggle SSL
- Bind DN e password (account di servizio)
- Base DN e filtro utente
- Mappatura attributi (nome utente, email, nome completo)

> 💡 Mantieni sempre un account amministratore locale come fallback in caso di problemi con SSO.

## Backup

### Backup manuale
Clicca **Crea backup** per generare uno snapshot del database. I backup includono tutti i certificati, CA, chiavi, impostazioni e log di audit.

### Backup pianificato
Configura backup automatici:
- Frequenza (giornaliero, settimanale, mensile)
- Conteggio conservazione (numero di backup da mantenere)

### Ripristino
Carica un file di backup per ripristinare UCM a uno stato precedente.

> ⚠ Il ripristino di un backup sostituisce TUTTI i dati attuali.

## Audit

- **Conservazione log** — Pulizia automatica dei vecchi log dopo N giorni
- **Inoltro syslog** — Invia eventi a un server syslog remoto (UDP/TCP/TLS)
- **Verifica integrità** — Abilita il concatenamento hash per il rilevamento manomissioni

## Database

UCM supporta due backend di database:

- **SQLite** (predefinito) — basato su file, senza configurazione, ideale per nodo singolo
- **PostgreSQL 13+** — consigliato per alta disponibilità, multi-istanza o se gestisci già un cluster PG

Il backend attivo è selezionato dalla variabile d'ambiente \`DATABASE_URL\`. Se non impostata, UCM usa SQLite in \`UCM_DATA_DIR/ucm.db\`.

### Pannello di stato
- Backend attivo (sqlite / postgresql) e driver
- Dimensione del database e numero di tabelle
- Versione di migrazione

### Testare la connessione
Convalida una \`DATABASE_URL\` (es. \`postgresql://user:pass@host:5432/ucm\`) prima di passare. Il test apre una connessione reale e riporta eventuali errori. I server PostgreSQL precedenti alla versione 13 vengono rifiutati — UCM richiede PostgreSQL 13 o più recente.

### Cambiare backend
Salva \`DATABASE_URL\` in \`/etc/ucm/ucm.env\` (DEB/RPM) e riavvia UCM. **Nessun dato viene copiato** — usa prima **Migra** se vuoi conservare i dati esistenti.

### Migrare i dati
Copia tutte le righe dal backend corrente al backend di destinazione. Funziona in entrambe le direzioni (SQLite ↔ PostgreSQL):

1. Il database di origine viene salvato in \`/opt/ucm/data/backups/db_migration/\`
2. Lo schema viene creato sulla destinazione tramite SQLAlchemy
3. I vincoli FK sono disabilitati durante il caricamento massivo
4. Le colonne origine/destinazione vengono intersecate (le colonne legacy sono ignorate con un avviso)
5. Le sequenze PostgreSQL vengono ripristinate dopo il caricamento
6. Il servizio si riavvia automaticamente (DEB/RPM) — su Docker imposta \`DATABASE_URL\` nel file compose e riavvia manualmente il container

**Controlli di sicurezza (fail-fast, sorgente intatta):**
- La destinazione deve essere vuota. Se \`users\`, \`cas\` o \`certificates\` contengono già righe, la migrazione viene rifiutata con HTTP 409 e un suggerimento di pulizia:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - SQLite: eliminare il file \`.db\` di destinazione
- Se la migrazione fallisce a metà, la sorgente rimane intatta e il messaggio di errore indica il backup della sorgente. Reimpostare la destinazione prima di riprovare.

> ⚠ Esegui sempre un backup completo di UCM (Impostazioni → Backup) prima di migrare tra backend.

## HTTPS

Gestisci il certificato TLS utilizzato dall'interfaccia web UCM:
- Visualizza i dettagli del certificato attuale
- Importa un nuovo certificato (PEM o PKCS#12)
- Genera un certificato autofirmato

> ⚠ La modifica del certificato HTTPS richiede un riavvio del servizio.

## Aggiornamenti

- Verifica la disponibilità di nuove versioni UCM dai rilasci GitHub
- Visualizza il changelog per gli aggiornamenti disponibili
- Versione attuale e informazioni di build
- **Aggiornamento automatico**: su installazioni supportate (DEB/RPM), clicca **Aggiorna ora** per scaricare e installare automaticamente l'ultima versione
- **Includi pre-release**: attiva per verificare anche i release candidate (rc)

## Webhook

Configura webhook HTTP per notificare sistemi esterni sugli eventi:

### Eventi supportati
- Certificato emesso, revocato, scaduto, rinnovato
- CA creata, eliminata
- Accesso utente, uscita utente
- Backup creato

### Autenticazione

Autenticazione in uscita opzionale (si applica oltre la firma HMAC opzionale):

- **Nessuna** — Nessun intestazione di autenticazione (webhook pubblici)
- **Bearer** — Authorization: Bearer {token}
- **Basic** — Authorization: Basic base64(utente:password)
- **API Key** — Intestazione personalizzata (p.es. X-Api-Key: {token})
- **Personalizzata** — Authorization: {schema} {token} (p.es. auth-key VALORE)

I token sono archiviati crittografati e mai restituiti nell'UI.

### Creazione di un webhook
1. Clicca **Aggiungi webhook**
2. Inserisci l'**URL** (deve essere HTTPS)
3. Seleziona gli **eventi** a cui iscriversi
4. Scegli il **tipo di autenticazione** e fornisci le credenziali (facoltativo)
5. Facoltativamente imposta un **segreto** per la verifica della firma HMAC
6. Clicca **Crea**

### Test
Clicca **Test** per inviare un evento di esempio all'URL del webhook e verificare che sia raggiungibile.
## Metriche Prometheus

Endpoint **\`/metrics\`** opt-in e protetto da token.

- Attivalo impostando un token metriche (Impostazioni › Generale); senza token → 404
- Esegui lo scrape con l'header \`Authorization: Bearer <token>\`
- Espone \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\`

## Cronologia di consegna dei webhook

Apri la cronologia (icona orologio) su un webhook per vederne le consegne.

- Stati **pending / delivered / failed** con ultimo codice HTTP ed errore
- **Riprova** una consegna manualmente
- Coda durevole con backoff esponenziale (fino a 5 tentativi)

## Vista dello scheduler

Impostazioni › Sistema mostra le attività in background.

- Elenco attività con **stato**, **ultima esecuzione**, **durata** ed **errori**
- **Esegui ora** su qualsiasi attività
- Copre scadenza, CRL, consegna webhook, backup, rinnovo automatico…

## Rinnovo automatico
Le impostazioni di rinnovo automatico guidano lo scheduler dei rinnovi.
- **Origini** — lo scheduler rinnova i certificati la cui chiave privata è detenuta dal server: per impostazione predefinita quelli emessi dal modulo o da una richiesta firmata ("manual"), e le iscrizioni SCEP, ACME ed EST con chiave generata dal server. I dispositivi che detengono la propria chiave si rinnovano tramite il loro protocollo
- **In attesa di approvazione** — un certificato il cui rinnovo è in coda per l'approvazione viene lasciato a quella decisione, purché possa arrivare prima della scadenza del certificato
- **Rinnovato nel frattempo** — un certificato rinnovato da un operatore durante il batch non viene rinnovato una seconda volta; uno eliminato durante il batch viene saltato

## Backup pianificati

Impostazioni › Backup abilita i backup automatici.

- Cadenza **giornaliera / settimanale / mensile**
- **Ritenzione**: conserva i N più recenti, elimina i vecchi
- Backup **cifrati** con la password di backup


## Connettore Active Directory

Connessione LDAP propria di UCM ad Active Directory, indipendente da qualsiasi provider LDAP configurato in SSO. Quello serve per accedere a UCM; questo viene utilizzato per le ricerche AD relative ai certificati e funziona indipendentemente dal fatto che lo SSO sia configurato o meno.

- **Scopo** — Risolve un account macchina o utente Kerberos nel relativo oggetto AD, in modo che UCM possa derivare un soggetto/SAN del certificato proprio come farebbe una vera CA Windows
- **Server** — Nome host/IP e porta di un controller di dominio
- **LDAPS** — Attivare per usare LDAP su SSL/TLS; **Verifica certificato SSL** convalida il certificato del DC (facoltativamente rispetto a un bundle CA personalizzato quando non è pubblicamente attendibile)
- **DN Base** e **DN Bind / Password** — Credenziali dell'account di servizio utilizzate per le ricerche
- **Verifica connessione** — Verificare la connettività e le credenziali prima di salvare

### URL dei criteri di iscrizione GPO

Una volta configurato, registrare uno degli URL visualizzati come server dei criteri di iscrizione dei certificati nei Criteri di gruppo (Criteri chiave pubblica → Client dei servizi certificati – Criteri di iscrizione dei certificati), insieme a Client dei servizi certificati – Iscrizione automatica:
- **Kerberos** — Nessuna richiesta di credenziali; richiede un client aggiunto al dominio e il tipo di autenticazione della GPO impostato su Kerberos
- **Nome utente/Password** — Richiede le credenziali; solo per l'iscrizione interattiva "Richiedi nuovo certificato"

## Iscrizione automatica Windows (XCEP/WSTEP)

Iscrizione dei certificati Windows nativa tramite **MS-XCEP** (rilevamento dei criteri) e **MS-WSTEP** (emissione e rinnovo dei certificati) -- gli stessi protocolli utilizzati da un vero ADCS per l'iscrizione interattiva "Richiedi nuovo certificato" in MMC, \`certreq\` e l'iscrizione automatica GPO non presidiata.

### Elenco di controllo per la configurazione

La scheda tiene traccia di ciò che è configurato rispetto a ciò che manca ancora, sia per il percorso di iscrizione manuale sia per quello non presidiato -- un'autorità di certificazione, il rilevamento dei criteri (XCEP), l'emissione dei certificati (WSTEP) e, per l'iscrizione automatica GPO non presidiata, un connettore Active Directory, Kerberos/SPNEGO e almeno un modello con l'iscrizione automatica consentita.

### Rilevamento dei criteri (XCEP)

- **Autorità di certificazione** — La CA i cui modelli vengono pubblicizzati e che emette certificati tramite questa configurazione
- **Validità (giorni)** — Validità predefinita applicata ai certificati emessi tramite WSTEP

### Kerberos / SPNEGO

Associa gli endpoint XCEP/WSTEP autenticati tramite Kerberos utilizzati per l'iscrizione automatica GPO silenziosa, in modo che macchine e utenti vengano autenticati tramite il proprio ticket Kerberos anziché con una richiesta di credenziali:
- **Nome principale del servizio (SPN)** — ad es. \`HTTP/ucm.esempio.it@ESEMPIO.IT\`
- **Keytab** — Generato con \`ktpass\` o \`ktutil\` sul controller di dominio per lo SPN sopra indicato

> ⚠ Se la libreria SPNEGO lato server non è installata, l'autenticazione Kerberos non funzionerà anche se abilitata qui -- viene mostrato un avviso nella scheda.

### URL dei criteri di iscrizione

- **Nome utente/Password** — Richiede le credenziali; per l'iscrizione interattiva "Richiedi nuovo certificato", non richiede Active Directory
- **Kerberos** — Nessuna richiesta di credenziali; richiede un client aggiunto al dominio e la configurazione GPO

### Vincolo di rinnovo con certificato

Oltre a Nome utente/Password e Kerberos, WSTEP supporta il **rinnovo con certificato client**, rispecchiando i veri endpoint CES di ADCS: la richiesta di rinnovo (RST) deve essere firmata XML-DSig con la chiave privata di un certificato **emesso dallo stesso UCM**. Il certificato presentato viene confrontato **byte per byte** con il certificato memorizzato per la CA configurata — il numero di serie o il soggetto da soli non bastano mai. Questo consente ai client Windows di rinnovare in modo non presidiato usando il certificato attuale, senza credenziali né ticket Kerberos.

### Estensione di sicurezza SID (KB5014754)

Nell'**emissione autenticata Kerberos**, UCM incorpora il SID AD del richiedente nell'estensione di sicurezza SID di Microsoft (\`szOID_NTDS_CA_SECURITY_EXT\`) del certificato emesso. I domain controller la usano per la **mappatura forte dei certificati** (KB5014754) — obbligatoria da quando AD impone la mappatura forte per l'autenticazione basata su certificati (accesso con smartcard, PKINIT).

### Soggetti derivati da AD

Un modello di certificato può scegliere **Crea soggetto da Active Directory** (Modelli → Iscrizione): per l'iscrizione automatica GPO non presidiata, il soggetto e il SAN vengono derivati dall'oggetto AD del richiedente tramite il connettore AD invece di richiedere al client di fornirne uno -- corrisponde alla configurazione di un modello ADCS reale per l'iscrizione automatica. Indipendentemente, **Consenti iscrizione automatica** pubblicizza il modello come \`autoEnroll=true\` nei criteri di iscrizione dei certificati, in modo che i client autenticati tramite GPO/Kerberos lo richiedano automaticamente all'accesso.
`
  }
}
