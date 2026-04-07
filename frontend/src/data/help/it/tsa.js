export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Time Stamp Authority',
    overview: 'TSA (RFC 3161) fornisce marche temporali fidate che provano che un documento o un hash esisteva in un momento specifico. Utilizzato per la firma del codice, la conformità legale e le tracce di audit.',
    sections: [
      {
        title: 'Schede',
        items: [
          { label: 'Impostazioni', text: 'Abilita TSA, seleziona la CA firmataria e configura l\'OID della policy TSA' },
          { label: 'Informazioni', text: 'URL dell\'endpoint TSA, esempi di utilizzo con OpenSSL e statistiche delle richieste' },
        ]
      },
      {
        title: 'Configurazione',
        items: [
          { label: 'CA firmataria', text: 'La CA la cui chiave privata firma i token timestamp — deve essere una CA valida e non scaduta' },
          { label: 'Policy OID', text: 'Object Identifier per la policy TSA (es. 1.2.3.4.1) — incluso in ogni risposta timestamp' },
          { label: 'Abilita/Disabilita', text: 'Attiva o disattiva l\'endpoint TSA senza perdere la configurazione' },
        ]
      },
      {
        title: 'Utilizzo',
        items: [
          { label: 'Crea richiesta', text: 'openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq' },
          { label: 'Invia al TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: 'Verifica', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'Le marche temporali TSA vengono usate nella firma del codice per garantire che le firme rimangano valide dopo la scadenza del certificato',
      'L\'endpoint TSA accetta HTTP POST con Content-Type: application/timestamp-query',
      'Usa algoritmi di hash SHA-256 o superiori quando crei richieste di marca temporale',
      'Non è richiesta autenticazione — l\'endpoint TSA è pubblicamente accessibile come CRL/OCSP',
    ],
    warnings: [
      'Una CA firmataria valida deve essere configurata prima di abilitare TSA',
      'L\'endpoint TSA è un endpoint di protocollo pubblico — non inserire dati sensibili nelle richieste di marca temporale',
    ],
  },
  helpGuides: {
    title: 'Protocollo TSA',
    content: `
## Panoramica

Time Stamp Authority (TSA) implementa la **RFC 3161** per fornire marche temporali fidate che provano crittograficamente che un documento, hash o firma digitale esisteva in un momento specifico. TSA è ampiamente utilizzato per la firma del codice, la conformità legale, l'archiviazione a lungo termine e le tracce di audit.

## Come funziona

1. **Il client crea una richiesta di marca temporale** — calcola l'hash di un file con SHA-256/SHA-512 e crea un \`TimeStampReq\` (codificato ASN.1 DER)
2. **Il client invia la richiesta al TSA** — HTTP POST all'endpoint \`/tsa\` con \`Content-Type: application/timestamp-query\`
3. **UCM firma la marca temporale** — la CA configurata firma l'hash + l'ora corrente in un \`TimeStampResp\`
4. **Il client riceve e conserva la risposta** — il file \`.tsr\` può successivamente provare che il documento esisteva in quel momento

## Configurazione

### Scheda Impostazioni

1. **Abilita TSA** — Attiva o disattiva il server TSA
2. **CA firmataria** — Seleziona quale Autorità di Certificazione firma i token timestamp
3. **Policy OID** — Object Identifier per la policy TSA (es. \`1.2.3.4.1\`), incluso in ogni risposta timestamp

### Scelta della CA firmataria

La chiave privata della CA firmataria viene usata per firmare ogni token timestamp. Buone pratiche:

- Usa una **sotto-CA dedicata** per le marche temporali piuttosto che la CA root
- Il certificato della CA dovrebbe includere l'Extended Key Usage **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8)
- Assicurati che il certificato della CA abbia una **validità sufficiente** — le marche temporali devono rimanere verificabili per anni

### Policy OID

Il Policy OID identifica la policy TSA secondo la quale vengono emesse le marche temporali. È incorporato in ogni \`TimeStampResp\`.

- Predefinito: \`1.2.3.4.1\` (segnaposto)
- Per la produzione, registra un OID sotto l'arco della tua organizzazione o usane uno dal tuo CP/CPS

## Scheda Informazioni

La scheda Informazioni mostra:

- **URL dell'endpoint TSA** — URL pronto da copiare per la configurazione del client
- **Esempi di utilizzo** — Comandi OpenSSL per creare richieste, inviarle e verificare le risposte
- **Statistiche** — Totale delle richieste di marca temporale elaborate (riuscite e fallite)

## Esempi di utilizzo

### Creare una richiesta di marca temporale

\`\`\`bash
# Calcola l'hash di un file e crea una richiesta di marca temporale
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### Inviare la richiesta al TSA

\`\`\`bash
# Invia la richiesta e ricevi una risposta timestamp
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### Verificare una marca temporale

\`\`\`bash
# Verifica la risposta timestamp rispetto al file originale
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### Firma del codice con marche temporali

Quando firmi il codice, aggiungi l'URL TSA per garantire che le firme rimangano valide dopo la scadenza del certificato:

\`\`\`bash
# Firma con marca temporale (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# Firma con marca temporale (signtool.exe su Windows)
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### Marche temporali per documenti PDF

\`\`\`bash
# Crea una marca temporale separata per un PDF
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://your-server:8443/tsa -o document.tsr
\`\`\`

## Dettagli del protocollo

| Proprietà | Valore |
|-----------|--------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Endpoint | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Tipo di risposta | \`application/timestamp-reply\` |
| Algoritmi di hash | SHA-256, SHA-384, SHA-512, SHA-1 (legacy) |
| Autenticazione | Nessuna (endpoint pubblico) |
| Trasporto | HTTP o HTTPS |

## Considerazioni sulla sicurezza

- L'endpoint TSA è **pubblico** — non è richiesta autenticazione (come CRL/OCSP)
- Ogni risposta timestamp è **firmata** dalla chiave della CA — i client verificano la firma per garantire l'autenticità
- Usa algoritmi di hash **SHA-256 o superiori** quando crei le richieste (SHA-1 è accettato ma sconsigliato)
- Il TSA **non** vede il documento originale — viene trasmesso solo l'hash
- Considera il **rate limiting** se l'endpoint TSA è esposto a internet

> 💡 Le marche temporali sono essenziali per la firma del codice: garantiscono che il software firmato rimanga fidato anche dopo la scadenza del certificato di firma.
`
  }
}
