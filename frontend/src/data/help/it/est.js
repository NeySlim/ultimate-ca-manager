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
          { label: 'Endpoint EST', text: 'URL degli endpoint EST per l\'integrazione e statistiche di iscrizione' },
        ]
      },
      {
        title: 'Autenticazione',
        items: [
          { label: 'mTLS (TLS reciproco)', text: 'Il client presenta un certificato durante l\'handshake TLS, metodo di autenticazione più sicuro' },
          { label: 'HTTP Basic Auth', text: 'Fallback con nome utente/password quando mTLS non è disponibile. Con allow_empty_username impostato tramite PATCH /api/v2/est/config, un client può inviare anche un nome utente vuoto con la password (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Certificato presentato', text: 'Per /simpleenroll e /serverkeygen via mTLS, un certificato firmato dalla CA EST deve essere uno che essa detiene ancora: i certificati revocati, sostituiti o eliminati vengono rifiutati (RFC 7030 §3.3.2). Un certificato emesso da un\'altra CA di questo server viene rifiutato quando esso o una CA sopra di esso è revocato, o quando è scaduto (v2.252); uno di un\'autorità che questo server non detiene è lasciato al livello TLS' },
          { label: 'Collegamento tls-unique', text: 'Una CSR con un challengePassword deve riportare il valore tls-unique della sua connessione TLS 1.2 verso UCM (RFC 7030 §3.5); viene rifiutata con 400 quando il valore differisce o non può essere verificato (TLS 1.3, un proxy davanti). /csrattrs non ne richiede uno. ignore_challenge_password, impostato tramite PATCH /api/v2/est/config, salta il controllo per un client che vi inserisce una password (v2.252)' },
          { label: 'Chiavi compromesse', text: 'Una CSR la cui chiave è stata revocata come compromessa (keyCompromise) viene rifiutata con 400 (v2.252)' },
        ]
      },
      {
        title: 'Endpoint',
        items: [
          { label: '/cacerts', text: 'Recupera la catena di certificati CA (nessuna autenticazione richiesta)' },
          { label: '/simpleenroll', text: 'Invia un CSR e ricevi un certificato firmato' },
          { label: '/simplereenroll', text: 'Rinnova un certificato esistente (richiede mTLS)' },
          { label: '/csrattrs', text: 'Ottieni gli attributi CSR raccomandati dal server: keyUsage, subjectAltName ed extKeyUsage come OID semplici (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, impostato tramite PATCH /api/v2/est/config, serve la forma precedente (gli OID dentro un extensionRequest) per un client che ne ha bisogno' },
          { label: 'Errori', text: 'I rifiuti di iscrizione, compreso il rate limiting, arrivano come messaggio in testo semplice (text/plain, RFC 8951 §5) che ne spiega il motivo, ad esempio un corpo che non è base64 o non è una CSR PKCS#10, oppure i vincoli sui nomi della CA (v2.252)' },
          { label: '/serverkeygen', text: 'Il server genera una coppia di chiavi e restituisce certificato + chiave. La chiave ha la robustezza della CA emittente, nella famiglia della chiave della richiesta se RSA o EC (la sua dimensione o curva è ignorata), altrimenti in quella della CA, portata al tipo consentito dalle policy più vicino. La chiave arriva come PKCS#8 non cifrato sotto TLS; una CSR che indica la chiave del certificato mTLS (AsymmetricDecryptKeyIdentifier) la riceve cifrata verso quel certificato, con key transport per RSA di 2048 bit o più (keyEncipherment) o key agreement per EC (keyAgreement), con gli algoritmi elencati nelle SMIMECapabilities della CSR, in un pacchetto di chiavi firmato da un certificato EST key generator che la CA emittente rilascia a questo scopo (Ed25519 sotto una CA Ed448, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST è il sostituto moderno di SCEP: preferisci EST per le nuove implementazioni',
      'Usa l\'autenticazione mTLS per la massima sicurezza. Basic Auth è un fallback',
      'L\'endpoint /simplereenroll richiede che il client presenti il suo certificato attuale tramite mTLS',
      'Copia gli URL degli endpoint dalla scheda Endpoint EST per configurare i tuoi client EST',
    ],
    warnings: [
      'EST richiede HTTPS: il client deve fidarsi del certificato del server UCM o della CA',
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

1. **Abilita EST**: Attiva/disattiva il protocollo EST
2. **CA firmataria**: Seleziona quale Autorità di certificazione firma i certificati iscritti tramite EST
3. **Autenticazione**: Configura le credenziali HTTP Basic Auth (nome utente e password)
4. **Validità certificato**: Periodo di validità predefinito per i certificati emessi tramite EST (in giorni)

### Salvataggio della configurazione

Clicca **Salva** per applicare le modifiche. Gli endpoint EST diventano disponibili immediatamente quando abilitati.

## Autenticazione

EST supporta due metodi di autenticazione:

### TLS reciproco (mTLS): Raccomandato

Il client presenta un certificato durante l'handshake TLS. UCM valida il certificato e autentica automaticamente il client.

- **Metodo più sicuro**: identità crittografica del client
- **Obbligatorio per** \`/simplereenroll\`: il client deve presentare il suo certificato attuale
- **Porta 8443**: quando UCM termina il TLS, l'handshake accetta solo i certificati della CA attendibile per mTLS (Impostazioni → Sicurezza) e delle CA sotto di essa; per riscrivere certificati di una CA EST fuori da questo ramo, fai fidare una CA sopra entrambe (v2.252)
- **Certificato presentato**: per \`/simpleenroll\` e \`/serverkeygen\`, un certificato firmato dalla CA EST deve essere uno che essa detiene ancora: i certificati revocati, sostituiti o eliminati vengono rifiutati (RFC 7030 §3.3.2). Un certificato emesso da un'altra CA di questo server viene rifiutato quando esso o una CA sopra di esso è revocato, o quando è scaduto (v2.252); uno di un'autorità che questo server non detiene è lasciato al livello TLS
- **Collegamento tls-unique**: una CSR con un \`challengePassword\` deve riportare il valore \`tls-unique\` della sua connessione TLS 1.2 verso UCM (RFC 7030 §3.5), e viene rifiutata con 400 quando il valore differisce o non può essere verificato (TLS 1.3, un proxy davanti); \`/csrattrs\` non ne richiede uno. \`ignore_challenge_password\`, impostato tramite \`PATCH /api/v2/est/config\`, salta il controllo per un client che vi inserisce una password (v2.252)
- **Dipende da** una corretta configurazione della terminazione TLS (il reverse proxy deve passare \`SSL_CLIENT_CERT\` a UCM)

### HTTP Basic Auth. Fallback

Autenticazione con nome utente e password tramite HTTPS. Configurata nelle Impostazioni EST.

- **Più semplice da configurare**: nessun certificato client necessario
- **Meno sicuro**: credenziali trasmesse per ogni richiesta (protette da HTTPS)
- **Usa quando** l'infrastruttura mTLS non è disponibile
- **Solo password**: con \`allow_empty_username\` impostato tramite \`PATCH /api/v2/est/config\`, un client può inviare un nome utente vuoto con la password (RFC 7030 §3.2.3, v2.252)

## Endpoint EST

Tutti gli endpoint sono sotto \`/.well-known/est/\`:

### GET /cacerts
Recupera la catena di certificati CA. **Nessuna autenticazione richiesta.**

Usalo per il bootstrap della fiducia: i client recuperano il certificato CA prima dell'iscrizione.

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
Rinnova un certificato esistente. **Richiede mTLS**: il client deve presentare il certificato che sta rinnovando, altrimenti riceve 403. Una CSR senza SubjectAltName rinnova i nomi del certificato stesso, o nessuno se non ne aveva, non un nome costruito dal CN (RFC 7030 §4.2.2, v2.252).

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Ottieni gli attributi CSR raccomandati dal server: keyUsage, subjectAltName ed extKeyUsage come OID semplici, la forma che la RFC 9908 §5.2 dà per un OID richiesto senza valore (v2.252). Un client che ha bisogno della forma precedente (gli OID dentro un attributo extensionRequest) la riottiene con \`csrattrs_legacy_encoding\` impostato tramite \`PATCH /api/v2/est/config\`.

### POST /serverkeygen
Il server genera una coppia di chiavi e restituisce il certificato insieme alla chiave privata. Utile quando il client non può generare le chiavi localmente.

La chiave generata ha la robustezza della CA emittente: la famiglia della chiave della richiesta quando è RSA o EC (la sua dimensione o curva è ignorata), altrimenti quella della CA, portata al tipo consentito dalle policy più vicino. 

La chiave privata arriva come PKCS#8 non cifrato (\`application/pkcs8\`), protetta da TLS. Per riceverla cifrata, autenticatevi con mTLS e inserite nella CSR l'identificatore di chiave del certificato client (AsymmetricDecryptKeyIdentifier): la chiave arriva allora in un pacchetto di chiavi RFC 5958 imbustato per quel certificato, con key transport per un certificato RSA di 2048 bit o più che dichiara keyEncipherment, oppure con key agreement (ECDH) per un certificato EC che dichiara keyAgreement, con gli algoritmi di key transport o key agreement e di contenuto presi dalle SMIMECapabilities della CSR nell'ordine del client. Il pacchetto è firmato da un certificato "EST key generator" che la CA emittente rilascia al primo utilizzo e rinnova da sola; è concatenato alla CA servita da \`/cacerts\` e ha la famiglia di chiavi della CA, Ed25519 sotto una CA Ed448 (v2.252).

## Scheda Endpoint EST

La scheda Endpoint EST visualizza:
- **URL degli endpoint**: URL pronti da copiare e incollare per ogni operazione EST
- **Statistiche di iscrizione**: iscrizioni totali, riuscite e fallite

## Esempi di integrazione

### Utilizzo del client est (libest)
Usa \`estclient\` con credenziali HTTP Basic (\`-u\` e \`-h\`) o un certificato client. Le sue opzioni TLS-SRP non si applicano: UCM non offre TLS-SRP.

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
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

La risposta è un PKCS#7 in base64 (solo certificati), non un certificato nudo: leggila con \`openssl pkcs7\`, non con \`openssl x509\`.

### Windows
Windows non ha un client EST integrato: \`certutil -enrollmentServerURL\` registra un servizio web di iscrizione ai certificati (WSTEP), non un server EST. Per le macchine Windows, usa l'iscrizione automatica di Windows (XCEP/WSTEP).

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
