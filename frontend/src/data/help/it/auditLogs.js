export default {
  helpContent: {
    title: 'Log di audit',
    subtitle: 'Tracciamento attività e conformità',
    overview: 'Traccia di audit completa di tutte le operazioni eseguite in UCM. Monitora chi ha fatto cosa, quando e da dove. Supporta filtri, ricerca, esportazione e verifica dell\'integrità.',
    sections: [
      {
        title: 'Filtri',
        items: [
          { label: 'Tipo di azione', text: 'Filtra per tipo di operazione (crea, aggiorna, elimina, accesso, ecc.)' },
          { label: 'Utente', text: 'Filtra per l\'utente che ha eseguito l\'azione' },
          { label: 'Stato', text: 'Mostra solo le operazioni riuscite o fallite' },
          { label: 'Intervallo date', text: 'Imposta le date da/a per restringere la finestra temporale' },
          { label: 'Ricerca', text: 'Ricerca libera su tutte le voci del log' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Esporta', text: 'Scarica i log in formato JSON o CSV' },
          { label: 'Pulizia', text: 'Elimina i vecchi log con conservazione configurabile (giorni)' },
          { label: 'Verifica integrità', text: 'Controlla l\'integrità della catena dei log per rilevare manomissioni' },
        ]
      },
    ],
    tips: [
      'Esporta i log regolarmente per la conformità e l\'archiviazione',
      'I tentativi di accesso falliti vengono registrati con l\'IP di origine per il monitoraggio della sicurezza',
      'Le voci del log includono lo User Agent per l\'identificazione delle applicazioni client',
    ],
    warnings: [
      'La pulizia dei log è irreversibile — i dati esportati non possono essere reimportati',
    ],
  },
  helpGuides: {
    title: 'Log di audit',
    content: `
## Panoramica

Traccia di audit completa di tutte le operazioni in UCM. Ogni azione — emissione certificato, revoca, accesso utente, modifica impostazione — viene registrata con dettagli su chi, cosa, quando e dove.

## Dettagli delle voci del log

Ogni voce del log registra:
- **Timestamp** — Quando l'azione è avvenuta
- **Utente** — Chi ha eseguito l'azione
- **Azione** — Cosa è stato fatto (crea, aggiorna, elimina, accesso, ecc.)
- **Risorsa** — Cosa è stato interessato (certificato, CA, utente, ecc.)
- **Stato** — Successo o fallimento
- **Indirizzo IP** — IP di origine della richiesta
- **User Agent** — Identificativo dell'applicazione client
- **Dettagli** — Contesto aggiuntivo (messaggi di errore, valori modificati)

## Filtri

### Per tipo di azione
Filtra per categoria di operazione:
- Operazioni certificato (emissione, revoca, rinnovo, esportazione)
- Operazioni CA (creazione, importazione, eliminazione)
- Operazioni utente (accesso, uscita, creazione, aggiornamento)
- Operazioni di sistema (modifica impostazioni, backup, ripristino)

### Per utente
Mostra solo le azioni eseguite da un utente specifico.

### Per stato
- **Successo** — Operazioni completate con successo
- **Fallito** — Operazioni fallite (errori di autenticazione, permesso negato, errori)

### Per intervallo date
Imposta le date **Da** e **A** per restringere la finestra temporale.

### Ricerca testuale
Ricerca libera su tutti i campi del log.

## Esportazione

Esporta i log filtrati in:
- **JSON** — Leggibile dalle macchine, include tutti i campi
- **CSV** — Compatibile con i fogli di calcolo, include i campi principali

Le esportazioni includono solo i risultati attualmente filtrati.

## Pulizia

Elimina i vecchi log in base al periodo di conservazione:
1. Clicca **Pulizia**
2. Imposta il periodo di conservazione in giorni
3. Conferma la pulizia

> ⚠ La pulizia dei log è irreversibile. Esporta i log importanti prima dell'eliminazione.

## Verifica dell'integrità

Clicca **Verifica integrità** per controllare la catena dei log di audit. UCM utilizza il concatenamento di hash per rilevare se delle voci del log sono state manomesse o eliminate.

## Inoltro syslog

Configura l'inoltro syslog remoto in **Impostazioni → Audit** per inviare gli eventi del log a un server SIEM o syslog esterno in tempo reale.
`
  }
}
