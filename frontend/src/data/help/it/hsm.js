export default {
  helpContent: {
    title: 'Moduli di sicurezza hardware',
    subtitle: 'Archiviazione esterna delle chiavi',
    overview: 'Integrazione con moduli di sicurezza hardware per l\'archiviazione sicura delle chiavi private. Supporto per PKCS#11, AWS CloudHSM, Azure Key Vault e Google Cloud KMS.',
    sections: [
      {
        title: 'Provider supportati',
        definitions: [
          { term: 'PKCS#11', description: 'Interfaccia HSM standard del settore (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM basato su cloud di Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Archiviazione chiavi gestita di Microsoft Azure' },
          { term: 'Google KMS', description: 'Servizio di gestione chiavi di Google Cloud' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Aggiungi provider', text: 'Configura la connessione a un HSM (percorso libreria, credenziali, slot)' },
          { label: 'Testa connessione', text: 'Verifica che l\'HSM sia raggiungibile e le credenziali siano valide' },
          { label: 'Genera chiave', text: 'Crea una nuova coppia di chiavi direttamente sull\'HSM' },
          { label: 'Stato', text: 'Monitora lo stato della connessione del provider' },
        ]
      },
    ],
    tips: [
      'Usa SoftHSM per i test prima di implementare un HSM fisico',
      'Le chiavi generate su un HSM non lasciano mai l\'hardware — non possono essere esportate',
      'Testa la connessione prima di utilizzare un provider HSM per la firma CA',
    ],
    warnings: [
      'Una configurazione errata del provider HSM può impedire la firma dei certificati',
      'La perdita dell\'accesso all\'HSM significa la perdita dell\'accesso alle chiavi memorizzate su di esso',
    ],
  },
  helpGuides: {
    title: 'Moduli di sicurezza hardware',
    content: `
## Panoramica

I moduli di sicurezza hardware (HSM) forniscono un'archiviazione resistente alla manomissione per le chiavi crittografiche. Le chiavi private memorizzate su un HSM non lasciano mai l'hardware, fornendo il massimo livello di protezione delle chiavi.

## Provider supportati

### PKCS#11
L'interfaccia HSM standard del settore. Dispositivi supportati:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (basato su software, per i test)
- Qualsiasi dispositivo compatibile PKCS#11

> 💡 **Docker**: SoftHSM è preinstallato nell'immagine Docker. Al primo avvio, un token predefinito viene inizializzato automaticamente e registrato come provider \`SoftHSM-Default\` — pronto all'uso immediatamente.

Configurazione:
- **Percorso libreria** — Percorso alla libreria condivisa PKCS#11 (.so/.dll)
- **Slot** — Numero dello slot HSM
- **PIN** — PIN utente per l'autenticazione

### AWS CloudHSM
HSM basato su cloud di Amazon Web Services:
- **Cluster ID** — Identificatore del cluster CloudHSM
- **Regione** — Regione AWS
- **Credenziali** — Chiave di accesso e segreto AWS

### Azure Key Vault
Archiviazione chiavi gestita di Microsoft Azure:
- **URL del Vault** — Endpoint di Azure Key Vault
- **Tenant ID** — Tenant Azure AD
- **Client ID/Secret** — Credenziali del service principal

### Google Cloud KMS
Servizio di gestione chiavi di Google Cloud:
- **Progetto** — ID progetto GCP
- **Posizione** — Posizione del key ring KMS
- **Key Ring** — Nome del key ring
- **Credenziali** — File JSON della chiave del service account

## Gestione dei provider

### Aggiunta di un provider
1. Clicca **Aggiungi provider**
2. Seleziona il **tipo di provider**
3. Inserisci i dettagli della connessione
4. Clicca **Testa connessione** per verificare
5. Clicca **Salva**

### Test della connessione
Testa sempre la connessione dopo aver creato o modificato un provider. UCM verifica che possa comunicare con l'HSM e autenticarsi.

### Stato del provider
Ogni provider mostra un indicatore di stato della connessione:
- **Connesso** — L'HSM è raggiungibile e autenticato
- **Disconnesso** — Impossibile raggiungere l'HSM
- **Errore** — Problema di autenticazione o configurazione

## Gestione delle chiavi

### Generazione delle chiavi
1. Seleziona un provider connesso
2. Clicca **Genera chiave**
3. Scegli l'algoritmo (RSA 2048/4096, ECDSA P-256/P-384)
4. Inserisci un'etichetta/alias per la chiave
5. Clicca **Genera**

La chiave viene creata direttamente sull'HSM. UCM memorizza solo un riferimento.

### Utilizzo delle chiavi HSM
Quando crei una CA, seleziona un provider HSM e una chiave invece di generare una chiave software. Le operazioni di firma della CA vengono eseguite sull'HSM.

> ⚠ Le chiavi generate su un HSM non possono essere esportate. Se perdi l'accesso all'HSM, perdi le chiavi.

> 💡 Usa SoftHSM per lo sviluppo e i test prima di implementare HSM fisici.
`
  }
}
