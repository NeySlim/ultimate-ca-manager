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
          { label: 'HTTPS', text: 'Certificato TLS per l\'interfaccia web UCM' },
          { label: 'Aggiornamenti', text: 'Verifica nuove versioni, visualizza changelog, aggiornamento automatico (DEB/RPM)' },
          { label: 'Webhook', text: 'Webhook HTTP per eventi certificato (emissione, revoca, scadenza). Autenticazione in uscita opzionale: Bearer, Basic, API key o intestazione personalizzata' },
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

## Backup pianificati

Impostazioni › Backup abilita i backup automatici.

- Cadenza **giornaliera / settimanale / mensile**
- **Ritenzione**: conserva i N più recenti, elimina i vecchi
- Backup **cifrati** con la password di backup

`
  }
}
