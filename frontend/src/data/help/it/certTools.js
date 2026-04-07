export default {
  helpContent: {
    title: 'Strumenti certificati',
    subtitle: 'Decodifica, converti e verifica i certificati',
    overview: 'Una suite di strumenti per lavorare con certificati, CSR e chiavi. Decodifica i certificati per ispezionarne i contenuti, converti tra formati, controlla gli endpoint SSL remoti e verifica la corrispondenza delle chiavi.',
    sections: [
      {
        title: 'Strumenti disponibili',
        items: [
          { label: 'Verifica SSL', text: 'Connettiti a un host remoto e ispeziona la sua catena di certificati SSL/TLS' },
          { label: 'Decodificatore CSR', text: 'Incolla un CSR in formato PEM per visualizzare soggetto, SAN e informazioni sulla chiave' },
          { label: 'Decodificatore certificati', text: 'Incolla un certificato in formato PEM per ispezionare tutti i campi' },
          { label: 'Corrispondenza chiavi', text: 'Verifica che un certificato, un CSR e una chiave privata appartengano allo stesso insieme' },
          { label: 'Convertitore', text: 'Converti tra formati PEM, DER, PKCS#12 e PKCS#7' },
        ]
      },
      {
        title: 'Dettagli convertitore',
        items: [
          'Conversione PEM ↔ DER',
          'PEM → PKCS#12 con password e catena completa',
          'PKCS#12 → estrazione PEM',
          'PEM → PKCS#7 (P7B) raggruppamento catena',
        ]
      },
    ],
    tips: [
      'La Verifica SSL supporta porte personalizzate — usala per controllare qualsiasi servizio TLS',
      'La Corrispondenza chiavi confronta gli hash del modulo per verificare le coppie corrispondenti',
      'Il Convertitore preserva la catena completa dei certificati quando crea file PKCS#12',
    ],
  },
  helpGuides: {
    title: 'Strumenti certificati',
    content: `
## Panoramica

Un toolkit per ispezionare, convertire e verificare i certificati senza uscire da UCM.

## Verifica SSL

Ispeziona il certificato SSL/TLS di un server remoto:

1. Inserisci l'**hostname** (es. \`google.com\`)
2. Facoltativamente cambia la **porta** (predefinita: 443)
3. Clicca **Verifica**

I risultati includono:
- Soggetto e emittente del certificato
- Date di validità
- SAN (Subject Alternative Names)
- Tipo e dimensione della chiave
- Catena completa dei certificati
- Versione del protocollo TLS

## Decodificatore CSR

Analizza e visualizza il contenuto del CSR:

1. Incolla un CSR in formato PEM
2. Clicca **Decodifica**

Mostra: Soggetto, SAN, algoritmo della chiave, dimensione della chiave, algoritmo di firma.

## Decodificatore certificati

Analizza e visualizza i dettagli del certificato:

1. Incolla un certificato in formato PEM
2. Clicca **Decodifica**

Mostra: Soggetto, Emittente, SAN, validità, numero di serie, key usage, estensioni, impronte digitali.

## Corrispondenza chiavi

Verifica che un certificato, un CSR e una chiave privata appartengano allo stesso insieme:

1. Incolla il **certificato** PEM
2. Incolla la **chiave privata** PEM (opzionalmente crittografata — fornisci la password)
3. Facoltativamente incolla un **CSR** PEM
4. Clicca **Verifica corrispondenza**

UCM confronta gli hash del modulo (RSA) o della chiave pubblica (EC). Una corrispondenza conferma che formano una coppia valida.

## Convertitore

Converti tra formati di certificati e chiavi:

### PEM → DER
Converte un PEM codificato in Base64 nel formato binario DER.

### PEM → PKCS#12
Crea un file P12/PFX protetto da password da:
- Certificato PEM
- Chiave privata PEM
- Certificati della catena opzionali
- Password per il file P12

### PKCS#12 → PEM
Estrae certificato, chiave e catena da un file P12:
- Carica il file P12
- Inserisci la password
- Scarica i componenti PEM estratti

### PEM → PKCS#7
Raggruppa più certificati in un singolo file P7B (senza chiavi).

> 💡 Il convertitore preserva la catena completa dei certificati quando crea file PKCS#12.
`
  }
}
