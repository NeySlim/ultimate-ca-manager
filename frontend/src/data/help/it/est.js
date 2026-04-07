export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Enrollment over Secure Transport',
    overview: 'EST (RFC 7030) fornisce l\'iscrizione sicura dei certificati tramite HTTPS con TLS reciproco (mTLS) o autenticazione HTTP Basic. Ideale per ambienti aziendali moderni che richiedono l\'iscrizione basata su standard con forte sicurezza del trasporto.',
    sections: [
      {
        title: 'Schede',
        items: [
          { label: 'Impostazioni', text: 'Abilita EST, seleziona la CA firmataria, configura le credenziali di autenticazione e la validità del certificato' },
          { label: 'Informazioni', text: 'URL degli endpoint EST per l\'integrazione, statistiche di iscrizione ed esempi di utilizzo' },
        ]
      },
      {
        title: 'Autenticazione',
        items: [
          { label: 'mTLS (TLS reciproco)', text: 'Il client presenta un certificato durante l\'handshake TLS — metodo di autenticazione più sicuro' },
          { label: 'HTTP Basic Auth', text: 'Fallback con nome utente/password quando mTLS non è disponibile' },
        ]
      },
      {
        title: 'Endpoint',
        items: [
          { label: '/cacerts', text: 'Recupera la catena di certificati CA (nessuna autenticazione richiesta)' },
          { label: '/simpleenroll', text: 'Invia un CSR e ricevi un certificato firmato' },
          { label: '/simplereenroll', text: 'Rinnova un certificato esistente (richiede mTLS)' },
          { label: '/csrattrs', text: 'Ottieni gli attributi CSR raccomandati dal server' },
          { label: '/serverkeygen', text: 'Il server genera la coppia di chiavi e restituisce certificato + chiave' },
        ]
      },
    ],
    tips: [
      'EST è il sostituto moderno di SCEP — preferisci EST per le nuove implementazioni',
      'Usa l\'autenticazione mTLS per la massima sicurezza — Basic Auth è un fallback',
      'L\'endpoint /simplereenroll richiede che il client presenti il suo certificato attuale tramite mTLS',
      'Copia gli URL degli endpoint dalla scheda Informazioni per configurare i tuoi client EST',
    ],
    warnings: [
      'EST richiede HTTPS — il client deve fidarsi del certificato del server UCM o della CA',
      'L\'autenticazione mTLS richiede una corretta configurazione della terminazione TLS (il reverse proxy deve inoltrare i certificati client)',
    ],
  },
  helpGuides: {
    title: 'Protocollo EST',
    content: `
## Panoramica

Enrollment over Secure Transport (EST) è definito in **RFC 7030** e fornisce l'iscrizione dei certificati, la re-iscrizione e il recupero dei certificati CA tramite HTTPS. EST è il sostituto moderno di SCEP, offrendo una sicurezza superiore attraverso l'autenticazione TLS reciproca (mTLS).

## Configurazione

### Scheda Impostazioni

1. **Abilita EST** — Attiva/disattiva il protocollo EST
2. **CA firmataria** — Seleziona quale Autorità di certificazione firma i certificati iscritti tramite EST
3. **Autenticazione** — Configura le credenziali HTTP Basic Auth (nome utente e password)
4. **Validità certificato** — Periodo di validità predefinito per i certificati emessi tramite EST (in giorni)

### Salvataggio della configurazione

Clicca **Salva** per applicare le modifiche. Gli endpoint EST diventano disponibili immediatamente quando abilitati.

## Autenticazione

EST supporta due metodi di autenticazione:

### TLS reciproco (mTLS) — Raccomandato

Il client presenta un certificato durante l'handshake TLS. UCM valida il certificato e autentica automaticamente il client.

- **Metodo più sicuro** — identità crittografica del client
- **Obbligatorio per** \`/simplereenroll\` — il client deve presentare il suo certificato attuale
- **Dipende da** una corretta configurazione della terminazione TLS (il reverse proxy deve passare \`SSL_CLIENT_CERT\` a UCM)

### HTTP Basic Auth — Fallback

Autenticazione con nome utente e password tramite HTTPS. Configurata nelle Impostazioni EST.

- **Più semplice da configurare** — nessun certificato client necessario
- **Meno sicuro** — credenziali trasmesse per ogni richiesta (protette da HTTPS)
- **Usa quando** l'infrastruttura mTLS non è disponibile

## Endpoint EST

Tutti gli endpoint sono sotto \`/.well-known/est/\`:

### GET /cacerts
Recupera la catena di certificati CA. **Nessuna autenticazione richiesta.**

Usalo per il bootstrap della fiducia — i client recuperano il certificato CA prima dell'iscrizione.

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Invia un CSR PKCS#10 e ricevi un certificato firmato.

Richiede autenticazione (mTLS o Basic Auth).

\`\`\`bash
# Utilizzo di curl con Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Rinnova un certificato esistente. **Richiede mTLS** — il client deve presentare il certificato che sta rinnovando.

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Ottieni gli attributi CSR (OID) raccomandati dal server.

### POST /serverkeygen
Il server genera una coppia di chiavi e restituisce il certificato insieme alla chiave privata. Utile quando il client non può generare le chiavi localmente.

## Scheda Informazioni

La scheda Informazioni visualizza:
- **URL degli endpoint** — URL pronti da copiare e incollare per ogni operazione EST
- **Statistiche di iscrizione** — Numero di iscrizioni, re-iscrizioni ed errori
- **Ultima attività** — Operazioni EST più recenti dai log di audit

## Esempi di integrazione

### Utilizzo del client est (libest)
\`\`\`bash
estclient -s your-server -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

### Utilizzo di OpenSSL
\`\`\`bash
# Recupera i certificati CA
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Genera CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# Iscrizione (Basic Auth)
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://your-server:8443/.well-known/est" \\
  kerberos
\`\`\`

## EST vs SCEP

| Caratteristica | EST | SCEP |
|---------|-----|------|
| Trasporto | HTTPS (TLS) | HTTP o HTTPS |
| Autenticazione | mTLS + Basic Auth | Password di sfida |
| Standard | RFC 7030 (2013) | RFC 8894 (2020, ma legacy) |
| Generazione chiavi | Opzione lato server | Solo client |
| Rinnovo | Re-iscrizione mTLS | Re-iscrizione |
| Sicurezza | Forte (basata su TLS) | Più debole (segreto condiviso) |
| Raccomandazione | ✅ Preferito per nuovi | Solo dispositivi legacy |

> 💡 Usa EST per le nuove implementazioni. Usa SCEP solo per dispositivi di rete legacy che non supportano EST.
`
  }
}
