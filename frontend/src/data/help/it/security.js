export default {
  helpContent: {
    title: 'Impostazioni di sicurezza',
    subtitle: 'Autenticazione e politiche di accesso',
    overview: 'Configura le politiche password, la gestione delle sessioni, la limitazione della frequenza e la sicurezza di rete. Queste impostazioni si applicano a tutto il sistema e interessano tutti gli account utente.',
    sections: [
      {
        title: 'Cifratura delle chiavi private',
        items: [
          { label: 'Stato e contatori', text: 'Mostra se la cifratura è abilitata e quante chiavi private memorizzate sono cifrate rispetto a quelle non cifrate' },
          { label: 'Abilita / Disabilita', text: 'Cifra tutte le chiavi private con AES-256. L’abilitazione rimuove le copie in chiaro e la disabilitazione le ricrea' },
          { label: 'File di chiavi su disco', text: 'Mostra quante copie di chiavi in chiaro restano; usa gli hook di distribuzione quando un altro servizio necessita di un file di chiave' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variabile d\'ambiente opt-in: rifiuta l\'avvio senza una chiave di cifratura del database esplicita' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variabile d\'ambiente opt-in: rifiuta l\'avvio se la cifratura delle chiavi private non è abilitata' },
        ]
      },
      {
        title: 'Politica password',
        items: [
          { label: 'Lunghezza minima', text: 'Numero minimo di caratteri richiesti' },
          { label: 'Complessità', text: 'Richiedi maiuscole, minuscole, numeri, caratteri speciali' },
          { label: 'Scadenza', text: 'Forza il cambio password dopo un numero stabilito di giorni' },
          { label: 'Cronologia', text: 'Impedisci il riutilizzo delle password precedenti' },
        ]
      },
      {
        title: 'Sessione e accesso',
        items: [
          { label: 'Timeout sessione', text: 'Disconnessione automatica dopo un periodo di inattività' },
          { label: 'Limitazione frequenza', text: 'Limita i tentativi di accesso per prevenire attacchi di forza bruta' },
          { label: 'Restrizioni IP', text: 'Consenti o nega l\'accesso da intervalli IP specifici' },
          { label: 'Imposizione 2FA', text: 'Richiedi l\'autenticazione a due fattori per tutti gli utenti' },
        ]
      },
      {
        title: 'Autenticazione mTLS',
        items: [
          { label: 'CA fidata', text: 'Seleziona la CA che emette e valida i certificati client di accesso mTLS' },
          { label: 'Richiedi certificato client', text: 'Facoltativamente rendi l\'mTLS obbligatorio per l\'interfaccia web, la modifica delle impostazioni mTLS richiede un riavvio del servizio' },
        ]
      },
    ],
    tips: [
      'Abilita la limitazione della frequenza per proteggerti da strumenti di attacco automatizzati',
      'Usa le restrizioni IP per limitare l\'accesso amministrativo alle reti fidate',
    ],
    warnings: [
      'Una politica password troppo restrittiva può frustrare gli utenti',
      'Assicurati sempre che almeno un amministratore possa accedere al sistema prima di abilitare le restrizioni IP',
      'Le impostazioni sensibili alla sicurezza (sessione, blocco, HSTS, URL pubblico, politica password) richiedono admin:settings, i campi sono bloccati per gli operatori',
    ],
  },
  helpGuides: {
    title: 'Impostazioni di sicurezza',
    content: `
## Panoramica

Configurazione di sicurezza a livello di sistema che interessa tutti gli account utente e i modelli di accesso.

## Cifratura delle chiavi private

Cifra tutte le chiavi private di CA e certificati memorizzate nel database con AES-256, protette da un file di chiave master conservato fuori dal database.

- **Stato e contatori**: La sezione mostra se la cifratura è abilitata e quante chiavi sono attualmente **cifrate** rispetto a quelle **non cifrate**
- **Abilita cifratura**: Genera il file della chiave master e cifra tutte le chiavi private memorizzate. Esegui subito il backup del file della chiave: senza di esso, le chiavi cifrate sono perse in modo permanente
- **Disabilita cifratura**: Decifra tutte le chiavi private riportandole alla memorizzazione in chiaro (conferma richiesta)

### Controllo all'avvio

Senza una chiave di cifratura configurata, UCM registra un avviso all'avvio ma continua a funzionare. Due **variabili d'ambiente opt-in** lo trasformano in un errore bloccante:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: rifiuta l'avvio senza una chiave di cifratura del database esplicita (altrimenti i segreti delle integrazioni ricadono su una chiave derivata dal machine id)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: rifiuta l'avvio se la cifratura delle chiavi private non è abilitata

Entrambe accettano \`1\`/\`true\`/\`yes\`/\`on\`. Una chiave non valida è considerata un errore fatale invece di ricadere silenziosamente sul testo in chiaro.

## Politica password

### Requisiti di complessità
- **Lunghezza minima**: Da 8 a 32 caratteri
- **Richiedi maiuscole**: Almeno una lettera maiuscola
- **Richiedi minuscole**: Almeno una lettera minuscola
- **Richiedi numeri**: Almeno una cifra
- **Richiedi caratteri speciali**: Almeno un simbolo

### Scadenza password
Forza gli utenti a cambiare la password dopo un numero stabilito di giorni. Imposta a 0 per disabilitare.

### Cronologia password
Impedisci il riutilizzo delle ultime N password. Gli utenti non possono impostare una password uguale a nessuna delle loro N password precedenti.

## Gestione delle sessioni

### Timeout sessione
Disconnetti automaticamente gli utenti dopo N minuti di inattività. Si applica solo alle sessioni dell'interfaccia web, non alle chiavi API.

### Sessioni simultanee
Limita il numero di sessioni simultanee per utente. Accessi aggiuntivi termineranno la sessione più vecchia.

## Limitazione della frequenza

### Tentativi di accesso
Limita i tentativi di accesso falliti per indirizzo IP entro una finestra temporale. Dopo aver superato il limite, l'IP viene temporaneamente bloccato.

### Durata del blocco
Per quanto tempo un IP viene bloccato dopo aver superato il limite di tentativi di accesso.

## Restrizioni IP

### Lista consentiti
Consenti connessioni solo da IP o intervalli CIDR specificati. Tutti gli altri IP vengono bloccati.

### Lista negati
Blocca IP o intervalli CIDR specifici. Tutti gli altri IP sono consentiti.

> ⚠ Sii estremamente attento con le restrizioni IP. Una configurazione errata può bloccare tutti gli utenti, inclusi gli amministratori. Testa sempre prima con un singolo IP.

## Autenticazione a due fattori

### Imposizione
Richiedi a tutti gli utenti di abilitare il 2FA. Gli utenti che non hanno configurato il 2FA riceveranno una richiesta al prossimo accesso. Un utente con una chiave di sicurezza registrata conferma con essa invece di configurare TOTP.

### Metodi supportati
- **TOTP**: Password monouso basate sul tempo (app di autenticazione)
- **WebAuthn**: Chiavi di sicurezza hardware e biometria

> 💡 Imponi il 2FA almeno per gli account amministratore. Considera di imporlo per tutti gli utenti in ambienti sensibili alla sicurezza.

## Autenticazione mTLS

Consenti agli utenti di accedere con un certificato client invece di una password:

- **CA fidata**: Seleziona la CA che emette e valida i certificati client mTLS
- **Richiedi certificato client**: Facoltativamente rendi l'mTLS obbligatorio per l'interfaccia web
- La modifica delle impostazioni mTLS richiede un riavvio del servizio

## Permessi richiesti

Le impostazioni sensibili alla sicurezza: sessione, blocco, HSTS, URL pubblico e politica password, richiedono il permesso **admin:settings**. Per gli operatori (solo write:settings), questi campi vengono mostrati bloccati; il resto della scheda si salva normalmente.
`
  }
}
