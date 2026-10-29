export default {
  helpContent: {
    title: 'Moduli di sicurezza hardware',
    subtitle: 'Archiviazione esterna delle chiavi',
    overview: 'Integrazione con moduli di sicurezza hardware per l\'archiviazione sicura delle chiavi private. Supporto per PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS e OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Provider supportati',
        definitions: [
          { term: 'PKCS#11', description: 'Interfaccia HSM standard del settore (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM basato su cloud di Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Archiviazione chiavi gestita di Microsoft Azure' },
          { term: 'Google KMS', description: 'Servizio di gestione chiavi di Google Cloud' },
          { term: 'OpenBao / Vault Transit', description: 'OpenBao o Vault Transit Secrets Engine per la gestione delle chiavi come servizio' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Aggiungi provider', text: 'Configura la connessione a un HSM (percorso libreria, credenziali, slot)' },
          { label: 'Testa connessione', text: 'Verifica che l\'HSM sia raggiungibile e le credenziali siano valide; per un modulo PKCS#11, registra anche ciò che il modulo riporta (libreria, produttore, versioni della libreria e del firmware), mostrato nella pagina del provider' },
          { label: 'Genera chiave', text: 'Crea una nuova coppia di chiavi direttamente sull\'HSM' },
          { label: 'Stato', text: 'Monitora lo stato della connessione del provider' },
          { label: 'Certificazione', text: 'Dichiara la certificazione dell\'HSM: Common Criteria EAL 4+, EUCC high, FIPS 140-3 livello 3, FIPS 140-2 livello 3 o altra. Se vuota, non è dichiarata. Il profilo di conformità eu-acm accetta solo Common Criteria EAL 4+, EUCC high e FIPS 140-3 livello 3 (fino al 31 dicembre 2030) per una CA basata su HSM' },
        ]
      },
      {
        title: 'CA basate su HSM (v2.130+)',
        content: 'Una volta configurato un provider, puoi fissare la chiave privata di una CA a quell\'HSM al momento della creazione:',
        items: [
          { label: 'Toggle Key Storage', text: 'Sul modulo di creazione CA, scegliere Local (cifrato in DB) o HSM. Selezionare provider + label chiave' },
          { label: 'Percorso di firma', text: 'Ogni emissione, firma CRL e firma OCSP di quella CA passa attraverso l\'HSM, la chiave non esce mai' },
          { label: 'Restrizioni di export', text: 'PKCS#12, JKS ed export di sola chiave sono disabilitati per le CA HSM (solo il certificato pubblico / la chain possono essere esportati)' },
          { label: 'CRL & OCSP', text: 'Entrambi funzionano in modo trasparente con le CA HSM (firmati via HSM)' },
          { label: 'Migrazione', text: 'Le CA locali esistenti non possono essere spostate in un HSM dopo la creazione, scegliere alla creazione' },
        ]
      },

    ],
    tips: [
      'Usa SoftHSM per i test prima di implementare un HSM fisico',
      'Le chiavi generate su un HSM non lasciano mai l\'hardware: non possono essere esportate',
      'Testa la connessione prima di utilizzare un provider HSM per la firma CA',
      'Per CA radice di lunga durata in produzione, preferire l\'archiviazione chiave basata su HSM',
    ],
    warnings: [
      'La certificazione dichiarata è un\'affermazione dell\'operatore sull\'HSM: UCM non verifica l\'hardware. I profili allineati a eIDAS la leggono per controllare la protezione della chiave della CA',
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

> 💡 **Docker**: SoftHSM è preinstallato nell'immagine Docker. Al primo avvio, un token predefinito viene inizializzato automaticamente e registrato come provider \`SoftHSM-Default\`: pronto all'uso immediatamente. In modalità FIPS SoftHSM non è un modulo validato: il provider predefinito non viene creato e un provider SoftHSM viene rifiutato, a meno che \`UCM_FIPS_ALLOW_SOFTHSM=1\` non ne consenta uno per i test.

Configurazione:
- **Percorso libreria**: Percorso alla libreria condivisa PKCS#11 (.so/.dll)
- **Slot**: Numero dello slot HSM
- **PIN**: PIN utente per l'autenticazione

### AWS CloudHSM
HSM basato su cloud di Amazon Web Services:
- **Cluster ID**: Identificatore del cluster CloudHSM
- **Etichetta Token**: etichetta del token PKCS#11 di CloudHSM
- **Utente Crypto / Password Crypto**: l'utente crittografico (CU) con cui UCM accede; non serve alcuna chiave di accesso AWS

### Azure Key Vault
Archiviazione chiavi gestita di Microsoft Azure:
- **URL del Vault**: Endpoint di Azure Key Vault
- **Tenant ID**: Tenant Azure AD
- **Client ID/Secret**: Credenziali del service principal

### Google Cloud KMS
Servizio di gestione chiavi di Google Cloud:
- **Progetto**: ID progetto GCP
- **Posizione**: Posizione del key ring KMS
- **Key Ring**: Nome del key ring
- **Credenziali**: File JSON della chiave del service account

### OpenBao / Vault Transit
OpenBao o HashiCorp Vault Transit Secrets Engine. Le chiavi sono gestite da remoto tramite l'API Transit: nessuna libreria PKCS#11 richiesta.

Configurazione:
- **URL**: Indirizzo del server (es. \`https://openbao.example.com:8200\`)
- **Token**: Token di autenticazione
- **Percorso di montaggio**: Punto di montaggio del motore Transit (predefinito: \`transit\`)
- **Namespace**: Namespace opzionale per configurazioni multi-tenant
- **Ignora verifica TLS**: Ignora la verifica del certificato TLS (per certificati autofirmati)

Tipi di chiave supportati:
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- AES-256-GCM (simmetrico)

> 💡 OpenBao è un fork comunitario di HashiCorp Vault. UCM funziona con entrambi.

## Gestione dei provider

### Aggiunta di un provider
1. Clicca **Aggiungi provider**
2. Seleziona il **tipo di provider**
3. Inserisci i dettagli della connessione
4. Clicca **Testa connessione** per verificare
5. Clicca **Salva**

### Test della connessione
Testa sempre la connessione dopo aver creato o modificato un provider. UCM verifica che possa comunicare con l'HSM e autenticarsi. Per un modulo PKCS#11, il test registra anche ciò che il modulo riporta (libreria, produttore, versioni della libreria e del firmware), mostrato nella pagina del provider.

### Stato del provider
Ogni provider mostra un indicatore di stato della connessione:
- **Connesso**: L'HSM è raggiungibile e autenticato
- **Disconnesso**: Impossibile raggiungere l'HSM
- **Errore**: Problema di autenticazione o configurazione

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
