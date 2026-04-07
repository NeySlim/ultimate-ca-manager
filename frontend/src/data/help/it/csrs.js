export default {
  helpContent: {
    title: 'Richieste di firma certificato',
    subtitle: 'Gestisci il flusso di lavoro CSR',
    overview: 'Carica, esamina e firma le richieste di firma certificato. I CSR consentono ai sistemi esterni di richiedere certificati dalle tue CA senza esporre le chiavi private.',
    sections: [
      {
        title: 'Flusso di lavoro',
        items: [
          { label: 'Genera CSR', text: 'Crea un nuovo CSR con coppia di chiavi direttamente in UCM' },
          { label: 'Carica CSR', text: 'Accetta file CSR codificati in PEM o incolla il testo PEM' },
          { label: 'Esamina', text: 'Ispeziona soggetto, SAN, tipo di chiave e firma prima della firma' },
          { label: 'Firma', text: 'Seleziona una CA, il tipo di certificato, imposta il periodo di validità ed emetti il certificato' },
          { label: 'Scarica', text: 'Scarica il CSR originale in formato PEM' },
        ]
      },
      {
        title: 'Schede',
        items: [
          { label: 'In attesa', text: 'CSR in attesa di revisione e firma' },
          { label: 'Cronologia', text: 'CSR precedentemente firmati o rifiutati' },
        ]
      },
    ],
    tips: [
      'I CSR preservano la chiave privata del richiedente — non lascia mai il suo sistema',
      'Puoi aggiungere una chiave privata a un CSR dopo la firma se necessario per l\'esportazione PKCS#12',
      'Usa la modalità Microsoft CA per firmare i CSR tramite AD CS quando sei connesso a una PKI Windows',
    ],
  },
  helpGuides: {
    title: 'Richieste di firma certificato',
    content: `
## Panoramica

Le richieste di firma certificato (CSR) consentono ai sistemi esterni di richiedere certificati senza esporre le loro chiavi private. Il CSR contiene la chiave pubblica e le informazioni sul soggetto; la chiave privata rimane presso il richiedente.

## Schede

### In attesa
CSR in attesa di revisione e firma. I nuovi CSR appaiono qui dopo il caricamento.

### Cronologia
CSR precedentemente firmati o rifiutati, con link ai certificati risultanti.

## Generazione di un CSR

UCM può generare un CSR e una coppia di chiavi direttamente:

1. Clicca **Genera CSR**
2. Compila i campi del Soggetto (CN obbligatorio)
3. Aggiungi Subject Alternative Names se necessario
4. Seleziona il tipo e la dimensione della chiave (RSA 2048/4096, ECDSA P-256/P-384)
5. Clicca **Genera**

Il CSR e la chiave privata vengono creati e memorizzati in UCM. Il CSR appare nella scheda In attesa pronto per la firma.

> 💡 Questo è comodo quando vuoi che UCM gestisca l'intero ciclo di vita — CSR, firma e archiviazione della chiave.

## Caricamento di un CSR

1. Clicca **Carica CSR**
2. Incolla il testo PEM o carica un file PEM/DER
3. UCM valida la firma del CSR e visualizza i dettagli
4. Il CSR appare nella scheda In attesa

## Esame di un CSR

Clicca su un CSR per visualizzare:
- **Soggetto** — CN, O, OU, C, ecc.
- **SAN** — Nomi DNS, indirizzi IP, email
- **Info chiave** — Algoritmo, dimensione, impronta digitale della chiave pubblica
- **Firma** — Algoritmo e validità

## Firma di un CSR

### Firma con CA locale

1. Seleziona un CSR in attesa
2. Clicca **Firma**
3. Scegli la **CA firmataria** (deve avere una chiave privata)
4. Seleziona il **tipo di certificato** (server, client, firma codice, email)
5. Imposta il **periodo di validità** in giorni
5. Facoltativamente applica un template per Key Usage ed estensioni
6. Clicca **Firma**

Il certificato risultante appare nella pagina Certificati.

### Firma con Microsoft CA

Se sono configurate connessioni Microsoft CA, appare una scheda **Microsoft CA** nel modale di firma:

1. Seleziona un CSR in attesa e clicca **Firma**
2. Passa alla scheda **Microsoft CA**
3. Seleziona la **connessione MS CA**
4. Seleziona il **template del certificato** (caricato automaticamente dalla CA)
5. Clicca **Firma**

Se il template richiede l'approvazione del responsabile, UCM traccia la richiesta in sospeso. Controlla il suo stato dal pannello dei dettagli del CSR.

### Iscrizione per conto di (EOBO)

Quando si firma tramite Microsoft CA, puoi iscrivere per conto di un altro utente:

1. Seleziona la connessione MS CA e il template
2. Seleziona **Iscrizione per conto di (EOBO)**
3. I campi **DN iscritto** e **UPN iscritto** si compilano automaticamente dal soggetto del CSR e dall'email SAN
4. Modifica i valori se necessario e clicca **Firma**

> ⚠️ L'EOBO richiede un certificato di agente di iscrizione configurato sul server AD CS e il template deve consentire l'iscrizione per conto di altri utenti.

## Aggiunta di una chiave privata

Dopo la firma, puoi allegare una chiave privata al certificato per l'esportazione PKCS#12. Clicca **Aggiungi chiave** sul certificato firmato.

> 💡 Questo è utile quando il richiedente invia sia il CSR che la chiave in modo sicuro.

## Eliminazione dei CSR

L'eliminazione rimuove il CSR da UCM. Se il CSR è già stato firmato, il certificato risultante non viene influenzato.
`
  }
}
