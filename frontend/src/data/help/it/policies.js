export default {
  helpContent: {
    title: 'Politiche dei certificati',
    subtitle: 'Regole di emissione e applicazione della conformità',
    overview: 'Definisci e gestisci le politiche dei certificati che controllano le regole di emissione, i requisiti delle chiavi, i limiti di validità e i flussi di approvazione. Le politiche vengono valutate in ordine di priorità quando i certificati vengono richiesti.',
    sections: [
      {
        title: 'Tipi di politica',
        items: [
          { label: 'Emissione', text: 'Regole applicate quando vengono creati nuovi certificati' },
          { label: 'Rinnovo', text: 'Regole applicate quando i certificati vengono rinnovati' },
          { label: 'Revoca', text: 'Regole applicate quando i certificati vengono revocati' },
        ]
      },
      {
        title: 'Regole',
        items: [
          { label: 'Validità massima', text: 'Durata massima del certificato in giorni' },
          { label: 'Tipi di chiave consentiti', text: 'Limita gli algoritmi e le dimensioni delle chiavi utilizzabili' },
          { label: 'Restrizioni SAN', text: 'Limita il numero di SAN e imponi pattern di nomi DNS' },
        ]
      },
      {
        title: 'Flussi di approvazione',
        items: [
          { label: 'Gruppi di approvazione', text: 'Assegna un gruppo di utenti responsabile dell\'approvazione delle richieste' },
          { label: 'Approvatori minimi', text: 'Numero di approvazioni richieste prima dell\'emissione' },
          { label: 'Notifiche', text: 'Avvisa gli amministratori quando le politiche vengono violate' },
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

## Tipi di politica

### Politiche di emissione
Regole applicate quando vengono creati nuovi certificati. Questo è il tipo più comune. Controlla i tipi di chiave, i periodi di validità, le restrizioni SAN e se è richiesta l'approvazione.

### Politiche di rinnovo
Regole applicate quando i certificati vengono rinnovati. Possono imporre una validità più breve al rinnovo o richiedere una nuova approvazione.

### Politiche di revoca
Regole applicate quando i certificati vengono revocati. Possono richiedere l'approvazione prima della revoca di certificati critici.

## Configurazione delle regole

### Validità massima
Durata massima del certificato in giorni. Valori comuni:
- **90 giorni** — Automazione a breve durata (stile ACME)
- **397 giorni** — Baseline CA/Browser Forum per TLS pubblico
- **730 giorni** — PKI interna/privata
- **365 giorni** — Firma del codice

### Tipi di chiave consentiti
Limita gli algoritmi e le dimensioni delle chiavi utilizzabili:
- **RSA-2048** — Minimo per la fiducia pubblica
- **RSA-4096** — Sicurezza superiore, certificati più grandi
- **EC-P256** — Moderno, veloce, raccomandato
- **EC-P384** — Curva ellittica a sicurezza superiore
- **EC-P521** — Sicurezza massima (raramente necessario)

### Restrizioni SAN
- **Massimo nomi DNS** — Limita il numero di Subject Alternative Names
- **Pattern DNS** — Limita a pattern di dominio specifici (es. \`*.company.com\`)

## Flussi di approvazione

Quando **Richiedi approvazione** è abilitato, l'emissione del certificato viene sospesa fino a quando il numero richiesto di approvatori del gruppo assegnato non ha approvato la richiesta.

### Configurazione
- **Gruppo di approvazione** — Seleziona un gruppo di utenti responsabile delle approvazioni
- **Approvatori minimi** — Numero di approvazioni richieste (es. 2 su 3 membri del gruppo)
- **Notifiche** — Avvisa gli amministratori quando le politiche vengono violate

> 💡 Usa i flussi di approvazione per certificati di alto valore come la firma del codice e i certificati con carattere jolly.

## Sistema di priorità

Le politiche vengono valutate in ordine di priorità. Numeri più bassi hanno precedenza più alta:
- **1–10** — Politiche di sicurezza critiche (firma codice, wildcard)
- **10–20** — Conformità standard (TLS pubblico, PKI interna)
- **20+** — Impostazioni predefinite permissive

Quando più politiche corrispondono a una richiesta di certificato, la politica con la priorità più alta (numero più basso) prevale.

## Ambito

### Tutte le CA
La politica si applica a ogni CA nel sistema. Usa per regole a livello di organizzazione.

### CA specifica
La politica si applica solo ai certificati emessi dalla CA selezionata. Usa per un controllo granulare.

## Politiche predefinite

UCM include 5 politiche predefinite che riflettono le best practice PKI del mondo reale:
- **Firma del codice** (priorità 5) — Chiavi robuste, approvazione richiesta
- **Certificati wildcard** (priorità 8) — Approvazione richiesta, max 10 SAN
- **TLS server web** (priorità 10) — Conforme al CA/B Forum, max 397 giorni
- **Automazione a breve durata** (priorità 15) — Stile ACME 90 giorni
- **PKI interna** (priorità 20) — 730 giorni, regole flessibili

> 💡 Personalizza o disabilita le politiche predefinite per adattarle ai requisiti della tua organizzazione.
`
  }
}
