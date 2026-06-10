export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gestione automatizzata dei certificati',
    overview: 'UCM supporta due modalità ACME: client ACME per certificati pubblici da qualsiasi CA conforme a RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, ecc.) e server ACME locale per l\'automazione PKI interna con mappatura multi-CA dei domini.',
    sections: [
      {
        title: 'Client ACME',
        items: [
          { label: 'Client', text: 'Richiedi certificati da qualsiasi CA ACME — Let\'s Encrypt, ZeroSSL, Buypass, HARICA o personalizzata' },
          { label: 'Server personalizzato', text: 'Imposta un URL directory ACME personalizzato per utilizzare qualsiasi CA conforme a RFC 8555' },
          { label: 'EAB', text: 'Supporto External Account Binding per CA che richiedono la pre-registrazione (ZeroSSL, HARICA, ecc.)' },
          { label: 'Tipi di chiave', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 per le chiavi dei certificati' },
          { label: 'Chiavi account', text: 'Algoritmi ES256 (P-256), ES384 (P-384) o RS256 per le chiavi dell\'account ACME' },
          { label: 'Provider DNS', text: 'Configura i provider di sfida DNS-01 (Cloudflare, Route53, ecc.)' },
          { label: 'Domini', text: 'Mappa i domini ai provider DNS per la validazione automatica' },
        ]
      },
      {
        title: 'Server ACME locale',
        items: [
          { label: 'Configurazione', text: 'Abilita/disabilita il server ACME integrato, seleziona la CA predefinita' },
          { label: 'Domini locali', text: 'Mappa i domini interni a CA specifiche per l\'emissione multi-CA' },
          { label: 'Account', text: 'Visualizza e gestisci gli account client ACME registrati' },
          { label: 'Cronologia', text: 'Traccia tutti gli ordini di emissione certificati ACME' },
        ]
      },
      {
        title: 'Proxy ACME',
        items: [
          { label: 'CA upstream', text: 'Selezionare un preset (Let\'s Encrypt Produzione/Staging) o inserire un URL personalizzato per qualsiasi CA RFC 8555' },
          { label: 'Stato account', text: 'Mostra se UCM è registrato presso la CA upstream. Gli account vengono registrati automaticamente alla prima richiesta proxy' },
          { label: 'Test connessione', text: 'Verificare la connettività con la CA upstream e controllare se sono richieste credenziali EAB' },
          { label: 'Reimposta account', text: 'Cancellare le credenziali dell\'account upstream per forzare una nuova registrazione (usare dopo il cambio di CA)' },
          { label: 'Credenziali EAB', text: 'Credenziali External Account Binding per CA che le richiedono (es: ZeroSSL, Google Trust)' },
          { label: 'Sfide DNS', text: 'UCM gestisce le sfide DNS-01 per conto dei client utilizzando i provider DNS configurati' },
        ]
      },
      {
        title: 'Risoluzione multi-CA',
        content: 'Quando un client ACME richiede un certificato, UCM risolve la CA firmataria in quest\'ordine:',
        items: [
          '1. Mappatura domini locali — corrispondenza esatta del dominio, poi dominio padre',
          '2. Mappatura domini DNS — verifica la CA emittente configurata per il provider DNS',
          '3. Predefinito globale — la CA impostata nella configurazione del server ACME',
          '4. Prima CA disponibile con chiave privata',
        ]
      },
      {
        title: 'Credenziali EAB (lato server)',
        content: 'Quando UCM agisce da server ACME, External Account Binding (RFC 8555 §7.3.4) consente di richiedere credenziali pre-emesse prima che i client registrino account:',
        items: [
          { label: 'Emettere', text: 'Generare una nuova coppia kid + chiave HMAC da ACME → EAB Credentials' },
          { label: 'Distribuire', text: 'Consegnare kid + HMAC al client (cert-manager, certbot, acme.sh)' },
          { label: 'Vincolare', text: 'Il client firma un JWS sulla chiave MAC su newAccount per vincolare il suo account ACME' },
          { label: 'Ruotare / Revocare', text: 'Revocare un kid in qualsiasi momento — gli account esistenti continuano, i nuovi vincoli vengono rifiutati' },
          { label: 'Audit', text: 'Emissione, rotazione e revoca sono auditate sotto l\'operatore che le ha effettuate' },
        ]
      },
      {
        title: 'Resolver DNS personalizzati (DNS-01)',
        items: [
          { label: 'Override per account', text: 'Sovrascrive i resolver di sistema durante la validazione dei record TXT _acme-challenge' },
          { label: 'Split-horizon', text: 'Utile quando il server autoritativo è interno ma la vista pubblica è cacheata altrove' },
          { label: 'Record obsoleti', text: 'Evita il caching dei resolver pubblici durante i rinnovi automatici rapidi' },
        ]
      },
      {
        title: 'ACME su IP interne / private',
        content: 'La validazione HTTP-01 e TLS-ALPN-01 funziona nativamente per target RFC1918, loopback, .lan / .local / .corp — il modello di deployment primario di UCM.',
        items: [
          { label: 'Toggle', text: 'Settings → SystemConfig → acme.allow_private_ips (default: true)' },
          { label: 'Sempre bloccato', text: 'Gli IP di metadati cloud (169.254.169.254, fd00:ec2::254, ecc.) sono bloccati incondizionatamente' },
        ]
      },

      {
        title: 'Certificati per indirizzi IP (RFC 8738)',
        content: 'Il server ACME locale può emettere certificati per indirizzi IPv4 e IPv6, non solo nomi DNS. Usa il tipo di identificatore « ip » nell\'ordine.',
        items: [
          { label: 'Identificatore', text: 'Ordine con { "type": "ip", "value": "192.0.2.10" } (IPv4) o un letterale IPv6 come 2001:db8::1' },
          { label: 'Sfide', text: 'Sono offerti solo HTTP-01 e TLS-ALPN-01 — DNS-01 è vietato per gli identificatori IP secondo RFC 8738' },
          { label: 'SNI TLS-ALPN-01', text: 'La validazione usa la forma reverse-DNS (in-addr.arpa / ip6.arpa) come hostname SNI' },
          { label: 'SAN emesso', text: 'Il certificato contiene un SAN iPAddress; sono supportati ordini misti DNS + IP' },
          { label: 'IP interne', text: 'Gli indirizzi RFC1918 e loopback si validano nativamente — il modello di deployment principale di UCM' },
        ]
      },
    ],
    tips: [
      'URL directory ACME: https://your-server:port/acme/directory',
      'Usa un URL directory personalizzato per connetterti a ZeroSSL, Buypass, HARICA o qualsiasi CA RFC 8555',
      'Le credenziali EAB (Key ID + chiave HMAC) vengono fornite dalla tua CA al momento della registrazione',
      'Le chiavi ECDSA P-256 offrono una sicurezza equivalente a RSA-2048 con dimensioni molto ridotte',
      'Usa i Domini locali per assegnare CA diverse a domini interni differenti',
      'Qualsiasi CA con chiave privata può essere selezionata come CA emittente',
      'I domini con carattere jolly (*.example.com) richiedono la validazione DNS-01',
      'Quando UCM è il server ACME, emetti le tue credenziali EAB in ACME → EAB Credentials',
      'Per Kubernetes/cert-manager: vedi i manifest di riferimento in examples/kubernetes/cert-manager/',
    ],
    warnings: [
      'La validazione del dominio è obbligatoria — il tuo server deve essere raggiungibile o il DNS configurato',
      'La modifica del tipo di chiave dell\'account richiede una nuova registrazione dell\'account ACME',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Panoramica

UCM supporta ACME (Automated Certificate Management Environment) in due modalità:

- **Client ACME** — Ottieni certificati da qualsiasi CA conforme a RFC 8555 (Let's Encrypt, ZeroSSL, Buypass, HARICA o personalizzata)
- **Server ACME locale** — Server ACME integrato per l'automazione PKI interna con supporto multi-CA

## Client ACME

### Impostazioni del client
Gestisci la configurazione del tuo client ACME:
- **Ambiente** — Staging (test) o Produzione (certificati reali)
- **Email di contatto** — Obbligatoria per la registrazione dell'account
- **Rinnovo automatico** — Rinnova automaticamente i certificati prima della scadenza
- **Tipo chiave certificato** — RSA-2048, RSA-4096, ECDSA P-256 o ECDSA P-384
- **Algoritmo chiave account** — ES256, ES384 o RS256 per la firma dell'account ACME

### Server ACME personalizzato
Usa qualsiasi CA conforme a RFC 8555, non solo Let's Encrypt:

| Provider CA | URL directory |
|---|---|
| **Let's Encrypt** | *(predefinito, lascia vuoto)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Imposta l'URL directory della tua CA in **Impostazioni** → **Server ACME personalizzato**.

### External Account Binding (EAB)
Alcune CA richiedono credenziali EAB per collegare il tuo account ACME con un account esistente presso la CA:

1. Registrati sul portale della tua CA per ottenere **EAB Key ID** e **chiave HMAC**
2. Inserisci entrambi i valori in **Impostazioni** → **Server ACME personalizzato**
3. La chiave HMAC è codificata in base64url (fornita dalla CA)

> 💡 L'EAB è richiesto da ZeroSSL, HARICA, Google Trust Services e dalla maggior parte delle CA aziendali.

### ECDSA vs RSA

| Tipo chiave | Dimensione | Sicurezza | Prestazioni |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Standard | Base |
| **RSA-4096** | 4096 bit | Superiore | Più lento |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Molto più veloce |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Più veloce |

Le chiavi ECDSA sono raccomandate per le implementazioni moderne — più piccole, più veloci e ugualmente sicure.

### Provider DNS
Configura i provider di sfida DNS-01 per la validazione del dominio. I provider supportati includono:
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- E altri

Ogni provider richiede credenziali API specifiche per il servizio DNS.

### Domini
Mappa i tuoi domini ai provider DNS. Quando si richiede un certificato per un dominio, UCM utilizza il provider mappato per creare i record di sfida DNS-01.

1. Clicca **Aggiungi dominio**
2. Inserisci il nome del dominio (es. \`example.com\` o \`*.example.com\`)
3. Seleziona il provider DNS
4. Clicca **Salva**

> 💡 I certificati con carattere jolly (\`*.example.com\`) richiedono la validazione DNS-01.


## Modalità Proxy ACME

Il proxy ACME consente ai client interni di richiedere certificati da una CA pubblica (Let's Encrypt, ZeroSSL, ecc.) tramite UCM, senza accesso diretto a Internet. UCM funge da intermediario, gestendo le sfide DNS-01 e inoltrando le richieste alla CA upstream.

### Quando usare la modalità proxy
- Server interni senza accesso diretto a Internet
- Gestione centralizzata delle sfide DNS-01 tramite i provider DNS configurati in UCM
- Audit e tracciamento di tutte le emissioni di certificati pubblici

### Configurazione
1. Andare su **ACME** → scheda **Let's Encrypt**
2. Scorrere fino alla sezione **Proxy ACME**
3. Attivare l'interruttore **Proxy ACME**
4. Selezionare una **CA upstream**: Let's Encrypt Produzione, Let's Encrypt Staging o Personalizzato
5. Per CA personalizzate, inserire manualmente l'URL del directory ACME
6. Se la CA upstream richiede EAB, espandere **Credenziali EAB** e inserire Key ID e chiave HMAC
7. Cliccare su **Test connessione** per verificare la connettività con la CA upstream
8. UCM registra automaticamente un account alla prima richiesta proxy

### Gestione account
- Il **badge stato account** mostra se UCM è registrato presso la CA upstream
- Il cambio di CA upstream cancella automaticamente le credenziali obsolete e forza una nuova registrazione
- Usare il pulsante **Reimposta account** per cancellare manualmente le credenziali se necessario
- **Test connessione** verifica se il directory upstream è raggiungibile e se è richiesto EAB

### Utilizzo del proxy
Puntare i client ACME interni al directory proxy:
\`\`\`
https://vostro-server-ucm:8443/acme/proxy/directory
\`\`\`

> 💡 Le credenziali EAB del proxy sono distinte da quelle del client — autenticano UCM presso la CA upstream, non i vostri client presso UCM.

> ⚠ La modalità proxy richiede almeno un provider DNS configurato in UCM per la risoluzione delle sfide.

## Server ACME locale

### Configurazione
- **Abilita/Disabilita** — Attiva/disattiva il server ACME integrato
- **CA predefinita** — Seleziona quale CA firma i certificati per impostazione predefinita
- **Termini di servizio** — URL opzionale dei ToS per i client

### URL directory ACME
\`\`\`
https://your-server:8443/acme/directory
\`\`\`

I client come certbot, acme.sh o Caddy usano questo URL per scoprire gli endpoint ACME.

### Domini locali (Multi-CA)
Mappa i domini interni a CA specifiche. Questo consente a domini diversi di essere firmati da CA diverse.

1. Clicca **Aggiungi dominio**
2. Inserisci il dominio (es. \`internal.corp\` o \`*.dev.local\`)
3. Seleziona la **CA emittente**
4. Abilita/disabilita l'**approvazione automatica**
5. Clicca **Salva**

### Ordine di risoluzione CA
Quando un client ACME richiede un certificato, UCM determina la CA firmataria in quest'ordine:
1. **Mappatura domini locali** — Corrispondenza esatta, poi corrispondenza dominio padre
2. **Mappatura domini DNS** — La CA configurata per il provider DNS
3. **Predefinito globale** — La CA impostata nella configurazione del server ACME
4. **Prima disponibile** — Qualsiasi CA con chiave privata

### Account
Visualizza gli account client ACME registrati:
- ID account e email di contatto
- Data di registrazione
- Numero di ordini

### Cronologia
Sfoglia tutti gli ordini di emissione certificati:
- Stato dell'ordine (in attesa, valido, non valido, pronto)
- Nomi di dominio richiesti
- CA firmataria utilizzata
- Timestamp di emissione

## Utilizzo di certbot

\`\`\`
# Registra account (Let's Encrypt — predefinito)
certbot register --agree-tos --email admin@example.com

# Registra con CA ACME personalizzata + EAB
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --agree-tos --email admin@example.com

# Richiedi certificato con chiave ECDSA
certbot certonly --server https://your-server:8443/acme/directory \\
  --standalone -d myserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Rinnova
certbot renew --server https://your-server:8443/acme/directory
\`\`\`

## Utilizzo di acme.sh

\`\`\`
# Predefinito (Let's Encrypt)
acme.sh --issue -d example.com --standalone

# CA ACME personalizzata con EAB e ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ Per ACME interno, i client devono fidarsi della CA UCM. Installa il certificato della CA Root nel trust store del client.
## Certificati per indirizzi IP (RFC 8738)

Il server ACME locale può emettere certificati per **indirizzi IP** (IPv4 e IPv6), non solo nomi DNS. Utile per servizi interni, appliance e host indirizzati direttamente tramite IP.

### Ordinare un certificato IP
Usa il tipo di identificatore \`ip\` nell'ordine ACME:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Sono supportati anche ordini misti DNS + IP.

### Validazione
- **HTTP-01** e **TLS-ALPN-01** sono le uniche sfide offerte per gli identificatori IP. **DNS-01 è vietato** per gli IP dalla RFC 8738.
- **HTTP-01** si connette direttamente all'IP (i letterali IPv6 sono tra parentesi quadre, es. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** usa la forma reverse-DNS dell'IP (\`in-addr.arpa\` / \`ip6.arpa\`) come hostname SNI.

### Certificato emesso
Il certificato firmato contiene una voce SubjectAltName **iPAddress** per ogni IP validato.

> 💡 Gli indirizzi interni (RFC1918, loopback) si validano nativamente — il modello di deployment principale di UCM. Gli IP di metadati cloud restano bloccati.

`
  }
}
