export default {
  helpContent: {
    title: 'Certificati utente',
    subtitle: 'Gestisci i certificati client mTLS',
    overview: 'Gestione dedicata dei certificati client mTLS iscritti tramite la pagina Account. Visualizza, esporta, revoca ed elimina i certificati emessi agli utenti per l\'autenticazione TLS reciproca.',
    sections: [
      {
        title: 'Stato del certificato',
        definitions: [
          { term: 'Valido', description: 'Entro il periodo di validità e non revocato' },
          { term: 'In scadenza', description: 'Scadrà entro 30 giorni' },
          { term: 'Scaduto', description: 'Oltre la data "Non dopo"' },
          { term: 'Revocato', description: 'Esplicitamente revocato da un operatore o amministratore' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Esporta', text: 'Scarica come PEM (con chiave e catena) o PKCS#12 (protetto da password)' },
          { label: 'Revoca', text: 'Revoca con una motivazione, il certificato apparirà nella CRL' },
          { label: 'Elimina', text: 'Rimuovi da UCM il certificato e la sua associazione all\'utente' },
        ]
      },
      {
        title: 'Permessi',
        items: [
          { label: 'Viewer', text: 'Possono vedere solo i propri certificati' },
          { label: 'Operatori', text: 'Possono visualizzare, esportare, revocare ed eliminare tutti i certificati utente; esportare la chiave privata del certificato di un altro utente richiede read:private_keys, che il ruolo non ha' },
          { label: 'Amministratori', text: 'Accesso completo, chiavi private incluse' },
          { label: 'Auditor', text: 'Possono visualizzare ed esportare i certificati, senza la loro chiave privata' },
        ]
      },
    ],
    tips: [
      'Iscrivi nuovi certificati mTLS da Account → scheda mTLS',
      'I certificati sono memorizzati e gestiti da UCM come qualsiasi altro certificato',
      'Usa la barra delle statistiche per filtrare rapidamente per stato',
      'Fai clic su una riga per vedere i dettagli completi del certificato nell\'ispettore',
    ],
    warnings: [
      'La revoca di un certificato utente impedisce immediatamente l\'accesso mTLS con quel certificato',
      'L\'eliminazione rimuove il certificato in modo permanente: non può essere recuperato',
    ],
  },
  helpGuides: {
    title: 'Certificati utente',
    content: `
## Panoramica

La pagina Certificati utente gestisce i certificati client mTLS iscritti tramite la scheda **Account → mTLS**. A differenza dei certificati normali, questi sono specificamente legati agli account utente per l'autenticazione TLS reciproca.

I certificati qui presenti sono interamente gestiti da UCM: sono memorizzati nel database con le chiavi private e possono essere esportati, revocati o eliminati in qualsiasi momento.

## Iscrivere un certificato

1. Vai su **Account → scheda mTLS**
2. Fai clic su **Iscrivi certificato**
3. Il sistema genera una coppia di chiavi ed emette un certificato client firmato dalla tua CA mTLS
4. Il certificato appare in questa pagina e può essere usato per l'accesso mTLS

## Stato del certificato

- **Valido**: Entro il periodo di validità e non revocato
- **In scadenza**: Scadrà entro 30 giorni
- **Scaduto**: Oltre la data "Non dopo"
- **Revocato**: Esplicitamente revocato, pubblicato nella CRL

## Esportare un certificato

1. Seleziona un certificato → **Esporta**
2. Scegli il formato:
   - **PEM**: Certificato + chiave privata + catena CA in formato testo
   - **PKCS#12**: Pacchetto binario, protetto da password (min. 8 caratteri)
3. Fai clic su **Scarica**

Il file esportato può essere importato in browser, sistemi operativi o client API per l'autenticazione mTLS.

> ⚠ La password PKCS#12 deve contenere almeno 8 caratteri.

## Revocare un certificato

1. Seleziona un certificato → **Revoca**
2. Scegli una motivazione di revoca:
   - Compromissione della chiave
   - Cambio di affiliazione
   - Sostituito
   - Cessazione dell'attività
   - Non specificata
3. Conferma la revoca

> ⚠ La revoca di un certificato impedisce immediatamente l'accesso mTLS con quel certificato. La revoca è permanente.

## Eliminare un certificato

L'eliminazione rimuove sia il certificato sia l'associazione utente-certificato. Solo amministratori e operatori possono eliminare.

> ⚠ L'eliminazione è permanente e non può essere annullata.

## Permessi

| Ruolo | Visualizza | Esporta | Revoca | Elimina |
|------|------|--------|--------|--------|
| Amministratore | Tutti | Tutti | Tutti | Tutti |
| Operatore | Tutti | Tutti (la chiave privata di un altro utente richiede read:private_keys) | Tutti | Tutti |
| Auditor | Tutti | Solo il certificato, senza chiave privata | ✗ | ✗ |
| Viewer | Solo i propri | Solo i propri | ✗ | ✗ |

### Permessi richiesti

- **read:user_certificates**: Visualizzare l'elenco e i dettagli dei certificati
- **write:user_certificates**: Revocare i certificati
- **delete:user_certificates**: Eliminare i certificati

> 💡 Iscrivi i nuovi certificati mTLS dalla pagina Account. Questa pagina serve a gestire i certificati esistenti.
`
  }
}
