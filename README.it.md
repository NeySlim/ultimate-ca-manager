# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** è una piattaforma web per la gestione di autorità di certificazione (CA) con supporto ai protocolli PKI (ACME, SCEP, EST, OCSP, CRL/CDP), integrazione con Microsoft ADCS, autenticazione a più fattori e gestione del ciclo di vita dei certificati.

> **UCM è un progetto giovane e in sviluppo attivo.** Feedback, segnalazioni di bug e richieste di funzionalità sono molto apprezzati! [Apri pure una issue](https://github.com/NeySlim/ultimate-ca-manager/issues): ogni segnalazione aiuta a migliorare UCM.

> Per le novità consulta le [note dell'ultima release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) e il [CHANGELOG](CHANGELOG.md) completo.

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Funzionalità

### PKI di base
- **Gestione delle CA** -- CA radice e intermedie, vista gerarchica, importazione/esportazione, **revoca di una CA intermedia** (CRL e OCSP della CA padre, stato «revocata a monte» per i certificati sottostanti), **CA con solo certificato** (una CA firmata da una richiesta esterna, con la chiave privata importata in un secondo momento), **chiavi di firma su HSM** (la chiave privata non lascia mai l'HSM), **profilo RFC 5280 configurabile** (digest della firma, Key Usage, EKU), una CA può essere **nascosta nei moduli di emissione** (una radice che firma solo CA intermedie) con impostazioni predefinite in stile Let's Encrypt e uno schema di firma **RSA-PSS** facoltativo, **profili di conformità** allineati ad ANSSI, BSI e ai meccanismi concordati dell'UE, **CA firmate esternamente** (UCM genera la coppia di chiavi e una CSR di tipo CA, una radice offline/esterna la firma: la chiave privata non lascia mai UCM, con rinnovo della CSR sulla stessa chiave), **certificati CA con firma incrociata** (allega o firma in modo incrociato un certificato accanto a quello proprio della CA, lo serve nella catena predefinita durante la sostituzione di una radice, sceglie la catena per esportazione o distribuzione, mostra cosa è ancora concatenato alla vecchia radice), **vincoli sui nomi RFC 5280** impostati alla creazione (sottoalberi DNS, intervalli IP ed e-mail consentiti ed esclusi, applicati su ogni percorso di emissione), validità da 1 anno o da un numero qualsiasi di giorni fino a 50 anni, e una regola facoltativa di **soggetto univoco** (un certificato il cui soggetto è già portato da un'altra entità sotto quella CA viene rifiutato su ogni percorso di emissione, RFC 5280 §4.1.2.6)
- **Ciclo di vita dei certificati** -- Emissione, firma, revoca (con il motivo RFC 5280, da ogni finestra di revoca e in blocco), rinnovo (**sul posto**: ID stabili tra i rinnovi, i numeri di serie sostituiti restano in CRL/OCSP fino alla scadenza originale, con una validità scelta comunque limitata dalla policy), ridenominazione (nome visualizzato modificabile, anche per i certificati senza CN), esportazione (PEM, DER, PKCS#12 con una modalità di compatibilità 3DES/SHA-1 per Android 15 e precedenti, macOS 14 e precedenti, Windows e Java meno recenti, JKS; la catena omette per impostazione predefinita la radice autofirmata, con l'opzione **Includi CA radice** quando la destinazione di pacchettizzazione o importazione la richiede), operazioni in blocco, filtri per stato / emittente / origine (ACME, SCEP, EST, AD CS, importazione…), compresi i record **archiviati** da un rinnovo o da una nuova registrazione e conservati per la cronologia, e un **commento** in testo semplice su ogni certificato, trovato dall'elenco e dalla ricerca globale
- **Linting di conformità** -- controlli per certificato rispetto a RFC 5280, CA/Browser Forum Baseline Requirements ed ETSI EN 319 412 tramite pkilint (e zlint quando disponibile), a solo scopo informativo
- **Gestione delle CSR** -- Creazione, importazione e firma delle richieste di firma del certificato con **OID EKU aggiuntivi personalizzati** (RFC 5280 §4.2.1.12), **validazione tipizzata dei SAN** (DNS / IP / e-mail / URI / UPN), curve NIST P-256 / P-384 / P-521 e Brainpool P256r1 / P384r1 / P512r1, e un **percorso di ritorno da CA esterna**: un certificato emesso altrove per una CSR generata in UCM completa quella CSR all'importazione e ne conserva la chiave privata; **nomi aggiunti alla firma** (l'indirizzo e-mail di una richiesta S/MIME da una smart card che contiene solo un CN, con gli stessi vincoli sui nomi, le stesse policy e la stessa approvazione) e **nuova firma** dalla cronologia, per i dispositivi che non possono produrre la richiesta due volte
- **Modelli di certificato** -- Profili predefiniti per server, client, firma del codice, e-mail, accesso con smart card Windows; tipi di chiave RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool e **post-quantistici ML-DSA-44/65/87** (Ed25519/Ed448 per le CA), **estensioni X.509 personalizzate per OID**, **qcStatements (ETSI EN 319 412-5) e OID delle policy del certificato**, e valori predefiniti del soggetto (e-mail inclusa) precompilati nel modulo di emissione; esportazione e importazione JSON che conservano ogni impostazione, un modello o più modelli per file
- **Individuazione dei certificati** -- Scansione di rete, profili di scansione, scansioni pianificate, importazione di certificati
- **Archivio attendibilità** -- Gestione dei certificati delle CA radice attendibili con avvisi di scadenza e rimozione in blocco
- **Riparazione delle catene** -- Validazione della catena basata su AKI/SKI con pianificatore di riparazione automatica
- **Certificati SSH** -- Gestione delle CA SSH, CA SSH su una **chiave HSM** (RSA o NIST ECDSA, la chiave privata non lascia mai il token), firma di certificati host/utente, importazione di CA e certificati, script di configurazione adatti a curl; ID chiave assegnati dalla CA (`principals@nome CA`) o lasciati al richiedente

### Protocolli
- **ACME** -- RFC 8555, registrazione e rinnovo automatici, challenge DNS-01/HTTP-01/TLS-ALPN-01, supporto wildcard, **identificatori IP (RFC 8738)**, **verifica CAA con vincolo ad account/metodo (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **file di challenge HTTP-01 serviti da UCM** (inoltra `/.well-known/acme-challenge/` dalla porta 80, verificati prima dell'invio, rinnovati automaticamente), **scelta del resolver DNS-01** (automatico, solo di sistema o solo quelli elencati, per reti senza accesso ai resolver pubblici) per split-horizon, ACME su IP interni/privati (incluso upstream loopback facoltativo per una CA sullo stesso host), **gestione multi-CA** (scelta della CA per richiesta, fissata sull'ordine così che i rinnovi riutilizzino la stessa CA: Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…), **CSR esterna e riutilizzo della chiave nel rinnovo**, **prova a secco di preflight su staging**, **proxy multi-CA** (i domini upstream già validati passano direttamente, endpoint per CA in `/acme/proxy/<slug>/directory`, compresa la revoca upstream), **catena di certificati preferita** (alternative RFC 8555 §7.4.2, per account CA), **profili di certificato** (draft-ietf-acme-profiles: policy di emissione con nome, pubblicate nella directory e selezionabili per ordine, ciascuna eventualmente associata a un modello di certificato i cui key usage ed EKU governano il certificato emesso, più un **profilo predefinito** e un digest di firma predefinito per gli ordini che non ne indicano alcuno), **gestione degli ordini del server locale** (vista degli ordini con pulizia e rimozione pianificata degli ordini scaduti); il proxy pubblica inoltre i valori TXT dns-01 lato client, così che i controlli di propagazione dei client (lego, Traefik, Caddy) passino senza modifiche, riutilizza l'ordine ancora in sospeso di un account nei nuovi tentativi, e un **listener DNS UPDATE (RFC 2136)** facoltativo permette ai solver rfc2136 standard, come quello di cert-manager, di rispondere a DNS-01 tramite il proxy con chiavi TSIG per account
- **SCEP** -- RFC 8894, registrazione automatica dei dispositivi con flussi di approvazione, GetCert/GetCRL, GetNextCACert firmato, facoltativamente sulla porta HTTP semplice per client come sscep (fuori dalla modalità FIPS, che accetta solo il trasporto di chiavi RSA-OAEP), rinnovi autenticati dal certificato del dispositivo, cifratura AES-128 con ripiego basato su password (PBKDF2) per i client non RSA; una richiesta approvata a mano viene emessa con il modello del profilo da cui è arrivata, esattamente come l'approvazione automatica; i profili con nome validano le challenge **Microsoft Intune** sull'API Intune del tenant, e vi si registrano dispositivi Windows (trasporto di chiavi RSAES-OAEP) e Apple, vedi [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, compresa la generazione della chiave lato server (CMS §4.4) e le **etichette CA** (§3.2.2: più CA servite da un unico endpoint)
- **OCSP** -- RFC 6960, stato del certificato in tempo reale, richieste multi-certificato, supporto nonce, validazione del responder delegato con rinnovo automatico del certificato del responder, validità delle risposte configurabile
- **TSA (RFC 3161)** -- autorità di marcatura temporale con OID di policy configurabile; firma con un **certificato di firma end-entity dedicato** (RFC 3161, richiesto per impostazione predefinita e dai verificatori rigorosi come `openssl ts -verify` e jarsigner), scelto tra i certificati emessi o generato con un clic (EKU timeStamping critico ed esclusivo); rinnovi seguiti automaticamente, catena dell'emittente incorporata nei token, modalità rigorosa con firmatario dedicato, stato e scadenza del firmatario mostrati nella panoramica
- **CRL/CDP** -- Distribuzione degli elenchi di revoche di certificati (CRL) con supporto Delta CRL (RFC 5280 §5.2.4), pianificazione per CA (validità indipendente dalla cadenza di pubblicazione) e digest di firma configurabile, URL con nome facoltativi (slug del nome della CA nei percorsi CDP/AIA, attivabili sulle CA esistenti), **caricamento di CRL firmate esternamente per CA offline / senza chiave** (validate rispetto al certificato della CA con monotonia del numero CRL, servite sull'endpoint CDP esistente e consultate da OCSP)
- **AIA CA Issuers** -- Download del certificato della CA tramite Authority Information Access (RFC 5280 §4.2.2.1)

### Integrazioni
- **Microsoft ADCS** -- Ciclo di vita completo su AD CS: firma delle CSR, individuazione dei modelli, EOBO (Enroll On Behalf Of), rinnovo/revoca tramite il connettore, e un canale di amministrazione WinRM facoltativo per la sincronizzazione delle revoche CRL, l'importazione dell'inventario delle CA e l'approvazione/rifiuto delle richieste in sospeso con un pannello di stato della CA
- **Autoenrollment Windows e connettore Active Directory** -- Policy e registrazione MS-XCEP/WSTEP per macchine e utenti aggiunti al dominio, con il modello indicato dalla richiesta; con l'associazione Kerberos, i modelli di macchina e quelli derivati da AD ricavano il soggetto da Active Directory (il nome host DNS del computer, oppure il DN e l'UPN dell'utente), su più controller di dominio con failover e un controllo di stato pianificato per ciascun DC, mai con un bind anonimo; la registrazione si configura in **profili per realm** (`/api/v2/windows-profiles`), ciascuno con la propria CA, i propri modelli, keytab Kerberos, gruppo AD e connettore, e una richiesta Kerberos è servita dal profilo attivo del realm del suo principal (l'associazione UsernamePassword dal profilo predefinito se è attivo, un rinnovo legato al certificato dal profilo registrato nel certificato presentato), su **più connettori Active Directory** (uno per foresta o dominio)
- **Microsoft Intune** -- Validazione delle challenge SCEP per i dispositivi gestiti da Intune, registrazioni di app Entra definite una sola volta in SCEP › Registrazioni di app Intune e scelte per profilo, con una guida passo passo in `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM incluso, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit; **CA su HSM** con chiavi di firma non esportabili, RSA-PSS e Brainpool su PKCS#11, e una certificazione del dispositivo dichiarata (Common Criteria, EUCC, FIPS 140-3) verificata dal profilo di conformità UE; un test di connessione mostra ciò che un modulo PKCS#11 riporta (libreria, produttore, firmware)
- **Kubernetes / cert-manager** -- Manifest di riferimento per ClusterIssuer (HTTP-01 + DNS-01 con EAB), Certificate di esempio, modello di Secret in `examples/kubernetes/cert-manager/`
- **Provider DNS** -- Cloudflare, Route53, Azure DNS, Plesk e altri per le challenge ACME DNS-01
- **Webhook** -- Notifiche basate su eventi per il ciclo di vita dei certificati (oltre 15 tipi di evento), **cronologia delle consegne per endpoint con nuovo tentativo manuale**, coda di consegna asincrona durevole con backoff esponenziale, e una finestra di conservazione della cronologia perché non cresca senza fine

### Sicurezza e accesso
- **Autenticazione** -- Password, WebAuthn/FIDO2 (anche come secondo fattore, accanto a TOTP o al suo posto), 2FA TOTP, mTLS, chiavi API (`X-API-Key` o `Authorization: Bearer`)
- **Blocco della sessione** -- Blocca la sessione dal menu dell'account o con Alt+Shift+L: ogni scheda si blocca, e il server la mantiene bloccata finché il suo stesso account non la sblocca con la password, il certificato client o la passkey
- **SSO** -- LDAP (LDAPS o StartTLS), OAuth2 (Azure/Google/GitHub), single sign-on SAML con Single Logout, mappatura dei ruoli su ruoli integrati e **ruoli personalizzati** (gruppi SAML letti dall'asserzione, comprese le claim di Entra ID e AD FS) e formato NameID configurabile; **tracciamento di `auth_source` per utente** e sincronizzazione dei ruoli all'accesso su richiesta; accesso **Microsoft Entra multi-tenant** con un elenco di tenant accettati, un **accesso di prova** che mostra l'identità, i gruppi e il ruolo che un provider assegnerebbe prima di essere attivato, e un account che **più provider** possono aprire
- **RBAC** -- 4 ruoli integrati (Admin, Operator, Auditor, Viewer) più ruoli personalizzati con permessi granulari; **i gruppi concedono permessi aggiuntivi** oltre al ruolo dell'utente (mai da amministratore)
- **Policy e approvazioni** -- Policy di emissione dei certificati con flussi di approvazione e regole applicate (tipi di chiave e hash di firma consentiti, limite di SAN DNS, limite di validità, con ambito per CA, modello o pattern DNS), che vincolano **ogni percorso dell'operatore** (il modulo di emissione, la firma di una richiesta memorizzata singola o in blocco, e il rinnovo) e, per tipi di chiave e hash, anche ACME, SCEP, EST, WSTEP e la creazione di CA; una policy che richiede approvazione trattiene le **richieste ACME, EST, SCEP e WSTEP** nella coda di approvazione, e ogni client ne è informato nei termini del proprio protocollo (ACME `processing`, EST 202 con Retry-After, SCEP PENDING, WSTEP pending); una policy può anche sottoporre ad approvazione **revoche e rinnovi**; una richiesta in coda si chiude da sola quando nel frattempo il suo bersaglio viene firmato, rinnovato, eliminato o revocato
- **Valori predefiniti di chiave e hash** -- Una richiesta che non indica né chiave né hash segue un unico valore predefinito su ogni percorso di emissione (RSA-2048 con SHA-256 a meno che un profilo o una policy lo rifiuti, poi il primo tipo accettato), l'hash segue la chiave di firma, e una nuova CA intermedia non adotta mai un hash inferiore a quello della sua CA padre
- **Log di audit** -- Registrazione delle azioni con verifica dell'integrità, inoltro syslog remoto e periodo di conservazione facoltativo
- **Cifratura delle chiavi private** -- AES-128 (Fernet, HMAC-SHA256) a riposo con una chiave master creata al primo avvio (in un container, quando `/etc/ucm` è un volume) o fornita come `KEY_ENCRYPTION_KEY`, che copre le chiavi di CA e certificati, delle CA SSH e dei target di distribuzione, gli account ACME e le chiavi EAB, le challenge SCEP e le password di bind LDAP, con **Cifra le chiavi rimanenti** per i segreti memorizzati prima dell'attivazione; con la cifratura attiva nessun file di chiave in chiaro resta su disco (le copie esistenti vengono rimosse all'attivazione e all'avvio, i file dei certificati pubblici restano), e i file di chiave vengono ricreati quando viene disattivata
- **Alta disponibilità** -- Esegui due o più nodi su un unico database PostgreSQL con `UCM_HA=1` (Docker, Docker Compose, DEB/RPM o `ha.enabled` del chart Helm): un nodo eletto esegue le attività pianificate, le modifiche a impostazioni e cifratura raggiungono ogni nodo, backup e ripristini funzionano da qualsiasi nodo, gli aggiornamenti dei pacchetti procedono un nodo alla volta, e le sessioni sono condivise, quindi solo gli endpoint di registrazione Kerberos richiedono l'affinità sull'indirizzo di origine (vedi [docs/HA.md](docs/HA.md))
- **Modalità FIPS** -- l'immagine Docker `-fips` esegue la crittografia di UCM nel FIPS Provider 3.5.9 di OpenSSL (certificato CMVP #5586), che approva ML-DSA, Ed25519 ed Ed448, quindi le firme post-quantistiche ed EdDSA sono disponibili in modalità FIPS con l'immagine; i pacchetti DEB e RPM compilati con `UCM_FIPS_BUILD=1` girano sul modulo FIPS di RHEL 9 (#5573) o Ubuntu 24.04 Pro (#5115), che non li offrono. Con `UCM_FIPS=1` UCM si avvia solo su un modulo attivo e sottoposto ad autotest, genera le chiavi tramite esso, consente un algoritmo solo quando il modulo caricato lo approva e rifiuta il resto (MD5, 3DES, scrypt, Argon2id, PKCS#12 legacy, NTLM), e un controllo di prontezza elenca in anticipo ciò che un'istanza perderebbe. UCM stesso non è un modulo validato, e Debian 13 e arm64 non fanno parte delle configurazioni testate del certificato #5586
- **Profili di conformità** -- policy per CA allineate ad ANSSI PG-083, BSI TR-02102-1 e ai meccanismi crittografici concordati dell'ECCG (tipi di chiave, hash, schemi di firma, orizzonti di validità, chiavi di CA custodite su HSM, firmatario di marcatura temporale EC), con rifiuti dove il testo impone e avvisi dove raccomanda, e un preflight in sola lettura prima di associare un profilo a una CA esistente; UCM non è certificato né qualificato da nessuno di questi organismi
- **SBOM** -- una SBOM CycloneDX per ogni pacchetto e piattaforma di immagine di ciascuna release, legata all'hash del file o al digest dell'immagine, che elenca ciò che viene distribuito con versioni e licenze dichiarate e ciò che un pacchetto risolve all'installazione ([docs/SBOM.md](docs/SBOM.md))
- **Hardening** -- HSTS configurabile dall'operatore (Impostazioni → Sicurezza o variabile d'ambiente), controllo dei proxy attendibili sugli header dei certificati client, permessi delle chiavi API limitati a quelli del creatore; i proxy attendibili possono essere indicati come reti CIDR e, una volta attivato il supporto proxy, gli header `X-Forwarded-*` sono accettati solo da essi, così che un client che raggiunge direttamente il backend non possa falsificare il proprio indirizzo; l'interfaccia web e l'API di gestione possono essere **limitate a indirizzi IP e reti elencati** mentre gli endpoint dei protocolli PKI restano raggiungibili

### Operazioni e monitoraggio
- **Panoramica** -- Quattro cifre principali, passaggi di configurazione al primo avvio e nove schede indipendenti (coda di lavoro con azioni di rinnovo, nuovo tentativo e pubblicazione, stato dell'automazione, emissioni per origine, orizzonte di scadenza, conformità, copertura delle revoche, gerarchia, ultime operazioni, autorità e HSM), mostrate, nascoste e riordinate con preset di layout salvati per utente, ricaricate da sole quando i dati cambiano
- **Report** -- Report PDF pianificati, riepiloghi per la direzione, certificati revocati, modelli personalizzati
- **Strumenti per certificati** -- Verifica SSL, decodifica di CSR/certificati, abbinamento delle chiavi, convertitore di formato
- **Notifiche e-mail** -- SMTP con STARTTLS o TLS implicito (porta 465), **OAuth2 (XOAUTH2)** per Gmail, Outlook.com e Microsoft 365, modelli HTML/testo personalizzabili, avvisi di scadenza dei certificati con più soglie in giorni (un'e-mail per soglia e periodo di validità, con escalation in stile 30/14/7/1), con la possibilità di escludere i certificati che i client ACME rinnovano da soli
- **Hook di distribuzione** -- Invio dei certificati emessi e rinnovati, e delle CRL rigenerate (DER o un bundle PEM con le CRL delle CA padre), a host remoti tramite SSH/SFTP, con percorsi di destinazione e un comando di ricarica facoltativo per ciascun binding: autenticazione a chiave (ed25519 generata o chiave importata, cifrata a riposo), pinning della chiave host alla prima connessione, percorsi di destinazione per binding (certificato / chiave / catena completa, la catena senza la radice autofirmata a meno che il binding la richieda, scritta in modo atomico), coda di consegna durevole con nuovi tentativi e cronologia per consegna, un **preset sullo stesso host** per i servizi che girano accanto a UCM, e **target API HTTP** che inviano un certificato a un firewall, bilanciatore di carico o API cloud con una sola richiesta costruita da un modello di corpo (URL, metodo, header cifrati, variabili in stile `{{cert_pem|json}}`, chiave privata solo con consenso esplicito su HTTPS verificato)
- **Backup e ripristino** -- Backup cifrati manuali e pianificati con policy di conservazione e un limite facoltativo allo spazio occupato dagli archivi memorizzati; gli archivi sono flussi di blocchi autenticati singolarmente, quindi crearne uno e verificarlo prima di un ripristino non lo tiene intero in memoria; gli archivi contengono gli ordini dei client ACME e le richieste in sospeso, si ripristinano in modalità unione o sostituzione, abbinano le righe per nome tra installazioni e rieseguono le migrazioni di riparazione
- **Bundle di log diagnostici** -- Download con un clic (Impostazioni → Informazioni → Diagnostica) di log dell'applicazione, log degli errori, journal di systemd e una diagnostica di sistema priva di segreti in formato ZIP, con i token sensibili oscurati
- **Visualizzatore dei log di sistema** -- Consultazione dei log dell'applicazione, di accesso, degli errori e del journal di systemd dall'interfaccia, filtrati per livello, intervallo di tempo e testo, con i segreti oscurati
- **Metriche Prometheus** -- endpoint `/metrics` facoltativo, protetto da bearer, che espone contatori di certificati, CA, pianificatore, webhook e ACME
- **Pianificatore** -- vista amministrativa delle attività in background (verifiche di scadenza, aggiornamento CRL, consegna dei webhook, backup, rinnovo automatico) con stato ed esecuzione immediata, eseguite in un processo separato sotto gunicorn
- **HTTPS autoservito** -- applica qualsiasi certificato emesso all'interfaccia web; il binding segue automaticamente i rinnovi (file rigenerati, servizio riavviato)
- **Impostazioni di rete sicure per impostazione predefinita** -- ascolto dual-stack (`HOST=::` serve IPv6 e IPv4 su un solo socket), e protezioni sull'URL base dell'amministratore (verifica di raggiungibilità prima dell'applicazione, il reindirizzamento canonico si disattiva quando l'host non viene più risolto, interruttore di ripristino `UCM_DISABLE_CANONICAL_REDIRECT=1`)
- **Aggiornamenti del software** -- Verifica degli aggiornamenti integrata con installazione in un clic, controllo giornaliero pianificato su un canale stabile o release candidate, e installazione automatica facoltativa (DEB/RPM) con verifica SHA256 obbligatoria ed eventi di esito veritieri (installato solo dopo che l'installazione effettiva è stata verificata per versione), più una finestra facoltativa con le note di release, mostrata una sola volta per utente dopo un aggiornamento
- **Ricerca globale** -- Ricerca tra le risorse e riquadro dei comandi (Ctrl+K)

### Piattaforma
- **Temi** -- Atelier e Aurore, ciascuno scuro o chiaro, oppure in base al sistema; **preferenze per utente salvate lato server** (lingua, tema, modalità)
- **i18n** -- 10 lingue (EN, FR, DE, ES, IT, PT, UK, RU, ZH, JA)
- **Stato dell'interfaccia persistente** -- I filtri selezionati restano dopo il ricaricamento nelle principali pagine a elenco (certificati, CA, modelli, policy, log di audit, archivio attendibilità, utenti, SSH)
- **Database** -- SQLite (predefinito) o **backend PostgreSQL nativo** con interfaccia di migrazione bidirezionale
- **Interfaccia responsive** -- React 18 + Radix UI, adatta ai dispositivi mobili
- **Ispettore e finestre separate** -- Ogni oggetto si apre in un ispettore ancorato con una scheda per oggetto, oppure separato in una finestra propria che resta tra le pagine; **Confronta** mostra da due a quattro certificati affiancati, con le righe diverse evidenziate
- **Tempo reale** -- Aggiornamenti dal vivo via WebSocket: una modifica fatta da un altro operatore aggiorna gli elenchi che la mostrano, e una riconnessione dopo un'interruzione li ricarica invece di lasciare righe obsolete a schermo
- **Multipiattaforma** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm), Kubernetes tramite il chart Helm (`oci://ghcr.io/neyslim/charts/ucm`); i pacchetti installano la rotazione dei log di accesso e degli errori
- **Pronto per il reverse proxy** -- Porte pubbliche indipendenti dalle porte di ascolto (un `:80` o `:443` esplicito negli URL base viene pubblicizzato così come digitato), proxy attendibili per IP o rete CIDR, e valori `proxy.*` del chart Helm per un Ingress davanti a UCM

---

## Avvio rapido

### Docker

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

Disponibile anche da GitHub Container Registry: `ghcr.io/neyslim/ultimate-ca-manager`. La variante FIPS ha il tag `<version>-fips` (si avvia con `UCM_FIPS=1`). Fissate `3` (o `3-fips`) per seguire solo le versioni 3.x.

### Debian/Ubuntu

Scarica il pacchetto `.deb` dall'[ultima release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest):

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Scarica il pacchetto `.rpm` dall'[ultima release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest): `ucm-VERSION-1.fc43.noarch.rpm` per Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` per RHEL, Rocky Linux e AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` per le stesse distribuzioni alla versione 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Accesso:** `https://localhost:8443` oppure `https://your-server-fqdn:8443`
**Primo accesso:** `admin`, con la password generata al primo avvio: `sudo cat /opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat /opt/ucm/data/initial-admin-password`). Va cambiata al primo accesso. Vedi [First access](docs/installation/README.md#first-access) per fornire la propria.

Vedi la [guida all'installazione](docs/installation/README.md) per tutti i metodi, inclusi Docker Compose e l'installazione da sorgenti.

---

## Documentazione

| Risorsa | Link |
|----------|------|
| Wiki (documentazione completa) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Installazione | [docs/installation/](docs/installation/README.md) |
| Guida utente | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Guida amministratore | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| Client del proxy ACME | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| Riferimento API | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Sicurezza | [docs/SECURITY.md](docs/SECURITY.md) |
| Guida all'aggiornamento | [UPGRADE.md](UPGRADE.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

---

## Stack tecnologico

| Componente | Tecnologia |
|-----------|------------|
| Frontend | React 18, Vite, Radix UI |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Database | SQLite o PostgreSQL |
| Server | Gunicorn + gevent WebSocket |
| Crittografia | pyOpenSSL, cryptography |
| Autenticazione | Cookie di sessione, WebAuthn/FIDO2, TOTP, mTLS |

---

## Percorsi dei file

| Elemento | Percorso |
|------|------|
| Applicazione | `/opt/ucm/` |
| Dati e DB | `/opt/ucm/data/` |
| Configurazione (DEB/RPM) | `/etc/ucm/ucm.env` |
| Log (DEB/RPM) | `/var/log/ucm/` |
| Servizio | `systemctl status ucm` |

Docker: dati in `/opt/ucm/data/` (da montare come volume), configurazione tramite variabili d'ambiente, log su stdout.

---

## Contribuire

Le pull request puntano a `dev`, e la prima chiede di firmare una sola volta il
[CLA](CLA.md). Per il resto vedi [CONTRIBUTING.md](CONTRIBUTING.md): come
segnalare un bug in modo utile, come si presenta una pull request rivedibile, e le regole su
test, traduzioni e migrazioni.

---

## Licenza

UCM è software libero sotto la [GNU AGPL v3.0 only](LICENSE). Eseguirlo, a qualsiasi scala e a fini commerciali, non costa nulla; è disponibile una [licenza commerciale](COMMERCIAL-LICENSE.md) per chi lo modifica e non può pubblicare le proprie modifiche.

Le versioni precedenti alla 2.243 restano sotto la loro licenza originale, BSD 3-Clause con Commons Clause.

---

## Supporto

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

Se UCM ti è utile, valuta di sostenerne lo sviluppo:

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
