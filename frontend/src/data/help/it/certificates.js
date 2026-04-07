export default {
  helpContent: {
    title: 'Certificati',
    subtitle: 'Emetti, gestisci e monitora i certificati',
    overview: 'Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati dalle tue CA, importa quelli esistenti, monitora le date di scadenza e gestisci rinnovi e revoche.',
    sections: [
      {
        title: 'Stato del certificato',
        definitions: [
          { term: 'Valido', description: 'Entro il periodo di validità e non revocato' },
          { term: 'In scadenza', description: 'Scadrà entro 30 giorni' },
          { term: 'Scaduto', description: 'Oltre la data "Non dopo"' },
          { term: 'Revocato', description: 'Esplicitamente revocato (pubblicato nella CRL)' },
          { term: 'Orfano', description: 'La CA emittente non esiste più nel sistema' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Emetti', text: 'Crea un nuovo certificato firmato da una delle tue CA' },
          { label: 'Importa', text: 'Importa un certificato esistente (PEM, DER o PKCS#12)' },
          { label: 'Rinnova', text: 'Riemetti con lo stesso soggetto e un nuovo periodo di validità' },
          { label: 'Revoca', text: 'Segna come revocato con un motivo — apparirà nella CRL' },
          { label: 'Rimuovi sospensione', text: 'Riattiva un certificato revocato con motivo "Sospensione certificato" — ripristina lo stato valido' },
          { label: 'Revoca e sostituisci', text: 'Revoca e riemetti immediatamente un sostituto' },
          { label: 'Esporta', text: 'Scarica in formato PEM, DER o PKCS#12' },
          { label: 'Confronta', text: 'Confronto affiancato di due certificati' },
        ]
      },
    ],
    tips: [
      'Aggiungi la stella ⭐ ai certificati importanti per inserirli nella lista dei preferiti',
      'Usa i filtri per trovare rapidamente i certificati per stato, CA o testo di ricerca',
      'Il rinnovo preserva lo stesso soggetto ma genera una nuova coppia di chiavi',
    ],
    warnings: [
      'La revoca è generalmente permanente — tranne per "Sospensione certificato" che può essere rimossa',
      'L\'eliminazione di un certificato lo rimuove da UCM ma non lo revoca',
    ],
  },
  helpGuides: {
    title: 'Certificati',
    content: `
## Panoramica

Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati, importa quelli esistenti, monitora le date di scadenza, gestisci rinnovi e revoche.

## Stato del certificato

- **Valido** — Entro il periodo di validità e non revocato
- **In scadenza** — Scadrà entro 30 giorni (configurabile)
- **Scaduto** — Oltre la data "Non dopo"
- **Revocato** — Esplicitamente revocato, pubblicato nella CRL
- **Orfano** — La CA emittente non esiste più in UCM

## Emissione di un certificato

1. Clicca **Emetti certificato**
2. Seleziona la **CA firmataria** (deve avere una chiave privata)
3. Compila il Soggetto (CN è obbligatorio, altri campi opzionali)
4. Aggiungi Subject Alternative Names (SAN): nomi DNS, IP, email
5. Scegli il tipo e la dimensione della chiave
6. Imposta il periodo di validità
7. Facoltativamente applica un **Template** per precompilare le impostazioni
8. Clicca **Emetti**

### Utilizzo dei template
I template precompilano Key Usage, Extended Key Usage, valori predefiniti del soggetto e validità. Seleziona un template prima di compilare il modulo per risparmiare tempo.

## Importazione di certificati

Formati supportati:
- **PEM** — Certificati singoli o in bundle
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificato + chiave + catena (password richiesta)
- **PKCS#7 (P7B)** — Catena di certificati senza chiavi

## Rinnovo di un certificato

Il rinnovo crea un nuovo certificato con:
- Stesso Soggetto e SAN
- Nuova coppia di chiavi (generata automaticamente)
- Nuovo periodo di validità
- Nuovo numero di serie

Il certificato originale rimane valido fino alla scadenza o alla revoca.

## Revoca di un certificato

1. Seleziona il certificato → **Revoca**
2. Scegli un motivo di revoca (Compromissione chiave, Compromissione CA, Cambio affiliazione, Sostituzione, Cessazione dell'attività, Sospensione certificato, ecc.)
3. Conferma la revoca

I certificati revocati vengono pubblicati nella CRL alla prossima rigenerazione.

> ⚠ La revoca è generalmente permanente — tranne per **Sospensione certificato** che può essere rimossa.

### Rimozione sospensione

Se un certificato è stato revocato con il motivo **Sospensione certificato**, può essere ripristinato allo stato valido:

1. Apri i dettagli del certificato revocato
2. Il pulsante **Rimuovi sospensione** appare nella barra delle azioni (solo per revoche con Sospensione certificato)
3. Clicca **Rimuovi sospensione** per ripristinare il certificato
4. Il certificato torna allo stato valido, la CRL viene rigenerata e la cache OCSP viene aggiornata

> 💡 La Sospensione certificato è utile per sospensioni temporanee (es. dispositivo smarrito, indagine in corso).

### Revoca e sostituzione
Combina la revoca con la riemissione immediata. Il nuovo certificato eredita lo stesso Soggetto e SAN.

## Esportazione dei certificati

Formati di esportazione:
- **PEM** — Solo certificato
- **PEM + Catena** — Certificato con catena completa dell'emittente
- **DER** — Formato binario
- **PKCS#12** — Certificato + chiave + catena, protetto da password

## Preferiti

Aggiungi la stella ⭐ ai certificati importanti per aggiungerli ai segnalibri. I preferiti appaiono per primi nelle viste filtrate e sono accessibili dal filtro preferiti.

## Confronto certificati

Seleziona due certificati e clicca **Confronta** per vedere un confronto affiancato di Soggetto, SAN, Key Usage, validità ed estensioni.

## Filtri e ricerca

- **Filtro per stato** — Valido, In scadenza, Scaduto, Revocato, Orfano
- **Filtro per CA** — Mostra i certificati di una CA specifica
- **Ricerca testuale** — Cerca per CN, numero di serie o SAN
- **Ordinamento** — Per nome, data di scadenza, data di creazione, stato
`
  }
}
