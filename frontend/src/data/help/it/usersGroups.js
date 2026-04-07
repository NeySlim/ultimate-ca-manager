export default {
  helpContent: {
    title: 'Utenti e gruppi',
    subtitle: 'Gestione identità e accessi',
    overview: 'Gestisci gli account utente e le appartenenze ai gruppi. Assegna ruoli per controllare l\'accesso alle funzionalità UCM. I gruppi consentono la gestione dei permessi in blocco per i team.',
    sections: [
      {
        title: 'Utenti',
        items: [
          { label: 'Crea utente', text: 'Aggiungi un nuovo utente con nome utente, email e password iniziale' },
          { label: 'Ruoli', text: 'Assegna ruoli di sistema o personalizzati per controllare i permessi' },
          { label: 'Stato', text: 'Abilita o disabilita gli account utente' },
          { label: 'Reset password', text: 'Reimposta la password di un utente (azione amministratore)' },
          { label: 'Chiavi API', text: 'Gestisci le chiavi API per utente per l\'accesso programmatico' },
        ]
      },
      {
        title: 'Gruppi',
        items: [
          { label: 'Crea gruppo', text: 'Definisci un gruppo e assegna i membri' },
          { label: 'Ereditarietà ruoli', text: 'I gruppi possono ereditare ruoli — tutti i membri ottengono i permessi del gruppo' },
          { label: 'Gestione membri', text: 'Aggiungi o rimuovi utenti dai gruppi' },
        ]
      },
    ],
    tips: [
      'Usa i gruppi per gestire i permessi dei team piuttosto che dei singoli utenti',
      'Gli utenti disabilitati non possono accedere ma i loro dati vengono preservati',
    ],
    warnings: [
      'L\'eliminazione di un utente è permanente — considera di disabilitarlo invece',
    ],
  },
  helpGuides: {
    title: 'Utenti e gruppi',
    content: `
## Panoramica

Gestisci gli account utente, i gruppi e le assegnazioni dei ruoli. Gli utenti si autenticano a UCM tramite password, SSO, WebAuthn o mTLS. I gruppi consentono la gestione dei permessi in blocco.

## Scheda Utenti

### Creazione di un utente
1. Clicca **Crea utente**
2. Inserisci il **nome utente** (univoco, non modificabile successivamente)
3. Inserisci l'**email** (utilizzata per notifiche e recupero)
4. Imposta una **password iniziale**
5. Seleziona un **ruolo** (Admin, Operator, Auditor, Viewer o personalizzato)
6. Clicca **Crea**

### Stato dell'utente
- **Attivo** — Può accedere ed eseguire azioni
- **Disabilitato** — Non può accedere, i dati vengono preservati

Cambia lo stato di un utente senza eliminare il suo account.

### Reset password
Gli amministratori possono reimpostare la password di qualsiasi utente. L'utente verrà invitato a cambiarla al prossimo accesso.

### Chiavi API
Ogni utente può avere più chiavi API per l'accesso programmatico. Le chiavi API ereditano i permessi del ruolo dell'utente. Vedi la pagina Account per gestire le tue chiavi.

## Scheda Gruppi

### Creazione di un gruppo
1. Clicca **Crea gruppo**
2. Inserisci un **nome** e una descrizione opzionale
3. Assegna un **ruolo** (i membri del gruppo ereditano questo ruolo)
4. Clicca **Crea**

### Gestione dei membri
- Clicca su un gruppo per vederne i membri
- Usa il **pannello di trasferimento** per aggiungere/rimuovere utenti
- Gli utenti possono appartenere a più gruppi

### Ereditarietà dei ruoli
I permessi effettivi di un utente sono l'**unione** di:
- Il ruolo assegnato direttamente
- Tutti i ruoli dai gruppi a cui appartiene

## Ruoli

### Ruoli di sistema
- **Admin** — Accesso completo a tutte le funzionalità
- **Operator** — Può gestire certificati, CA, CSR ma non le impostazioni di sistema
- **Auditor** — Accesso in sola lettura a tutti i dati operativi per conformità e audit
- **Viewer** — Accesso in sola lettura a certificati, CA e template

### Ruoli personalizzati
Crea ruoli con permessi granulari nella pagina **RBAC**.

> 💡 Usa i gruppi per gestire i permessi dei team piuttosto che assegnare ruoli ai singoli utenti.
`
  }
}
