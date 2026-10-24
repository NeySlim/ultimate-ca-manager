export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gestione automatizzata dei certificati',
    overview: 'UCM supporta due modalità ACME: client ACME per certificati pubblici da qualsiasi CA conforme a RFC 8555 (Let\'s Encrypt, ZeroSSL, HARICA, ecc.) e server ACME locale per l\'automazione PKI interna con mappatura multi-CA dei domini.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "Il server ACME locale pubblica una risorsa renewalInfo: i client apprendono il momento ideale per rinnovare ogni certificato.",
        items: [
          { label: "Finestra suggerita", text: "Restituisce una finestra inizio/fine centrata prima della scadenza, per distribuire i rinnovi" },
          { label: "Revoca", text: "Un certificato revocato restituisce una finestra nel passato → i client conformi rinnovano subito" },
          { label: "Senza autenticazione", text: "renewalInfo è una semplice GET, nessun account o JWS richiesto (RFC 9773)" },
        ]
      },
      {
        title: 'Client ACME',
        items: [
          { label: 'Client', text: 'Richiedi certificati da qualsiasi CA ACME, Let\'s Encrypt, ZeroSSL, HARICA o personalizzata' },
          { label: 'Scheda ordini (v2.219)', text: 'Gli ordini del client hanno una scheda dedicata "Let\'s Encrypt orders" nella barra laterale, con conteggio visibili/totale e filtro di stato, rispecchiando la vista Local orders' },
          { label: 'Account CA esterni', text: 'Uno o più account per CA, più account possono condividere lo stesso URL di directory (es. due account Let\'s Encrypt per separazione amministrativa); un URL di directory vuoto equivale a Let\'s Encrypt Production' },
          { label: 'Server personalizzato', text: 'Imposta un URL directory ACME personalizzato per utilizzare qualsiasi CA conforme a RFC 8555' },
          { label: 'EAB', text: 'Supporto External Account Binding per CA che richiedono la pre-registrazione (ZeroSSL, HARICA, ecc.)' },
          { label: 'Tipi di chiave', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 per le chiavi dei certificati' },
          { label: 'Chiavi account', text: 'Algoritmi ES256 (P-256), ES384 (P-384) o RS256 per le chiavi dell\'account ACME' },
          { label: 'Provider DNS', text: 'Configura i provider di sfida DNS-01 (Cloudflare, Route53, Tencent DNSPod, Plesk, ecc.). Plesk usa la sua API XML; Verify TLS Certificate può essere disattivato per un pannello autofirmato e si può aggiungere un ritardo di propagazione DNS' },
          { label: 'Comando personalizzato', text: 'Tipo di provider DNS che esegue comandi locali configurati dall\'amministratore per creare/eliminare record TXT, i dettagli del record sono passati tramite le variabili d\'ambiente DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION. Percorso binario assoluto obbligatorio, nessuna shell, timeout configurabile' },
          { label: 'Domini', text: 'Mappa i domini ai provider DNS per la validazione automatica' },
          { label: 'HTTP-01', text: 'UCM serve il file di sfida dei suoi ordini in sospeso su /.well-known/acme-challenge/ sulla porta del protocollo HTTP (8080 per impostazione predefinita): inoltra quel percorso dalla porta 80 del dominio a UCM. Verify controlla prima il file e gli ordini HTTP-01 si rinnovano automaticamente' },
        ]
      },
      {
        title: 'Server ACME locale',
        items: [
          { label: 'Configurazione', text: 'Abilita/disabilita il server ACME integrato, seleziona la CA predefinita' },
          { label: 'Domini locali', text: 'Mappa i domini interni a CA specifiche per l\'emissione multi-CA' },
          { label: 'Account', text: 'Visualizza e gestisci gli account client ACME registrati' },
          { label: 'E-mail dell\'account (v2.218)', text: 'L\'e-mail di contatto di un account locale può essere modificata dal suo pannello di dettaglio. Secondo la RFC 8555 il contatto appartiene al client ACME, quindi il suo prossimo aggiornamento dell\'account può sovrascrivere il valore' },
          { label: 'Cronologia', text: 'Traccia tutti gli ordini di emissione certificati ACME' },
                  { label: 'Ordini locali (v2.217)', text: 'La scheda Local orders elenca gli ordini del server integrato con filtro di stato, eliminazione singola e pulizia; gli ordini scaduti non emessi vengono eliminati automaticamente ogni 6 ore, e un digest di firma predefinito si applica agli ordini senza profilo. Dalla v2.218 la pulizia rimuove anche le sfide sorelle rimaste in attesa delle autorizzazioni già convalidate' },
                  { label: 'Profili e modelli (v2.221)', text: 'I profili di certificato (draft-ietf-acme-profiles) sono pubblicati nella directory e scelti dal client per ogni ordine. Ogni profilo fissa validità e digest e può associare un modello di certificato, i cui KU/EKU governano quindi il certificato emesso' },
                  { label: 'Profilo predefinito', text: 'La maggior parte dei client non richiede alcun profilo. Il profilo predefinito, scelto sotto i profili, si applica ai loro ordini; senza di esso ricevono 90 giorni e il digest predefinito' },
        ]
      },
      {
        title: 'Proxy ACME',
        items: [
          { label: 'Account CA a monte', text: 'Seleziona uno degli Account CA esterni: il suo URL directory (Let\'s Encrypt, ZeroSSL, qualsiasi CA RFC 8555) e le credenziali EAB sono impostati su quell\'account' },
          { label: 'Stato account', text: 'Mostra se UCM è registrato presso la CA upstream. Gli account vengono registrati automaticamente alla prima richiesta proxy' },
          { label: 'Test connessione', text: 'Verificare la connettività con la CA upstream e controllare se sono richieste credenziali EAB' },
          { label: 'Reimposta account', text: 'Cancella la registrazione upstream dell\'account CA selezionato per forzare una nuova registrazione' },
          { label: 'Credenziali EAB', text: 'Credenziali External Account Binding per CA che le richiedono (es: ZeroSSL, Google Trust), inserite sull\'account CA in Account CA esterni' },
          { label: 'Sfide DNS', text: 'UCM gestisce le sfide DNS-01 per conto dei client utilizzando i provider DNS configurati' },
          { label: 'Elimina certificati sostituiti', text: 'Interruttore opt-in: quando un ordine proxy viene finalizzato, i certificati importati in precedenza da ordini proxy per lo stesso identico insieme di domini vengono eliminati. I certificati revocati sono sempre conservati; i certificati non-proxy non vengono mai toccati. Disattivato per impostazione predefinita' },
                  { label: 'Pre-check dei client (v2.217)', text: 'Il proxy pubblica anche i valori TXT dns-01 calcolati con la chiave account di ogni client: i pre-check di propagazione di lego/Traefik/Caddy passano senza essere disattivati; un new-order ripetuto restituisce l\'ordine ancora pending dell\'account' },
        ]
      },
      {
        title: 'DNS UPDATE (RFC 2136) per il proxy ACME',
        items: [
          { label: 'Cos\'è', text: 'I client usano il loro solver rfc2136 standard (certbot, lego, cert-manager, acme.sh, win-acme, Posh-ACME) e lo puntano a UCM. UCM crea comunque il record TXT con il proprio provider DNS' },
          { label: 'Chiavi', text: 'Crea le chiavi per ogni account proxy in Account CA esterni. Una chiave può essere collegata a una credenziale EAB: in tal caso vale solo per gli ordini dell\'account ACME registrato con quella credenziale. UCM mostra il segreto una sola volta' },
          { label: 'Modifiche accettate', text: 'UCM accetta solo un record TXT sotto _acme-challenge con il valore che si aspetta per l\'ordine. Rifiuta le altre modifiche. Risponde sempre NOERROR a una cancellazione' },
          { label: 'Porta e rete', text: 'Imposta la porta del listener nella sezione Proxy ACME (0 la disattiva, da 1024 a 65535, serve un riavvio). Usala solo nella rete interna. Per usare la porta 53, reindirizzala in Docker o Kubernetes, oppure con il firewall' },
          { label: 'Algoritmi', text: 'hmac-sha256, hmac-sha384 e hmac-sha512. UCM rifiuta md5 e sha1, i valori predefiniti di molti client: imposta l\'algoritmo in ogni client. cert-manager non supporta sha384, e win-acme lo calcola in modo errato' },
          { label: 'Individuazione della zona (SOA)', text: 'I client chiedono il record SOA per trovare la zona, e UCM risponde. win-acme invece invia aggiornamenti di prova, e usa sempre la porta 53' },
          { label: 'Controlli DNS dei client', text: 'Alcuni client controllano il record TXT nel DNS pubblico prima di continuare (lego, cert-manager, acme.sh). Servono un resolver che veda la zona pubblica, oppure un tempo di attesa: --dns.propagation-wait (lego), --dnssleep (acme.sh), --dns01-recursive-nameservers (cert-manager)' },
        ]
      },
      {
        title: 'Credenziali EAB (lato server)',
        content: 'Quando UCM agisce da server ACME, External Account Binding (RFC 8555 §7.3.4) consente di richiedere credenziali pre-emesse prima che i client registrino account:',
        items: [
          { label: 'Emettere', text: 'Generare una nuova coppia kid + chiave HMAC da ACME → EAB Credentials' },
          { label: 'Distribuire', text: 'Consegnare kid + HMAC al client (cert-manager, certbot, acme.sh)' },
          { label: 'Vincolare', text: 'Il client firma un JWS sulla chiave MAC su newAccount per vincolare il suo account ACME' },
          { label: 'Ruotare / Revocare', text: 'Revocare un kid in qualsiasi momento, gli account esistenti continuano, i nuovi vincoli vengono rifiutati' },
          { label: 'Audit', text: 'Emissione, rotazione e revoca sono auditate sotto l\'operatore che le ha effettuate' },
          { label: 'Restrizioni di dominio', text: 'Limita una credenziale ai domini che può richiedere: * (qualsiasi), *.example.com (tutti i sottodomini) o un elenco esplicito, un elenco vuoto blocca completamente l\'emissione. Applicate su new-order/new-authz, server e proxy; significative solo quando l\'EAB è obbligatorio' },
        ]
      },
      {
        title: 'Resolver DNS personalizzati (DNS-01)',
        items: [
          { label: 'Modalità', text: 'ACME → Let\'s Encrypt → resolver DNS-01: Automatico (elencati, autoritativi, pubblici, poi di sistema), Solo resolver di sistema o Solo resolver elencati. Le modalità ristrette non interrogano mai i resolver pubblici, per le reti che li bloccano' },
          { label: 'Split-horizon', text: 'Utile quando il server autoritativo è interno ma la vista pubblica è cacheata altrove' },
          { label: 'Record obsoleti', text: 'Evita il caching dei resolver pubblici durante i rinnovi automatici rapidi' },
          { label: 'Voci host:port', text: 'IP separati da virgole con porta facoltativa (127.0.0.1:5353, [2001:db8::53]:5300), ogni resolver mantiene la propria porta: es. un BIND solo loopback o dnsmasq su una porta alternativa' },
        ]
      },
      {
        title: 'ACME su IP interne / private',
        content: 'La validazione HTTP-01 e TLS-ALPN-01 funziona nativamente per target RFC1918, loopback, .lan / .local / .corp, il modello di deployment primario di UCM.',
        items: [
          { label: 'Toggle', text: 'ACME → ACME locale → Consenti indirizzi privati e interni (default: attivo)' },
          { label: 'Toggle', text: 'Scheda Let\'s Encrypt → Consenti CA ACME su loopback, per una CA coubicata su 127.0.0.1 (predefinito: disattivato)' },
          { label: 'Sempre bloccato', text: 'Gli IP di metadati cloud (169.254.169.254, fd00:ec2::254, ecc.) sono bloccati incondizionatamente' },
        ]
      },
      {
        title: 'Risoluzione multi-CA',
        content: 'Quando un client ACME richiede un certificato, UCM risolve la CA firmataria in quest\'ordine:',
        items: [
          '1. Mappatura domini locali: corrispondenza esatta del dominio, poi dominio padre',
          '2. Mappatura domini DNS: verifica la CA emittente configurata per il provider DNS',
          '3. Predefinito globale: la CA impostata nella configurazione del server ACME',
          '4. Prima CA disponibile con chiave privata',
        ]
      },
      {
        title: 'Certificati per indirizzi IP (RFC 8738)',
        content: 'Il server ACME locale può emettere certificati per indirizzi IPv4 e IPv6, non solo nomi DNS. Usa il tipo di identificatore « ip » nell\'ordine.',
        items: [
          { label: 'Identificatore', text: 'Ordine con { "type": "ip", "value": "192.0.2.10" } (IPv4) o un letterale IPv6 come 2001:db8::1' },
          { label: 'Sfide', text: 'Sono offerti solo HTTP-01 e TLS-ALPN-01, DNS-01 è vietato per gli identificatori IP secondo RFC 8738' },
          { label: 'SNI TLS-ALPN-01', text: 'La validazione usa la forma reverse-DNS (in-addr.arpa / ip6.arpa) come hostname SNI' },
          { label: 'SAN emesso', text: 'Il certificato contiene un SAN iPAddress; sono supportati ordini misti DNS + IP' },
          { label: 'IP interne', text: 'Gli indirizzi RFC1918 e loopback si validano nativamente, il modello di deployment principale di UCM' },
        ]
      },
      {
        title: 'Validazione DNS persistente (dns-persist-01)',
        content: 'Il server ACME locale può validare i domini tramite un record TXT persistente legato all\'account ACME (draft-ietf-acme-dns-persist): rinnovo senza scritture DNS. Opt-in, disattivato per impostazione predefinita.',
        items: [
          { label: 'Record', text: 'Create _validation-persist.<dominio> TXT "<dominio-emittente>; accounturi=<URL dell\'account>", l\'oggetto challenge annuncia i due valori attesi' },
          { label: 'Attivazione', text: 'ACME → Configurazione → Validazione DNS persistente (dns-persist-01)' },
          { label: 'Wildcard / sottodomini', text: 'Aggiungete policy=wildcard per autorizzare anche certificati wildcard e sottodomini del nome validato' },
          { label: 'persistUntil', text: 'persistUntil=<timestamp unix> opzionale: blocca le nuove validazioni dopo tale data' },
          { label: 'Sicurezza', text: 'Il record conferisce alla chiave dell\'account la capacità di emissione finché esiste, eliminate il TXT per revocarla' },
        ]
      }
    ],
    tips: [
      'URL directory ACME: https://your-server:port/acme/directory',
      'Usa un URL directory personalizzato per connetterti a ZeroSSL, HARICA o qualsiasi CA RFC 8555',
      'Le credenziali EAB (Key ID + chiave HMAC) vengono fornite dalla tua CA al momento della registrazione',
      'Quando UCM è il server ACME, emetti le tue credenziali EAB in ACME → EAB Credentials',
      'Per Kubernetes/cert-manager: vedi i manifest di riferimento in examples/kubernetes/cert-manager/',
      'Le chiavi ECDSA P-256 offrono una sicurezza equivalente a RSA-2048 con dimensioni molto ridotte',
      'Usa i Domini locali per assegnare CA diverse a domini interni differenti',
      'Qualsiasi CA con chiave privata può essere selezionata come CA emittente',
      'I domini con carattere jolly (*.example.com) richiedono la validazione DNS-01',
      'Ogni account CA mantiene la propria registrazione upstream: passando il proxy a un altro account si usa quella di quell\'account',
      'Usa l\'URL del proxy con certbot: certbot certonly --server https://your-server:port/acme/proxy/directory',
    ],
    warnings: [
      'La validazione del dominio è obbligatoria: il tuo server deve essere raggiungibile o il DNS configurato',
      'La modifica del tipo di chiave dell\'account richiede una nuova registrazione dell\'account ACME',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Panoramica

UCM supporta ACME (Automated Certificate Management Environment) in due modalità:

- **Client ACME**: Ottieni certificati da qualsiasi CA conforme a RFC 8555 (Let's Encrypt, ZeroSSL, HARICA o personalizzata)
- **Server ACME locale**: Server ACME integrato per l'automazione PKI interna con supporto multi-CA

## Client ACME

### Impostazioni del client
Gestisci la configurazione del tuo client ACME:
- **Ambiente**: Staging (test) o Produzione (certificati reali)
- **Email di contatto**: Obbligatoria per la registrazione dell'account
- **Rinnovo automatico**: Rinnova automaticamente i certificati prima della scadenza
- **Tipo chiave certificato**: RSA-2048, RSA-4096, ECDSA P-256 o ECDSA P-384
- **Algoritmo chiave account**: ES256, ES384 o RS256 per la firma dell'account ACME

### Server ACME personalizzato
Usa qualsiasi CA conforme a RFC 8555, non solo Let's Encrypt:

| Provider CA | URL directory |
|---|---|
| **Let's Encrypt** | *(predefinito, lascia vuoto)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Imposta l'URL directory della tua CA come **URL directory ACME** del suo account in **Account CA esterni**.

### Account CA esterni
Gestisci tutti gli account esterni con cui UCM si registra:

- **Più account per CA consentiti**: più account possono condividere lo stesso URL di directory (es. due account Let's Encrypt con email di contatto diverse per la separazione amministrativa, utile con dns-persist-01). La riga dell'account, non l'URL, è l'identità.
- **URL di directory vuoto**: corrisponde per impostazione predefinita a Let's Encrypt Production.
- **Account predefinito**: utilizzato quando una richiesta non seleziona alcun account; le ricerche per URL risolvono verso l'account predefinito.
- **Importa**: importa la chiave privata di un account esistente alla creazione: gli involucri PKCS#8, SEC1/X9.62 (\`BEGIN EC PRIVATE KEY\`) e PKCS#1 (\`BEGIN RSA PRIVATE KEY\`) sono tutti accettati; l'algoritmo è derivato automaticamente.
- **Endpoint proxy dedicato**: ogni account può esporre \`/acme/proxy/<slug>/directory\` con il proprio slug.

### External Account Binding (EAB)
Alcune CA richiedono credenziali EAB per collegare il tuo account ACME con un account esistente presso la CA:

1. Registrati sul portale della tua CA per ottenere **EAB Key ID** e **chiave HMAC**
2. Inserisci entrambi i valori (**ID chiave EAB**, **Chiave HMAC EAB**) sull'account CA in **Account CA esterni**
3. La chiave HMAC è codificata in base64url (fornita dalla CA)

> 💡 L'EAB è richiesto da ZeroSSL, HARICA, Google Trust Services e dalla maggior parte delle CA aziendali.

### ECDSA vs RSA

| Tipo chiave | Dimensione | Sicurezza | Prestazioni |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Standard | Base |
| **RSA-4096** | 4096 bit | Superiore | Più lento |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Molto più veloce |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Più veloce |

Le chiavi ECDSA sono raccomandate per le implementazioni moderne: più piccole, più veloci e ugualmente sicure.

### Origine della chiave
Quando richiedi un certificato, scegli da dove proviene la chiave privata:

- **Genera nuova chiave** *(predefinito)*: UCM crea una nuova coppia di chiavi per ogni ordine
- **Riusa la chiave al rinnovo**: mantiene la stessa chiave privata tra i rinnovi (necessario per DANE/TLSA e key pinning); la prima emissione genera la chiave, i rinnovi la ricaricano
- **Fornisci CSR esterno**: incolla un CSR PEM generato altrove; UCM lo invia al finalize e la chiave privata non entra mai in UCM. I domini del CSR devono corrispondere esattamente agli identificatori dell'ordine

### Preflight (prova a vuoto)
**Esegui preflight** nel modulo di richiesta valida l'intera richiesta contro la directory **staging** di Let's Encrypt, senza consumare i limiti di produzione:

- Verifica sintassi dei domini, email di contatto, account ACME / EAB e connettività CA
- La modalità **Completa** crea un ordine staging e mostra in anteprima i record TXT \`_acme-challenge\` esatti da pubblicare
- **Solo validazione** verifica configurazione e connettività senza creare ordini
- Facoltativamente verifica la propagazione DNS dei TXT dopo l'aggiunta dei record

> 💡 Le CA personalizzate non hanno endpoint staging: il preflight convalida allora solo configurazione e connettività.

### Provider DNS
Configura i provider di sfida DNS-01 per la validazione del dominio. I provider supportati includono:
- Cloudflare
- AWS Route 53
- Azure DNS
- Google Cloud DNS
- DigitalOcean
- OVH
- Tencent Cloud DNSPod
- Plesk (API XML): **Verify TLS Certificate** può essere disattivato per un pannello autofirmato e si può aggiungere un ritardo di propagazione DNS
- E altri

Ogni provider richiede credenziali API specifiche per il servizio DNS.

#### Provider Comando personalizzato
Per i servizi DNS senza driver nativo, il provider **Comando personalizzato** esegue comandi locali configurati dall'amministratore per creare/eliminare record TXT. I dettagli del record sono passati come variabili d'ambiente:

- \`DOMAIN\`: dominio di base in corso di validazione
- \`RECORD_NAME\`: nome completo del record TXT (\`_acme-challenge.example.com\`)
- \`RECORD_VALUE\`: contenuto del TXT (digest della sfida)
- \`TTL\`: TTL del record in secondi
- \`ACTION\`: \`create\` o \`delete\`

Il comando richiede un **percorso binario assoluto**, viene eseguito senza shell (niente pipe né espansioni) e viene terminato dopo un timeout configurabile (5–300 s, predefinito 60). Usa un piccolo script wrapper per integrare qualsiasi strumento DNS esterno.

### Resolver DNS personalizzati
**Resolver DNS-01** sceglie dove UCM cerca i record TXT \`_acme-challenge\`: **Automatico** (resolver elencati, poi server autoritativi della zona, poi resolver pubblici, poi resolver di sistema), **Solo resolver di sistema** o **Solo resolver elencati**. Le modalità ristrette non interrogano mai i resolver pubblici, per le reti che li bloccano. Le voci sono IP separati da virgole con porta facoltativa, es. \`127.0.0.1:5353\` o \`[2001:db8::53]:5300\`.

### Sfide HTTP-01
UCM serve il file di sfida dei suoi ordini in sospeso su \`/.well-known/acme-challenge/<token>\`, sulla porta del protocollo HTTP (8080 per impostazione predefinita). La CA lo richiede sulla porta 80 del dominio: inoltra quel percorso a UCM dal tuo reverse proxy, oppure associa UCM alla porta 80. **Verify Challenge** controlla prima il file e non invia se non viene servito; **Force verification** invia comunque. Gli ordini HTTP-01 si rinnovano automaticamente.

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
3. Selezionare un **Account CA upstream** in **Account CA esterni** (Let's Encrypt, Actalis, ZeroSSL, URL personalizzata, EAB)
4. Cliccare su **Test connessione** per verificare la connettività con la CA upstream
5. Registrare l'account upstream se necessario (email + **Registra account**)
6. UCM registra automaticamente un account alla prima richiesta proxy se non già fatto

### Percorsi proxy dedicati (multi-CA)
Ogni account CA esterno può esporre il proprio endpoint proxy ACME:

1. Aprire **Account CA esterni** (stessa scheda Let's Encrypt)
2. Modificare o creare un account CA
3. Attivare **Esporre tramite proxy ACME**
4. Impostare uno **slug** univoco: es. \`actalis-production\`, \`letsencrypt-staging\`
5. Salvare: l'URL appare nella sezione proxy e sulla scheda account

I client usano:
\`\`\`
https://vostro-server-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

Il percorso predefinito legacy resta disponibile per l'account selezionato nelle impostazioni proxy:
\`\`\`
https://vostro-server-ucm:8443/acme/proxy/directory
\`\`\`

Slug riservati (vietati): \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, ecc.

### Gestione account
- Il **badge stato account** mostra se UCM è registrato presso la CA upstream
- Ogni account CA mantiene la propria registrazione upstream: passando all'account upstream di un altro si usa quella di quell'account, registrata alla prima richiesta proxy se necessario
- Usare il pulsante **Reimposta account** per cancellare manualmente le credenziali se necessario
- **Test connessione** verifica se il directory upstream è raggiungibile e se è richiesto EAB

### Eliminazione dei certificati sostituiti
Ogni rinnovo proxy importa un nuovo certificato nell'inventario, quindi quelli sostituiti si accumulano nel tempo. L'interruttore **Elimina certificati sostituiti** (impostazioni proxy) pulisce automaticamente: quando un ordine proxy viene finalizzato, i certificati importati in precedenza da ordini proxy per lo **stesso identico insieme di domini** vengono eliminati.

- **I certificati revocati sono sempre conservati**: il record di revoca resta intatto
- I certificati non emessi tramite il proxy non vengono mai toccati
- Disattivato per impostazione predefinita

### Utilizzo del proxy
Puntare i client ACME interni al directory proxy del CA di destinazione.

**URL per slug** (consigliato con più CA):
\`\`\`
https://vostro-server-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

**URL predefinita** (account selezionato nelle impostazioni proxy):
\`\`\`
https://vostro-server-ucm:8443/acme/proxy/directory
\`\`\`

Esempio con certbot (sostituire \`<slug>\`):
\`\`\`
certbot certonly \\
  --server https://vostro-server-ucm:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 Le credenziali EAB dell'account CA upstream sono distinte da quelle del client: autenticano UCM presso la CA upstream, non i vostri client presso UCM. Impostale su quell'account in **Account CA esterni**.

> ⚠ Prerequisito: il dominio deve essere in ACME Domains con provider DNS. Il proxy supporta solo dns-01.

> ⚠ Evitare richieste simultanee per lo stesso FQDN (Certbot + interfaccia UCM).

> ℹ️ In lab / certificato autofirmato, aggiungere \`--no-verify-ssl\` a Certbot.

### DNS UPDATE (RFC 2136)
Anche i client che possono usare solo un solver rfc2136 standard possono usare il proxy ACME. Inviano l'aggiornamento DNS a UCM, e UCM crea il record TXT con il proprio provider DNS.

#### Configurazione
1. Attiva **Esporre tramite proxy ACME** sull'account CA e imposta un percorso proxy (vedi sopra)
2. Nella sezione **Proxy ACME** imposta la **porta del listener DNS UPDATE** (0 la disattiva, da 1024 a 65535). Riavvia UCM per applicarla
3. Rendi la porta raggiungibile solo dalla rete interna. Per la porta 53, reindirizzala verso il listener in Docker o Kubernetes, oppure con il firewall
4. Sulla scheda dell'account CA fai clic su **Chiavi DNS UPDATE (RFC 2136)**, poi su **Nuova chiave**
5. Scegli un algoritmo (hmac-sha256 è il predefinito) e, se serve, una credenziale EAB
6. Copia il segreto e l'esempio di configurazione per il tuo client. UCM mostra il segreto una sola volta

#### Cosa accetta UCM
- Solo record TXT sotto \`_acme-challenge\` con il valore che UCM si aspetta per l'ordine
- UCM risponde sempre NOERROR a una cancellazione
- Una chiave vale per l'account proxy a cui appartiene. Con un collegamento EAB vale solo per gli ordini dell'account ACME registrato con quella credenziale
- Revoca una chiave per fermarla subito. Elimina una chiave revocata per rimuoverla

#### Note sui client
- **Algoritmo**: UCM rifiuta i valori predefiniti di molti client (HMAC-MD5, hmac-sha1). Imposta hmac-sha256 (o sha512) in ogni client
- **certbot**: \`dns_rfc2136_server\` deve essere un indirizzo IP. Imposta \`dns_rfc2136_algorithm = HMAC-SHA256\`
- **lego**: imposta \`DNSUPDATE_TSIG_ALGORITHM\`. Il valore predefinito è hmac-sha1. Usa \`--dns.propagation-wait\` se lego non vede la zona pubblica
- **cert-manager**: supporta solo HMACSHA256 e HMACSHA512, non sha384. Trova la zona con i suoi resolver ricorsivi: imposta \`--dns01-recursive-nameservers\` su un resolver che vede la zona pubblica
- **acme.sh**: usa \`dns_nsupdate\` con \`NSUPDATE_KEY\` che punta al file di chiave BIND. Usa \`--dnssleep\` se i controlli del DNS pubblico falliscono
- **win-acme**: invia sempre l'aggiornamento alla porta 53 (\`--serverport\` è usato come timeout), quindi reindirizza la porta 53 verso il listener UCM. Calcola hmac-sha384 in modo errato: usa sha256
- **Posh-ACME**: \`DDNSNameserver\` è obbligatorio. Senza di esso, nsupdate invia l'aggiornamento al MNAME della zona sulla porta 53

Esempio (acme.sh):
\`\`\`
export NSUPDATE_SERVER="ucm.example.com"
export NSUPDATE_SERVER_PORT="8053"
export NSUPDATE_KEY="/etc/ucm-tsig.key"
acme.sh --issue --dns dns_nsupdate --server https://ucm.example.com/acme/proxy/<slug>/directory -d www.example.com --dnssleep 30
\`\`\`

> ⚠ Usa il listener solo nella rete interna. Non pubblicarlo su Internet.

## Server ACME locale

### Configurazione
- **Abilita/Disabilita**: Attiva/disattiva il server ACME integrato
- **CA predefinita**: Seleziona quale CA firma i certificati per impostazione predefinita
- **Termini di servizio**: URL opzionale dei ToS per i client

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
1. **Mappatura domini locali**: Corrispondenza esatta, poi corrispondenza dominio padre
2. **Mappatura domini DNS**: La CA configurata per il provider DNS
3. **Predefinito globale**: La CA impostata nella configurazione del server ACME
4. **Prima disponibile**: Qualsiasi CA con chiave privata

### Credenziali EAB (lato server)
Quando UCM è il server ACME (o il proxy), puoi richiedere l'**External Account Binding**: i client devono presentare una coppia kid + chiave HMAC pre-emessa per registrare un account. Emetti e revoca le credenziali da **ACME → EAB Credentials**.

Ogni credenziale può essere limitata ai **domini per cui può richiedere certificati**:
- \`*\`: qualsiasi dominio (predefinito per le credenziali nuove ed esistenti)
- \`*.example.com\`: il dominio e tutti i suoi sottodomini
- Un elenco esplicito di domini
- Un **elenco vuoto blocca completamente l'emissione** per quella credenziale

Le restrizioni sono applicate su new-order e new-authz, sia sul server ACME integrato sia sul proxy. Sono significative solo quando l'**EAB è obbligatorio**: altrimenti i client possono semplicemente registrarsi senza credenziale.

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

> 💡 Gli indirizzi interni (RFC1918, loopback) si validano nativamente: il modello di deployment principale di UCM. Gli IP di metadati cloud restano bloccati.

## Validazione DNS persistente (dns-persist-01)

Il server ACME locale supporta **dns-persist-01** (draft-ietf-acme-dns-persist): validazione tramite un record TXT **persistente** legato all'account ACME, i rinnovi non richiedono scritture DNS.

### Configurazione
1. Attivatelo in **ACME → Configurazione → Validazione DNS persistente** (disattivato per impostazione predefinita).
2. Create il record una sola volta:
\`\`\`
_validation-persist.app.example.com. IN TXT "ca.example.com; accounturi=https://ca.example.com/acme/acct/<id>"
\`\`\`
L'oggetto challenge annuncia i valori attesi \`accounturi\` e \`issuer-domain-names\`.

### Opzioni
- \`policy=wildcard\`: autorizza anche certificati wildcard e sottodomini del nome validato (un record su un dominio padre copre i suoi figli)
- \`persistUntil=<timestamp-unix>\`: blocca le nuove validazioni dopo tale data

> ⚠️ Il record conferisce capacità di emissione alla chiave dell'account ACME finché esiste: eliminate il TXT per revocarla.

## Utilizzo di certbot

\`\`\`
# Registra account (Let's Encrypt: predefinito)
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

## Renewal Information (ARI, RFC 9773)

Il server ACME locale annuncia \`renewalInfo\` nel suo directory e serve una **finestra di rinnovo suggerita** per certificato.

- Finestra centrata prima della scadenza → rinnovi distribuiti nel tempo
- Certificato revocato → finestra nel passato (rinnova subito)
- GET non autenticata su \`/acme/renewalInfo/<certID>\`

`
  }
}
