export default {
  helpContent: {
    title: 'Politiche dei certificati',
    subtitle: 'Regole di emissione e applicazione della conformità',
    overview: 'Definisci e gestisci le politiche dei certificati che controllano le regole di emissione, i requisiti delle chiavi, i limiti di validità e i flussi di approvazione. Le politiche vengono valutate in ordine di priorità quando i certificati vengono richiesti.',
    sections: [
      {
        title: 'Operazioni',
        items: [
          { label: 'Emissione', text: 'Il modulo di emissione, la firma CSR e la firma massiva, e i rinnovi eseguiti da un operatore' },
          { label: 'Rinnovo', text: 'Rinnovi da parte di un operatore, singoli o massivi, e dello scheduler, che mette in coda il proprio rinnovo invece di eseguirlo' },
          { label: 'Revoca', text: 'Revoche di certificati e CA intermedie da parte di un operatore (una CA anche dalle politiche limitate a essa); un client ACME non può attendere una decisione, quindi la sua revoca viene rifiutata' },
          { label: 'Più operazioni', text: 'Una politica può governare più operazioni; una senza operazioni (un vecchio tipo rinnovo o revoca, mai applicato) non governa nulla finché non ne scegli' },
        ]
      },
      {
        title: 'Regole',
        items: [
          { label: 'Validità massima', text: 'Durata massima del certificato in giorni' },
          { label: 'Tipi di chiave consentiti', text: 'Limita gli algoritmi e le dimensioni delle chiavi utilizzabili' },
          { label: 'Restrizioni SAN', text: 'Limita il numero di SAN e imponi pattern di nomi DNS' },
          { label: 'Hash di firma consentiti', text: 'SHA-256, SHA-384 o SHA-512; se nessuno è selezionato, tutti sono consentiti. Quando nessuno ha scelto l\'hash, si applica quello predefinito se consentito, altrimenti il più debole tra quelli consentiti. Il modulo di emissione e Crea CA propongono solo i tipi di chiave e gli hash che le policy consentono' },
        ]
      },
      {
        title: 'Flussi di approvazione',
        items: [
          { label: 'Gruppi di approvazione', text: 'Assegna un gruppo di utenti responsabile dell\'approvazione delle richieste' },
          { label: 'Approvatori minimi', text: 'Numero di approvazioni richieste prima dell\'emissione' },
          { label: 'Notifiche', text: "E-mail quando la politica rifiuta un'operazione o la mette in attesa di approvazione; agli indirizzi indicati, altrimenti ai suoi approvatori. Un rifiuto ripetuto viene segnalato una volta all'ora" },
        ]
      },
    ],
    tips: [
      'Numero di priorità più basso = precedenza più alta. Usa 1–10 per le politiche critiche.',
      'Limita le politiche a CA specifiche per un controllo granulare.',
      'Abilita le notifiche per individuare presto le violazioni delle politiche.',
    ],
  },
  helpGuides: {
    title: 'Politiche dei certificati',
    content: `
## Panoramica

Le politiche dei certificati definiscono le regole e i vincoli applicati quando i certificati vengono emessi, rinnovati o revocati. Le politiche vengono valutate in **ordine di priorità** (numero più basso = precedenza più alta) e possono essere limitate a CA specifiche.

## Operazioni

Una politica governa una o più operazioni: il requisito di approvazione e le regole si applicano a quelle.

### Emissione
Il modulo di emissione, la firma CSR e la firma massiva, e i rinnovi eseguiti da un operatore. È la scelta più comune. Controlla i tipi di chiave, i periodi di validità, le restrizioni SAN e se è richiesta l'approvazione.

### Rinnovo
Rinnovi da parte di un operatore, singoli o massivi, e dello scheduler. Con una politica di rinnovo che richiede l'approvazione, lo scheduler mette in coda il rinnovo invece di eseguirlo, e l'approvazione rifirma la chiave detenuta dal server.

### Revoca
Revoche di certificati (singole, massive, dai certificati utente) e di CA intermedie. Limitata dalla CA emittente, dal template e dal pattern DNS; la revoca di una CA è trattenuta anche dalle politiche limitate a quella CA, perché cadono con essa tutti i certificati che ha emesso. Le altre regole non si applicano. Un client ACME non può attendere una decisione: la sua revoca viene rifiutata e lasciata agli operatori. Rimuovere un enrollment mTLS viene rifiutato finché il suo certificato non è revocato, chiunque lo detenga; gli amministratori aggirano il blocco.

Una politica creata prima dell'introduzione delle operazioni conserva ciò che faceva: una politica di emissione resta tale, mentre un tipo rinnovo o revoca, mai applicato, non governa nulla finché non ne scegli le operazioni.

## Configurazione delle regole

### Validità massima
Durata massima del certificato in giorni. Valori comuni:
- **90 giorni**: Automazione a breve durata (stile ACME)
- **397 giorni**: Baseline CA/Browser Forum per TLS pubblico
- **730 giorni**: PKI interna/privata
- **365 giorni**: Firma del codice

### Tipi di chiave consentiti
Limita gli algoritmi e le dimensioni delle chiavi utilizzabili:
- **RSA-2048**: Minimo per la fiducia pubblica
- **RSA-3072**: La dimensione di chiave predefinita per le nuove CA
- **RSA-4096**: Sicurezza superiore, certificati più grandi
- **EC-P256**: Moderno, veloce, raccomandato
- **EC-P384**: Curva ellittica a sicurezza superiore
- **EC-P521**: Sicurezza massima (raramente necessario)

**Hash di firma consentiti** limita l'hash di firma allo stesso modo (SHA-256, SHA-384, SHA-512); se nessuno è selezionato, tutti sono consentiti. Quando nessuno ha scelto l'hash, si applica quello predefinito se consentito, altrimenti il più debole tra quelli consentiti. Il modulo di emissione e Crea CA propongono solo i tipi di chiave e gli hash che le policy consentono.

### Restrizioni SAN
- **Massimo nomi DNS**: Limita il numero di Subject Alternative Names
- **Pattern DNS**: Limita a pattern di dominio specifici (es. \`*.company.com\`)

## Flussi di approvazione

Quando **Richiedi approvazione** è abilitato, l'emissione del certificato viene sospesa fino a quando il numero richiesto di approvatori del gruppo assegnato non ha approvato la richiesta.

### Configurazione
- **Gruppo di approvazione**: Seleziona un gruppo di utenti responsabile delle approvazioni
- **Approvatori minimi**: Numero di approvazioni richieste (es. 2 su 3 membri del gruppo)
- **Notifiche**: e-mail quando la politica rifiuta un'operazione (una regola violata) o la mette in attesa di approvazione. Vengono inviate agli indirizzi di notifica della politica, altrimenti ai suoi approvatori (i membri del suo gruppo di approvazione, o ogni utente che può approvare). Ogni richiesta in attesa viene segnalata una sola volta, con un link; lo stesso rifiuto ripetuto, ad esempio da un client ACME che riprova, una volta all'ora. SMTP deve essere configurato

> 💡 Usa i flussi di approvazione per certificati di alto valore come la firma del codice e i certificati con carattere jolly.

## Sistema di priorità

Le politiche vengono valutate in ordine di priorità. Numeri più bassi hanno precedenza più alta:
- **1–10**: Politiche di sicurezza critiche (firma codice, wildcard)
- **10–20**: Conformità standard (TLS pubblico, PKI interna)
- **20+**: Impostazioni predefinite permissive

Quando più politiche corrispondono a una richiesta di certificato, la politica con la priorità più alta (numero più basso) prevale.

## Ambito

### Tutte le CA
La politica si applica a ogni CA nel sistema. Usa per regole a livello di organizzazione.

### CA specifica
La politica si applica solo ai certificati emessi dalla CA selezionata. Usa per un controllo granulare.

## Politiche predefinite

UCM include 5 politiche predefinite che riflettono le best practice PKI del mondo reale:
- **Firma del codice** (priorità 5): Chiavi robuste, approvazione richiesta
- **Certificati wildcard** (priorità 8): Approvazione richiesta, max 10 SAN
- **TLS server web** (priorità 10): Conforme al CA/B Forum, max 397 giorni
- **Automazione a breve durata** (priorità 15): Stile ACME 90 giorni
- **PKI interna** (priorità 20): 730 giorni, regole flessibili

> 💡 Personalizza o disabilita le politiche predefinite per adattarle ai requisiti della tua organizzazione.
`
  }
}
