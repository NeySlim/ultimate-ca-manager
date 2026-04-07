export default {
  helpContent: {
    title: 'Modelli di certificato',
    subtitle: 'Profili certificato riutilizzabili',
    overview: 'Definisci profili certificato riutilizzabili con campi soggetto, key usage, extended key usage, periodi di validità e altre estensioni preconfigurati. Applica i modelli durante l\'emissione o la firma dei certificati.',
    sections: [
      {
        title: 'Tipi di modello',
        definitions: [
          { term: 'End-Entity', description: 'Per certificati server, client, firma del codice e email' },
          { term: 'CA', description: 'Per la creazione di Autorità di Certificazione intermedie' },
        ]
      },
      {
        title: 'Funzionalità',
        items: [
          { label: 'Valori predefiniti soggetto', text: 'Precompila Organizzazione, OU, Paese, Stato, Città' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, ecc.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Validità', text: 'Periodo di validità predefinito in giorni' },
          { label: 'Duplica', text: 'Clona un modello esistente e modificalo' },
          { label: 'Importa/Esporta', text: 'Condividi modelli come file JSON tra istanze UCM' },
        ]
      },
    ],
    tips: [
      'Crea modelli separati per server TLS, client e firma del codice',
      'Usa l\'azione Duplica per creare rapidamente varianti di un modello',
    ],
  },
  helpGuides: {
    title: 'Modelli di certificato',
    content: `
## Panoramica

I modelli definiscono profili certificato riutilizzabili. Invece di configurare manualmente Key Usage, Extended Key Usage, validità e campi soggetto ogni volta, applica un modello per precompilare tutto.

## Tipi di modello

### Modelli End-Entity
Per certificati server, certificati client, firma del codice e protezione email. Questi modelli tipicamente impostano:
- **Key Usage** — Digital Signature, Key Encipherment
- **Extended Key Usage** — Server Auth, Client Auth, Code Signing, Email Protection

### Modelli CA
Per la creazione di CA intermedie. Questi impostano:
- **Key Usage** — Certificate Sign, CRL Sign
- **Basic Constraints** — CA:TRUE, lunghezza del percorso opzionale

## Creazione di un modello

1. Clicca **Crea modello**
2. Inserisci un **nome** e una descrizione opzionale
3. Seleziona il **tipo** di modello (End-Entity o CA)
4. Configura i **valori predefiniti del soggetto** (O, OU, C, ST, L)
5. Seleziona i flag **Key Usage**
6. Seleziona i valori **Extended Key Usage**
7. Imposta il **periodo di validità predefinito** in giorni
8. Clicca **Crea**

## Utilizzo dei modelli

Quando emetti un certificato o firmi un CSR, seleziona un modello dal menu a tendina. Il modello precompila:
- Campi soggetto (puoi sovrascriverli)
- Key Usage e Extended Key Usage
- Periodo di validità

## Duplicazione dei modelli

Clicca **Duplica** per creare una copia di un modello esistente. Modifica la copia senza influire sull'originale.

## Importa ed Esporta

### Esporta
Esporta i modelli come JSON per condividerli tra istanze UCM.

### Importa
Importa da:
- **File JSON** — Carica un file JSON del modello
- **Incolla JSON** — Incolla il JSON direttamente nell'area di testo

## Esempi comuni di modelli

### Server TLS
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Validità: 365 giorni

### Autenticazione Client
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Validità: 365 giorni

### Firma del codice
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Validità: 365 giorni
`
  }
}
