export default {
  helpContent: {
    title: 'Controllo degli accessi basato sui ruoli',
    subtitle: 'Gestione granulare dei permessi',
    overview: 'Definisci ruoli personalizzati con permessi granulari. I ruoli di sistema (Admin, Operator, Auditor, Viewer) sono integrati. I ruoli personalizzati ti permettono di controllare esattamente quali operazioni ogni utente può eseguire.',
    sections: [
      {
        title: 'Ruoli di sistema',
        definitions: [
          { term: 'Admin', description: 'Accesso completo a tutte le funzionalità e impostazioni' },
          { term: 'Operator', description: 'Può gestire certificati e CA ma non le impostazioni di sistema' },
          { term: 'Auditor', description: 'Accesso in sola lettura a tutti i dati operativi per conformità e audit' },
          { term: 'Viewer', description: 'Accesso di base in sola lettura a certificati, CA e template' },
        ]
      },
      {
        title: 'Ruoli personalizzati',
        items: [
          { label: 'Crea ruolo', text: 'Definisci un nuovo ruolo con nome e descrizione' },
          { label: 'Matrice dei permessi', text: 'Seleziona/deseleziona i permessi per categoria (CA, Certificati, Utenti, ecc.)' },
          { label: 'Copertura', text: 'Percentuale visuale dei permessi totali concessi al ruolo' },
          { label: 'Conteggio utenti', text: 'Vedi quanti utenti sono assegnati a ogni ruolo' },
        ]
      },
    ],
    tips: [
      'Segui il principio del privilegio minimo — concedi solo i permessi necessari',
      'I ruoli di sistema non possono essere modificati o eliminati',
      'Attiva/disattiva intere categorie per una configurazione rapida dei ruoli',
    ],
  },
  helpGuides: {
    title: 'Controllo degli accessi basato sui ruoli',
    content: `
## Panoramica

RBAC fornisce una gestione granulare dei permessi. Definisci ruoli personalizzati con permessi specifici e assegnali a utenti o gruppi.

## Ruoli di sistema

Quattro ruoli integrati che non possono essere modificati o eliminati:

- **Admin** — Accesso completo a tutto
- **Operator** — Gestisce certificati, CA, CSR, template. Nessun accesso a impostazioni di sistema, utenti o RBAC
- **Auditor** — Accesso in sola lettura a tutti i dati operativi (certificati, CA, ACME, SCEP, HSM, log di audit, politiche, gruppi) ma non a impostazioni o gestione utenti
- **Viewer** — Accesso di base in sola lettura a certificati, CA, CSR, template e trust store

## Ruoli personalizzati

### Creazione di un ruolo personalizzato
1. Clicca **Crea ruolo**
2. Inserisci un **nome** e una descrizione opzionale
3. Configura i permessi usando la **matrice dei permessi**
4. Clicca **Crea**

### Matrice dei permessi
I permessi sono organizzati per categoria:
- **CA** — Creazione, lettura, aggiornamento, eliminazione, importazione, esportazione
- **Certificati** — Emissione, lettura, revoca, rinnovo, esportazione, eliminazione
- **CSR** — Creazione, lettura, firma, eliminazione
- **Template** — Creazione, lettura, aggiornamento, eliminazione
- **Utenti** — Creazione, lettura, aggiornamento, eliminazione
- **Gruppi** — Creazione, lettura, aggiornamento, eliminazione
- **Impostazioni** — Lettura, aggiornamento
- **Audit** — Lettura, esportazione, pulizia
- **ACME** — Configurazione, gestione account
- **SCEP** — Configurazione, approvazione richieste
- **Trust Store** — Gestione certificati di fiducia
- **HSM** — Gestione provider e chiavi
- **Backup** — Creazione, ripristino

### Attivazione per categoria
Clicca sull'intestazione di una categoria per abilitare/disabilitare tutti i permessi in quella categoria contemporaneamente.

### Indicatore di copertura
Un badge percentuale mostra quanta parte dell'insieme totale dei permessi copre il ruolo. 100% = equivalente ad Admin.

## Assegnazione dei ruoli

I ruoli vengono assegnati:
- **Direttamente** — Nella pagina Utenti, modifica un utente e seleziona un ruolo
- **Tramite gruppi** — Assegna un ruolo a un gruppo; tutti i membri lo ereditano

## Permessi effettivi

I permessi effettivi di un utente sono calcolati come l'unione di:
1. I permessi del ruolo assegnato direttamente
2. Tutti i ruoli dai gruppi a cui appartiene

Prevale la regola più permissiva (modello additivo, senza regole di negazione).

> ⚠ I ruoli di sistema non possono essere modificati o eliminati. Crea ruoli personalizzati per esigenze specifiche.
`
  }
}
