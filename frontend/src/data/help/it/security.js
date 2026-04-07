export default {
  helpContent: {
    title: 'Impostazioni di sicurezza',
    subtitle: 'Autenticazione e politiche di accesso',
    overview: 'Configura le politiche password, la gestione delle sessioni, la limitazione della frequenza e la sicurezza di rete. Queste impostazioni si applicano a tutto il sistema e interessano tutti gli account utente.',
    sections: [
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
    ],
    tips: [
      'Abilita la limitazione della frequenza per proteggerti da strumenti di attacco automatizzati',
      'Usa le restrizioni IP per limitare l\'accesso amministrativo alle reti fidate',
    ],
    warnings: [
      'Una politica password troppo restrittiva può frustrare gli utenti',
      'Assicurati sempre che almeno un amministratore possa accedere al sistema prima di abilitare le restrizioni IP',
    ],
  },
  helpGuides: {
    title: 'Impostazioni di sicurezza',
    content: `
## Panoramica

Configurazione di sicurezza a livello di sistema che interessa tutti gli account utente e i modelli di accesso.

## Politica password

### Requisiti di complessità
- **Lunghezza minima** — Da 8 a 32 caratteri
- **Richiedi maiuscole** — Almeno una lettera maiuscola
- **Richiedi minuscole** — Almeno una lettera minuscola
- **Richiedi numeri** — Almeno una cifra
- **Richiedi caratteri speciali** — Almeno un simbolo

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
Richiedi a tutti gli utenti di abilitare il 2FA. Gli utenti che non hanno configurato il 2FA riceveranno una richiesta al prossimo accesso.

### Metodi supportati
- **TOTP** — Password monouso basate sul tempo (app di autenticazione)
- **WebAuthn** — Chiavi di sicurezza hardware e biometria

> 💡 Imponi il 2FA almeno per gli account amministratore. Considera di imporlo per tutti gli utenti in ambienti sensibili alla sicurezza.
`
  }
}
