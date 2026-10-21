export default {
  helpContent: {
    title: 'Il mio account',
    subtitle: 'Impostazioni personali e sicurezza',
    overview: 'Gestisci il tuo profilo, le impostazioni di sicurezza e le chiavi API. Abilita l\'autenticazione a due fattori e registra chiavi di sicurezza per una protezione avanzata dell\'account.',
    sections: [
      {
        title: 'Profilo',
        items: [
          { label: 'Nome completo', text: 'Il tuo nome visualizzato nell\'applicazione' },
          { label: 'Email', text: 'Utilizzata per le notifiche e il recupero dell\'account' },
          { label: 'Info account', text: 'Data di creazione, ultimo accesso, conteggio totale degli accessi' },
        ]
      },
      {
        title: 'Sicurezza',
        items: [
          { label: 'Password', text: 'Modifica la tua password attuale' },
          { label: '2FA (TOTP)', text: 'Abilita le password monouso basate sul tempo tramite app di autenticazione. Riabilitarlo mentre è attivo viene rifiutato: disabilitalo prima' },
          { label: 'Chiavi di sicurezza', text: 'Registra chiavi WebAuthn/FIDO2 (YubiKey, impronta digitale, ecc.)' },
          { label: 'mTLS', text: 'Gestisci i certificati client per l\'autenticazione TLS reciproca' },
        ]
      },
      {
        title: 'Chiavi API',
        items: [
          { label: 'Crea chiave', text: 'Genera una nuova chiave API con scadenza opzionale' },
          { label: 'Permessi', text: 'Una chiave porta l\'ambito scelto alla creazione, mai più dei tuoi permessi. Una chiave può creare o rigenerare solo una chiave i cui permessi possiede essa stessa' },
          { label: 'Revoca', text: 'Invalida immediatamente una chiave API' },
          { label: 'Utenti disattivati', text: 'Le chiavi API appartenenti a un utente disattivato vengono rifiutate anche se la chiave stessa è ancora valida' },
          { label: 'Solo sessione interattiva', text: 'Le chiavi API, anche quelle ad accesso completo, non possono modificare il tuo profilo, la password, il 2FA, le chiavi di sicurezza, i certificati mTLS o le sessioni, né raggiungere il tuo account tramite le azioni di amministrazione utenti: accedi in modo interattivo' },
        ]
      },
      {
        title: 'Preferenze (sincronizzate lato server)',
        content: 'Lingua, famiglia di tema e modalità sono persistite nel database e ti seguono attraverso browser e dispositivi:',
        items: [
          { label: 'Memorizzato', text: 'In users.preferences (JSON). Nuovi endpoint GET/PUT /api/v2/account/preferences' },
          { label: 'Auto-applicato', text: '/api/v2/auth/verify restituisce le tue preferenze, applicate a ogni caricamento di pagina' },
          { label: 'Browser nuovo', text: 'Login da un nuovo dispositivo o dopo aver pulito i dati del sito → lingua e tema scelti vengono ripristinati' },
        ]
      },

    ],
    tips: [
      'Abilita almeno un secondo fattore (TOTP o chiave di sicurezza) per gli account amministratore',
      'Le chiavi API possono avere una data di scadenza per integrazioni a breve termine',
      'Scansiona il codice QR con qualsiasi app TOTP: Google Authenticator, Authy, 1Password, ecc.',
      'Le chiavi API possono anche essere create senza scadenza per l\'automazione a lungo termine',
      'Le selezioni di filtro su ogni pagina elenco (Certificati, CA, Audit, ecc.) sono persistite automaticamente attraverso i ricaricamenti',
    ],
  },
  helpGuides: {
    title: 'Il mio account',
    content: `
## Panoramica

Gestisci il tuo profilo personale, le impostazioni di sicurezza e le chiavi API.

## Profilo

- **Nome completo**: Il tuo nome visualizzato in UCM
- **Email**: Utilizzata per notifiche, recupero password e registrazione ACME
- **Info account**: Data di creazione, timestamp dell'ultimo accesso, conteggio totale degli accessi

## Sicurezza

### Cambio password
Modifica la tua password attuale. Deve rispettare la politica password del sistema (lunghezza minima, requisiti di complessità).

### Autenticazione a due fattori (TOTP)
Aggiungi una password monouso basata sul tempo utilizzando qualsiasi app di autenticazione:

1. Clicca **Abilita 2FA**
2. Scansiona il codice QR con la tua app di autenticazione (Google Authenticator, Authy, 1Password, ecc.)
3. Inserisci il codice a 6 cifre per confermare
4. Salva i **codici di recupero**: vengono mostrati solo una volta

> ⚠ Se perdi l'accesso all'autenticatore e ai codici di recupero, un amministratore dovrà disabilitare il tuo 2FA.

Per spostare il 2FA su un nuovo autenticatore, disabilitalo prima: riabilitarlo mentre è attivo viene rifiutato.

### Chiavi di sicurezza (WebAuthn/FIDO2)
Registra chiavi di sicurezza hardware o autenticatori biometrici:
- YubiKey
- Lettore di impronte digitali
- Windows Hello
- Touch ID

1. Clicca **Registra chiave di sicurezza**
2. Inserisci un nome per la chiave
3. Segui la richiesta del browser per l'autenticazione
4. La chiave appare nell'elenco delle credenziali registrate

Con il 2FA attivo o imposto, una chiave registrata può anche completare il secondo passaggio di un accesso con password: scegli **Usa una chiave di sicurezza**.

Senza un'app di autenticazione, attiva **Chiave di sicurezza come secondo fattore** nella sezione Autenticazione a due fattori: ogni accesso con password richiede allora una delle tue chiavi, e l'ultima chiave non può essere rimossa finché l'opzione è attiva.

### Certificati mTLS
Gestisci i certificati client per l'autenticazione TLS reciproca:
- Carica un certificato client
- Scarica i tuoi certificati registrati
- Elimina i vecchi certificati

## Chiavi API

### Creazione di una chiave API
1. Clicca **Crea chiave API**
2. Inserisci un **nome** (descrittivo, es. "Pipeline CI/CD")
3. Facoltativamente imposta una **data di scadenza**
4. Clicca **Crea**
5. Copia immediatamente la chiave: viene mostrata solo una volta

### Utilizzo delle chiavi API
Includi la chiave nell'header \`X-API-Key\`:

\`\`\`
X-API-Key: <la-tua-chiave-api>
\`\`\`

Oppure inviala come token bearer: \`Authorization: Bearer <la-tua-chiave-api>\`.

### Permessi
Ogni chiave porta l'ambito scelto alla creazione (**Accesso completo**, **Solo lettura**, **Lettura e scrittura**, **Solo certificati**) e mai più accesso del tuo account. Una chiave può creare o rigenerare solo una chiave i cui permessi possiede essa stessa.

Le chiavi API, anche quelle ad accesso completo, non possono modificare il tuo profilo, la password, il 2FA, le chiavi di sicurezza, i certificati mTLS o le sessioni, né raggiungere il tuo account tramite le azioni di amministrazione utenti: questi richiedono una sessione interattiva.

### Revoca delle chiavi
Clicca **Elimina** per invalidare immediatamente una chiave API. Le sessioni attive che utilizzano la chiave verranno terminate.

> 💡 Usa chiavi API a breve scadenza con date di scadenza per CI/CD e automazione.
`
  }
}
