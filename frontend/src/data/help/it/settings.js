export default {
  helpContent: {
    title: 'Impostazioni',
    subtitle: 'Configurazione del sistema',
    overview: 'Configura tutti gli aspetti del sistema UCM. Le impostazioni sono organizzate per categoria: generale, aspetto, email, sicurezza, SSO, backup, audit, database, HTTPS, aggiornamenti e webhook.',
    sections: [
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
          { label: 'Database', text: 'Percorso del database, dimensione e stato delle migrazioni' },
          { label: 'HTTPS', text: 'Certificato TLS per l\'interfaccia web UCM' },
          { label: 'Aggiornamenti', text: 'Verifica nuove versioni, visualizza changelog, aggiornamento automatico (DEB/RPM)' },
          { label: 'Webhook', text: 'Webhook HTTP per eventi certificato (emissione, revoca, scadenza)' },
        ]
      },
    ],
    tips: [
      'Usa il widget Stato del sistema in alto per controllare rapidamente lo stato dei servizi',
      'Testa le impostazioni SMTP prima di fare affidamento sulle notifiche email',
      'Personalizza il template email con il tuo branding utilizzando l\'editor HTML/Testo integrato',
      'Pianifica backup automatici per gli ambienti di produzione',
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

Informazioni sul database UCM:
- Percorso su disco
- Dimensione file
- Versione migrazione
- Versione SQLite

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

### Creazione di un webhook
1. Clicca **Aggiungi webhook**
2. Inserisci l'**URL** (deve essere HTTPS)
3. Seleziona gli **eventi** a cui iscriversi
4. Facoltativamente imposta un **segreto** per la verifica della firma HMAC
5. Clicca **Crea**

### Test
Clicca **Test** per inviare un evento di esempio all'URL del webhook e verificare che sia raggiungibile.
`
  }
}
