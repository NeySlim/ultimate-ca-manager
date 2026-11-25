# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** est une plateforme web de gestion d'autorités de certification (AC) qui prend en charge les protocoles PKI (ACME, SCEP, EST, OCSP, CRL/CDP), s'intègre à Microsoft AD CS et offre l'authentification multifacteur et la gestion du cycle de vie des certificats.

> **UCM est un projet jeune, en développement actif.** Retours, rapports de bogues et demandes de fonctionnalités sont les bienvenus ! N'hésitez pas à [ouvrir un ticket](https://github.com/NeySlim/ultimate-ca-manager/issues) : chaque rapport aide à améliorer UCM.

> Les nouveautés sont dans les [notes de la dernière version](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) et dans le [CHANGELOG](CHANGELOG.md) complet.

![Tableau de bord](docs/screenshots/dashboard-dark.png)

---

## Fonctionnalités

### Cœur PKI
- **Gestion des AC** -- AC racines et intermédiaires, vue hiérarchique, import/export, **révocation d'une AC intermédiaire** (CRL et OCSP du parent, état « révoquée en amont » en dessous), **AC à certificat seul** (une AC signée à partir d'une demande externe, sa clé privée importée plus tard), **clés de signature protégées par HSM** (la clé privée ne quitte jamais le HSM), **profil RFC 5280 configurable** (empreinte de signature, Key Usage, EKU), possibilité de **masquer une AC des formulaires d'émission** (une racine qui ne signe que des intermédiaires) avec des valeurs par défaut dans le style de Let's Encrypt et un schéma de signature **RSA-PSS** facultatif, **profils de conformité** alignés sur l'ANSSI, le BSI et les mécanismes agréés de l'UE, **AC signées en externe** (UCM génère la paire de clés et une CSR de type AC, une racine hors ligne ou externe la signe : la clé privée ne quitte jamais UCM, avec renouvellement de la CSR sur la même clé), **certificats d'AC en certification croisée** (rattacher ou croiser-signer un certificat à côté de celui de l'AC, le servir dans la chaîne par défaut pendant un changement de racine, choisir la chaîne à chaque export ou déploiement, voir ce qui chaîne encore vers l'ancienne racine), **contraintes de noms RFC 5280** définies à la création (sous-arbres DNS, plages IP et e-mail autorisés et exclus, appliqués sur tous les chemins d'émission), validité d'un an ou d'un nombre de jours quelconque jusqu'à 50 ans, et règle facultative d'**unicité du sujet** (un certificat dont le sujet est déjà porté par une autre entité sous cette AC est refusé sur tous les chemins d'émission, RFC 5280 §4.1.2.6)
- **Cycle de vie des certificats** -- Émettre, signer, révoquer (avec le motif RFC 5280, depuis chaque boîte de dialogue de révocation et en masse), renouveler (**sur place** : identifiants stables d'un renouvellement à l'autre, numéros de série remplacés conservés dans la CRL et l'OCSP jusqu'à leur expiration d'origine, une validité choisie restant plafonnée par la politique), renommer (nom d'affichage modifiable, y compris pour les certificats sans CN), exporter (PEM, DER, PKCS#12 avec un mode de compatibilité 3DES/SHA-1 pour Android 15 et antérieur, macOS 14 et antérieur, les anciens Windows et Java, JKS ; la chaîne omet par défaut la racine auto-signée, avec une option **Inclure l'AC racine** quand une cible d'empaquetage ou d'import en a besoin), opérations en masse, filtre par état / émetteur / source (ACME, SCEP, EST, AD CS, import…), y compris les enregistrements **archivés** par un renouvellement ou une nouvelle inscription et conservés pour l'historique, et un **commentaire** en texte brut sur chaque certificat, retrouvé par la liste et la recherche globale
- **Contrôle de conformité (linting)** -- vérifications par certificat selon la RFC 5280, les Baseline Requirements du CA/Browser Forum et ETSI EN 319 412 via pkilint (et zlint quand il est disponible), à titre informatif seulement
- **Gestion des CSR** -- Créer, importer et signer des demandes de signature de certificat avec des **OID EKU supplémentaires personnalisés** (RFC 5280 §4.2.1.12), une **validation typée des SAN** (DNS / IP / e-mail / URI / UPN), les courbes NIST P-256 / P-384 / P-521 et Brainpool P256r1 / P384r1 / P512r1, et un **chemin de retour d'AC externe** : un certificat émis ailleurs pour une CSR générée dans UCM complète cette CSR à l'import et conserve sa clé privée ; **noms ajoutés à la signature** (l'adresse e-mail d'une demande S/MIME issue d'une carte à puce qui ne porte qu'un CN, sous les mêmes contraintes de noms, politiques et approbation) et **nouvelle signature** depuis l'historique, pour les équipements qui ne peuvent pas produire leur demande deux fois
- **Modèles de certificats** -- Profils prédéfinis pour serveur, client, signature de code, e-mail, ouverture de session par carte à puce Windows ; types de clés RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool et **post-quantique ML-DSA-44/65/87** (Ed25519/Ed448 pour les AC), **extensions X.509 personnalisées par OID**, **qcStatements (ETSI EN 319 412-5) et OID de politique de certificat**, et valeurs de sujet par défaut (e-mail compris) préremplies dans le formulaire d'émission ; export et import JSON qui conservent tous les réglages, un modèle ou plusieurs par fichier
- **Découverte de certificats** -- Analyse du réseau, profils d'analyse, analyses planifiées, import de certificats
- **Magasin de confiance** -- Gestion des certificats d'AC racines de confiance avec alertes d'expiration et suppression en masse
- **Réparation de chaînes** -- Validation des chaînes par AKI/SKI avec planificateur de réparation automatique
- **Certificats SSH** -- Gestion d'autorités de certification SSH, AC SSH sur une **clé HSM** (RSA ou NIST ECDSA, la clé privée ne quittant jamais le jeton), signature de certificats d'hôte et d'utilisateur, import d'AC et de certificats, scripts d'installation utilisables avec curl ; identifiants de clé nommés par l'AC (`principals@nom de l'AC`) ou laissés au demandeur

### Protocoles
- **ACME** -- RFC 8555, inscription et renouvellement automatiques, défis DNS-01/HTTP-01/TLS-ALPN-01, jokers (wildcard), **identifiants IP (RFC 8738)**, **contrôle CAA avec liaison au compte et à la méthode (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **fichiers de défi HTTP-01 servis par UCM** (rediriger `/.well-known/acme-challenge/` depuis le port 80, vérifiés avant l'envoi, renouvelés automatiquement), **choix du résolveur DNS-01** (automatique, système seulement ou résolveurs listés seulement, pour les réseaux sans accès aux résolveurs publics) pour le split-horizon, ACME sur des IP internes ou privées (y compris un amont en boucle locale, sur option, pour une AC colocalisée), **gestion multi-AC** (choix de l'AC par demande, fixé sur la commande pour que les renouvellements réutilisent la même AC : Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…), **CSR externe et réutilisation de la clé au renouvellement**, **simulation préalable sur l'environnement de test (staging)**, **proxy multi-AC** (les domaines amont déjà validés passent tels quels, points d'accès par AC sous `/acme/proxy/<slug>/directory`, révocation amont comprise), **chaîne de certification préférée** (alternatives de la RFC 8555 §7.4.2, par compte d'AC), **profils de certificat** (draft-ietf-acme-profiles : des politiques d'émission nommées, annoncées dans le répertoire et sélectionnables par commande, chacune pouvant être liée à un modèle de certificat dont l'usage de clé et l'EKU régissent alors le certificat émis, plus un **profil par défaut** et une empreinte de signature par défaut pour les commandes qui n'en nomment aucun), **gestion des commandes du serveur local** (vue des commandes avec nettoyage et purge planifiée des commandes expirées) ; le proxy publie aussi les valeurs TXT dns-01 côté client pour que les vérifications préalables de propagation des clients (lego, Traefik, Caddy) passent telles quelles, réutilise la commande encore en attente d'un compte lors des nouvelles tentatives, et un **écouteur DNS UPDATE (RFC 2136)** facultatif permet aux solveurs rfc2136 standard, comme celui de cert-manager, de répondre au DNS-01 à travers le proxy avec des clés TSIG par compte
- **SCEP** -- RFC 8894, inscription automatique des équipements avec circuits d'approbation, GetCert/GetCRL, GetNextCACert signé, éventuellement sur le port HTTP simple pour des clients comme sscep (hors mode FIPS, qui n'accepte que le transport de clé RSA-OAEP), renouvellements authentifiés par le certificat de l'équipement, chiffrement AES-128 avec repli par mot de passe (PBKDF2) pour les clients non RSA ; une demande approuvée à la main est émise avec le modèle du profil par lequel elle est arrivée, exactement comme l'approbation automatique ; des profils nommés valident les défis **Microsoft Intune** auprès de l'API Intune du locataire, et les équipements Windows (transport de clé RSAES-OAEP) et Apple s'inscrivent par ce biais, voir [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, avec génération de clé côté serveur (CMS §4.4) et **étiquettes d'AC** (§3.2.2 : servir plusieurs AC depuis un seul point d'accès)
- **OCSP** -- RFC 6960, état des certificats en temps réel, requêtes multi-certificats, prise en charge du nonce, validation du répondeur délégué avec renouvellement automatique de son certificat, validité des réponses configurable
- **TSA (RFC 3161)** -- autorité d'horodatage avec OID de politique configurable ; signe avec un **certificat de signature d'entité finale dédié** (RFC 3161, exigé par défaut et par les vérificateurs stricts comme `openssl ts -verify` et jarsigner), choisi parmi les certificats émis ou généré en un clic (critique, EKU timeStamping exclusif) ; renouvellements suivis automatiquement, chaîne de l'émetteur intégrée aux jetons, mode strict du signataire dédié, état et expiration du signataire affichés sur la vue d'ensemble
- **CRL/CDP** -- Distribution des listes de révocation avec prise en charge des Delta CRL (RFC 5280 §5.2.4), calendrier par AC (validité découplée de la cadence de publication) et empreinte de signature configurable, URL nommées facultatives (slug du nom de l'AC dans les chemins CDP/AIA, activable sur des AC existantes), **import de CRL signées en externe pour les AC hors ligne ou sans clé** (validées contre le certificat de l'AC avec monotonie du numéro de CRL, servies au point d'accès CDP existant et consultées par l'OCSP)
- **AIA CA Issuers** -- Téléchargement du certificat d'AC via Authority Information Access (RFC 5280 §4.2.2.1)

### Intégrations
- **Microsoft AD CS** -- Cycle de vie complet sur AD CS : signature de CSR, découverte des modèles, EOBO (Enroll On Behalf Of), renouvellement et révocation par le connecteur, et un canal d'administration WinRM facultatif pour la synchronisation des révocations CRL, l'import de l'inventaire des AC et l'approbation ou le refus des demandes en attente, avec un panneau d'état de l'AC
- **Inscription automatique Windows et connecteur Active Directory** -- Stratégie et inscription MS-XCEP/WSTEP pour les machines et utilisateurs joints au domaine, sous le modèle que nomme la demande ; avec la liaison Kerberos, les modèles de machine et ceux dérivés d'AD tirent le sujet d'Active Directory (le nom d'hôte DNS de l'ordinateur, ou le DN et l'UPN de l'utilisateur), sur plusieurs contrôleurs de domaine avec basculement et contrôle d'état planifié par contrôleur, jamais avec une liaison anonyme ; l'inscription se configure dans des **profils par realm** (`/api/v2/windows-profiles`), chacun avec sa propre AC, ses modèles, son keytab Kerberos, son groupe AD et son connecteur ; une demande Kerberos est servie par le profil activé du realm de son principal (la liaison UsernamePassword par le profil par défaut quand il est activé, un renouvellement lié à un certificat par le profil enregistré sur le certificat présenté), à travers **plusieurs connecteurs Active Directory** (un par forêt ou domaine)
- **Microsoft Intune** -- Validation des défis SCEP pour les équipements gérés par Intune, enregistrements d'application Entra définis une fois sous SCEP › Enregistrements d'application Intune et choisis par profil, avec un guide pas à pas dans `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM inclus, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit ; **AC protégées par HSM** avec clés de signature non exportables, RSA-PSS et Brainpool sur PKCS#11, et une certification de l'équipement déclarée (Critères communs, EUCC, FIPS 140-3) contrôlée par le profil de conformité de l'UE ; un test de connexion affiche ce que signale un module PKCS#11 (bibliothèque, fabricant, micrologiciel)
- **Kubernetes / cert-manager** -- Manifestes de référence pour un ClusterIssuer (HTTP-01 + DNS-01 avec EAB), un Certificate d'exemple et un modèle de Secret dans `examples/kubernetes/cert-manager/`
- **Fournisseurs DNS** -- Cloudflare, Route53, Azure DNS, Plesk et d'autres pour les défis ACME DNS-01
- **Webhooks** -- Notifications événementielles pour les événements du cycle de vie des certificats (plus de 15 types d'événements), **historique des envois par point d'accès avec nouvelle tentative manuelle**, file d'envoi asynchrone durable avec attente exponentielle, et une durée de conservation de l'historique pour qu'il ne grossisse pas indéfiniment

### Sécurité et accès
- **Authentification** -- Mot de passe, WebAuthn/FIDO2 (aussi comme second facteur, en plus ou à la place du TOTP), 2FA par TOTP, mTLS, clés d'API (`X-API-Key` ou `Authorization: Bearer`)
- **Verrouillage de session** -- Verrouiller la session depuis le menu du compte ou avec Alt+Shift+L : tous les onglets se verrouillent, et le serveur la garde verrouillée jusqu'à ce que son propre compte la déverrouille avec son mot de passe, son certificat client ou sa clé d'accès (passkey)
- **SSO** -- LDAP (LDAPS ou StartTLS), OAuth2 (Azure/Google/GitHub), authentification unique SAML avec déconnexion unique (Single Logout), correspondance des rôles avec les rôles intégrés et des **rôles personnalisés** (groupes SAML lus dans l'assertion, revendications Entra ID et AD FS comprises) et format de NameID configurable ; **suivi de `auth_source` par utilisateur** et synchronisation des rôles à la connexion sur option ; connexion **Microsoft Entra multi-tenant** avec une liste de tenants acceptés, **connexion de test** qui montre l'identité, les groupes et le rôle qu'un fournisseur donnerait avant son activation, et un compte que **plusieurs fournisseurs** peuvent ouvrir
- **RBAC** -- 4 rôles intégrés (Admin, Operator, Auditor, Viewer) plus des rôles personnalisés aux permissions fines ; **les groupes accordent des permissions supplémentaires** en plus du rôle de l'utilisateur (jamais administrateur)
- **Politiques et approbations** -- Politiques d'émission de certificats avec circuits d'approbation et règles appliquées (types de clés et hachages de signature autorisés, plafond de SAN DNS, plafond de validité, limitées par AC, modèle ou motif DNS), qui s'imposent à **tous les chemins opérateur** (le formulaire d'émission, la signature d'une demande enregistrée seule ou en masse, et le renouvellement) et, pour les types de clés et les hachages, à ACME, SCEP, EST, WSTEP et à la création d'AC également ; une politique qui exige une approbation met en attente **les demandes ACME, EST, SCEP et WSTEP** dans la file d'approbation, et chaque client en est informé dans les termes de son protocole (ACME `processing`, EST 202 avec Retry-After, SCEP PENDING, WSTEP pending) ; une politique peut aussi soumettre à approbation **les révocations et les renouvellements** ; une demande en file est close d'elle-même quand sa cible est signée, renouvelée, supprimée ou révoquée entre-temps
- **Valeurs par défaut des clés et hachages** -- Une demande qui ne nomme ni clé ni hachage suit une seule valeur par défaut sur tous les chemins d'émission (RSA-2048 avec SHA-256 sauf si un profil ou une politique le refuse, puis le premier type accepté), le hachage suit la clé de signature, et une nouvelle AC intermédiaire ne prend jamais un hachage inférieur à celui de son parent
- **Journaux d'audit** -- Journalisation des actions avec vérification d'intégrité, transfert syslog distant et durée de conservation facultative
- **Chiffrement des clés privées** -- AES-128 (Fernet, HMAC-SHA256) au repos sous une clé maître créée au premier démarrage (dans un conteneur, quand `/etc/ucm` est un volume) ou fournie par `KEY_ENCRYPTION_KEY`, couvrant les clés des AC et des certificats, les clés des AC SSH et des cibles de déploiement, les clés de compte ACME et EAB, les défis SCEP et les mots de passe de liaison LDAP, avec **Chiffrer les clés restantes** pour les secrets enregistrés avant son activation ; chiffrement activé, aucun fichier de clé en clair n'est conservé sur le disque (les copies existantes sont supprimées à l'activation et au démarrage, les fichiers de certificats publics restent), et les fichiers de clés sont recréés quand il est désactivé
- **Haute disponibilité** -- Faire tourner deux nœuds ou plus sur une seule base PostgreSQL avec `UCM_HA=1` (Docker, Docker Compose, DEB/RPM ou `ha.enabled` du chart Helm) : un nœud élu exécute les tâches planifiées, les changements de réglages et de chiffrement atteignent chaque nœud, les sauvegardes et les restaurations fonctionnent depuis n'importe quel nœud, les mises à jour de paquets se font un nœud à la fois, et les sessions sont partagées, si bien que seuls les points d'accès d'inscription Kerberos demandent une affinité par adresse source (voir [docs/HA.md](docs/HA.md))
- **Mode FIPS** -- l'image Docker `-fips` exécute la cryptographie d'UCM dans l'OpenSSL FIPS Provider 3.5.9 (certificat CMVP #5586), qui approuve ML-DSA, Ed25519 et Ed448 : les signatures post-quantiques et EdDSA sont donc disponibles en mode FIPS avec l'image ; les paquets DEB et RPM construits avec `UCM_FIPS_BUILD=1` s'exécutent sur le module FIPS de RHEL 9 (#5573) ou d'Ubuntu 24.04 Pro (#5115), qui ne les fournissent pas. Avec `UCM_FIPS=1`, UCM ne démarre que sur un module actif ayant passé ses auto-tests, génère les clés par son intermédiaire, n'autorise un algorithme que si le module chargé l'approuve et refuse le reste (MD5, 3DES, scrypt, Argon2id, PKCS#12 hérité, NTLM), et un contrôle de disponibilité liste à l'avance ce qu'une instance perdrait. UCM n'est pas lui-même un module validé, et Debian 13 et arm64 ne font pas partie des configurations testées du certificat #5586
- **Profils de conformité** -- politiques par AC alignées sur l'ANSSI PG-083, le BSI TR-02102-1 et les mécanismes cryptographiques agréés de l'ECCG (types de clés, hachages, schémas de signature, horizons de validité, clés d'AC détenues par HSM, signataire d'horodatage EC), avec des refus là où le texte impose et des avertissements là où il recommande, et un contrôle préalable en lecture seule avant qu'un profil soit rattaché à une AC existante ; UCM n'est ni certifié ni qualifié par aucun de ces organismes
- **SBOM** -- un SBOM CycloneDX pour chaque paquet et chaque plateforme d'image de chaque version, lié au hachage du fichier ou au condensat de l'image, listant ce qu'elle embarque avec les versions et les licences déclarées, et ce qu'un paquet résout à l'installation ([docs/SBOM.md](docs/SBOM.md))
- **Durcissement** -- HSTS configurable par l'opérateur (Paramètres → Sécurité ou variable d'environnement), filtrage des en-têtes de certificat client par les proxys de confiance, permissions des clés d'API plafonnées à celles de leur créateur ; les proxys de confiance peuvent être donnés comme réseaux CIDR et, une fois la prise en charge des proxys activée, les en-têtes `X-Forwarded-*` ne sont acceptés que de leur part, si bien qu'un client qui atteint directement le serveur ne peut pas usurper son adresse ; l'interface web et l'API de gestion peuvent être **restreintes à des adresses IP et réseaux listés** tandis que les points d'accès des protocoles PKI restent joignables

### Exploitation et supervision
- **Vue d'ensemble** -- Quatre chiffres clés, étapes de première configuration et neuf cartes indépendantes (file de travail avec actions de renouvellement, de nouvelle tentative et de publication, santé de l'automatisation, émissions par source, horizon d'expiration, conformité, couverture des révocations, hiérarchie, dernières opérations, autorités et HSM), affichées, masquées et réordonnées avec des préréglages de disposition enregistrés par utilisateur, rechargées d'elles-mêmes quand les données changent
- **Rapports** -- Rapports PDF planifiés, synthèses de direction, certificats révoqués, modèles personnalisés
- **Boîte à outils de certificats** -- Vérificateur SSL, décodeur CSR/certificat, appariement de clés, convertisseur de formats
- **Notifications par e-mail** -- SMTP avec STARTTLS ou TLS implicite (port 465), **OAuth2 (XOAUTH2)** pour Gmail, Outlook.com et Microsoft 365, modèles HTML/texte personnalisables, alertes d'expiration des certificats avec plusieurs seuils en jours (un e-mail par seuil et par période de validité, dans le style 30/14/7/1), en laissant éventuellement de côté les certificats que les clients ACME renouvellent eux-mêmes
- **Crochets de déploiement** -- Pousser les certificats émis et renouvelés, et les CRL régénérées (DER ou bundle PEM avec les CRL parentes), vers des hôtes distants par SSH/SFTP, avec des chemins de destination et une commande de rechargement facultative par liaison : authentification par clé (ed25519 générée ou clé importée, chiffrée au repos), épinglage de la clé d'hôte à la première connexion, chemins de destination par liaison (certificat / clé / chaîne complète, la chaîne sans la racine auto-signée sauf si la liaison la demande, écrite de façon atomique), file d'envoi durable avec nouvelles tentatives et historique par envoi, un **préréglage même hôte** pour les services qui tournent à côté d'UCM, et des **cibles d'API HTTP** qui poussent un certificat vers un pare-feu, un répartiteur de charge ou une API cloud en une requête construite à partir d'un modèle de corps (URL, méthode, en-têtes chiffrés, variables de style `{{cert_pem|json}}`, clé privée seulement sur option explicite et en HTTPS vérifié)
- **Sauvegarde et restauration** -- Sauvegardes chiffrées manuelles et planifiées avec politiques de rétention et plafond facultatif de l'espace occupé par les archives conservées ; les archives sont des flux de blocs authentifiés indépendamment, si bien que les créer et les vérifier avant une restauration ne les garde pas entièrement en mémoire ; les archives contiennent les commandes du client ACME et les demandes en attente, se restaurent en mode fusion ou remplacement, associent les lignes par nom d'une installation à l'autre et rejouent les migrations de réparation
- **Lot de journaux de diagnostic** -- Téléchargement en un clic (Paramètres → À propos → Diagnostic) des journaux de l'application, du journal d'erreurs, du journal systemd et d'un diagnostic système sans secrets, sous forme de ZIP, avec les jetons sensibles masqués
- **Visionneuse de journaux système** -- Parcourir depuis l'interface les journaux de l'application, d'accès, d'erreurs et systemd, filtrés par niveau, plage horaire et texte, avec les secrets masqués
- **Métriques Prometheus** -- point d'accès `/metrics` facultatif, protégé par jeton bearer, qui expose des compteurs sur les certificats, les AC, le planificateur, les webhooks et ACME
- **Planificateur** -- vue d'administration des tâches de fond (contrôles d'expiration, actualisation des CRL, envoi des webhooks, sauvegardes, renouvellement automatique) avec état et exécution immédiate, dans un processus à part sous gunicorn
- **HTTPS auto-servi** -- appliquer n'importe quel certificat émis à l'interface web ; la liaison suit les renouvellements automatiquement (fichiers régénérés, service redémarré)
- **Valeurs réseau sûres par défaut** -- écoute double pile (`HOST=::` sert IPv6 et IPv4 sur une seule socket) et garde-fous sur l'URL de base de l'administration (contrôle d'accessibilité avant application, redirection canonique qui s'efface quand l'hôte ne se résout plus, variable de secours `UCM_DISABLE_CANONICAL_REDIRECT=1`)
- **Mises à jour logicielles** -- Vérificateur de mises à jour intégré avec installation en un clic, vérification quotidienne planifiée sur le canal stable ou release candidate, et installation sans surveillance facultative (DEB/RPM) avec vérification SHA256 obligatoire et événements de résultat fidèles (installé seulement une fois l'installation effective vérifiée par sa version), plus une fenêtre facultative de notes de version, une seule fois par utilisateur après une mise à jour
- **Recherche globale** -- Recherche transversale et palette de commandes (Ctrl+K)

### Plateforme
- **Thèmes** -- Atelier et Aurore, chacun en sombre ou en clair, ou selon le système ; **préférences par utilisateur conservées côté serveur** (langue, thème, mode)
- **i18n** -- 10 langues (EN, FR, DE, ES, IT, PT, UK, RU, ZH, JA)
- **État de l'interface conservé** -- Les filtres choisis persistent d'un rechargement à l'autre sur les principales pages de liste (certificats, AC, modèles, politiques, journaux d'audit, magasin de confiance, utilisateurs, SSH)
- **Base de données** -- SQLite (par défaut) ou **backend PostgreSQL natif** avec interface de migration bidirectionnelle
- **Interface adaptative** -- React 18 + Radix UI, adaptée au mobile
- **Inspecteur et fenêtres détachées** -- Chaque objet s'ouvre dans un inspecteur ancré avec un onglet par objet, ou détaché dans sa propre fenêtre qui reste d'une page à l'autre ; **Comparer** affiche deux à quatre certificats côte à côte, les lignes différentes étant marquées
- **Temps réel** -- Mises à jour en direct par WebSocket : une modification faite par un autre opérateur actualise les listes qui l'affichent, et une reconnexion après une coupure les recharge au lieu de laisser des lignes périmées à l'écran
- **Multiplateforme** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm), Kubernetes par le chart Helm (`oci://ghcr.io/neyslim/charts/ucm`) ; les paquets installent la rotation des journaux d'accès et d'erreurs
- **Prêt pour un reverse proxy** -- Ports publics indépendants des ports d'écoute (un `:80` ou `:443` explicite dans les URL de base est annoncé tel quel), proxys de confiance par IP ou réseau CIDR, et valeurs `proxy.*` du chart Helm pour un Ingress devant UCM

---

## Démarrage rapide

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

Disponible aussi sur GitHub Container Registry : `ghcr.io/neyslim/ultimate-ca-manager`. La variante FIPS est étiquetée `<version>-fips` (à lancer avec `UCM_FIPS=1`). Épinglez `3` (ou `3-fips`) pour ne suivre que les versions 3.x.

### Debian/Ubuntu

Téléchargez le paquet `.deb` depuis la [dernière version](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) :

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Téléchargez le paquet `.rpm` depuis la [dernière version](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) : `ucm-VERSION-1.fc43.noarch.rpm` pour Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` pour RHEL, Rocky Linux et AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` pour les mêmes distributions en version 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Accès :** `https://localhost:8443` ou `https://fqdn-de-votre-serveur:8443`
**Première connexion :** `admin`, avec le mot de passe généré au premier démarrage : `sudo cat /opt/ucm/data/initial-admin-password` (Docker : `docker exec <container> cat /opt/ucm/data/initial-admin-password`). Il doit être changé dès la première connexion. Voir [Premier accès](docs/installation/README.md#first-access) pour fournir le vôtre.

Voir le [guide d'installation](docs/installation/README.md) pour toutes les méthodes, y compris Docker Compose et l'installation depuis les sources.

---

## Documentation

| Ressource | Lien |
|-----------|------|
| Wiki (documentation complète) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Installation | [docs/installation/](docs/installation/README.md) |
| Guide utilisateur | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Guide d'administration | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| Clients du proxy ACME | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| Référence de l'API | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Sécurité | [docs/SECURITY.md](docs/SECURITY.md) |
| Guide de mise à jour | [UPGRADE.md](UPGRADE.md) |
| Journal des modifications | [CHANGELOG.md](CHANGELOG.md) |

---

## Pile technique

| Composant | Technologie |
|-----------|-------------|
| Frontend | React 18, Vite, Radix UI |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Base de données | SQLite ou PostgreSQL |
| Serveur | Gunicorn + gevent WebSocket |
| Cryptographie | pyOpenSSL, cryptography |
| Authentification | Cookies de session, WebAuthn/FIDO2, TOTP, mTLS |

---

## Emplacements des fichiers

| Élément | Chemin |
|---------|--------|
| Application | `/opt/ucm/` |
| Données et base | `/opt/ucm/data/` |
| Configuration (DEB/RPM) | `/etc/ucm/ucm.env` |
| Journaux (DEB/RPM) | `/var/log/ucm/` |
| Service | `systemctl status ucm` |

Docker : données dans `/opt/ucm/data/` (à monter en volume), configuration par variables d'environnement, journaux vers stdout.

---

## Contribuer

Les pull requests visent `dev`, et la première demande de signer une fois le
[CLA](CLA.md). Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le reste : comment
signaler utilement un bogue, à quoi ressemble une pull request relisable, et les règles sur
les tests, les traductions et les migrations.

---

## Licence

UCM est un logiciel libre sous [GNU AGPL v3.0 uniquement](LICENSE). L'exécuter, à n'importe quelle échelle et à titre commercial, ne coûte rien ; une [licence commerciale](COMMERCIAL-LICENSE.md) est proposée à ceux qui le modifient et ne peuvent pas publier leurs changements.

Les versions antérieures à la 2.243 restent sous leur licence d'origine, BSD 3-Clause avec la Commons Clause.

---

## Assistance

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

Si UCM vous est utile, pensez à soutenir son développement :

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
