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
        title: 'Risoluzione multi-CA',
        content: 'Quando un client ACME richiede un certificato, UCM risolve la CA firmataria in quest\'ordine:',
        items: [
          '1. Mappatura domini locali — corrispondenza esatta del dominio, poi dominio padre',
          '2. Mappatura domini DNS — verifica la CA emittente configurata per il provider DNS',
          '3. Predefinito globale — la CA impostata nella configurazione del server ACME',
          '4. Prima CA disponibile con chiave privata',
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
`
  }
}
