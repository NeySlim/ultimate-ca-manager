# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&sort=semver&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/ucm)](https://artifacthub.io/packages/helm/ucm/ucm)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** é uma plataforma web de gerenciamento de autoridades certificadoras com suporte a protocolos PKI (ACME, SCEP, EST, OCSP, CRL/CDP), integração com o Microsoft ADCS, autenticação multifator e gerenciamento do ciclo de vida de certificados.

> **O UCM é um projeto jovem e em desenvolvimento ativo.** Comentários, relatos de bugs e pedidos de funcionalidades são muito bem-vindos! Fique à vontade para [abrir uma issue](https://github.com/NeySlim/ultimate-ca-manager/issues): cada relato ajuda a melhorar o UCM.

> Veja as [notas da última versão](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) e o [CHANGELOG](CHANGELOG.md) completo para saber o que há de novo.

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Funcionalidades

### Núcleo PKI
- **Gerenciamento de ACs** -- ACs raiz e intermediárias, visão da hierarquia, importação/exportação, **revogação de AC intermediária** (CRL e OCSP da AC superior, com o status "revogada na origem" abaixo dela), **ACs apenas com certificado** (uma AC assinada a partir de uma requisição externa, com a chave privada importada depois), **chaves de assinatura em HSM** (a chave privada nunca sai do HSM), **perfil RFC 5280 configurável** (algoritmo de hash da assinatura, Key Usage, EKU), possibilidade de **ocultar uma AC dos formulários de emissão** (uma raiz que só assina intermediárias) com padrões no estilo Let's Encrypt e um esquema de assinatura **RSA-PSS** opcional, **perfis de conformidade** alinhados à ANSSI, ao BSI e aos mecanismos acordados da UE, **ACs assinadas externamente** (o UCM gera o par de chaves e uma CSR do tipo AC, uma raiz offline/externa a assina: a chave privada nunca sai do UCM, com renovação por CSR com a mesma chave), **certificados de AC com assinatura cruzada** (anexar ou assinar de forma cruzada ao lado do certificado próprio da AC, servi-lo na cadeia padrão durante a troca de uma raiz, escolher a cadeia por exportação ou implantação, ver o que ainda encadeia até a raiz antiga), **restrições de nome da RFC 5280** definidas na criação (subárvores permitidas e excluídas de DNS, faixas de IP e e-mail, aplicadas em todos os caminhos de emissão), validade de 1 ano ou de qualquer número de dias até 50 anos, e uma regra opcional de **assunto único** (um certificado cujo assunto já pertence a outra entidade sob essa AC é recusado em todos os caminhos de emissão, RFC 5280 §4.1.2.6)
- **Ciclo de vida dos certificados** -- Emitir, assinar, revogar (com o motivo da RFC 5280, a partir de qualquer diálogo de revogação e em lote), renovar (**no local**: IDs estáveis entre renovações, números de série substituídos permanecem na CRL/OCSP até o vencimento original, com a validade escolhida ainda limitada pela política), renomear (nome de exibição editável, inclui certificados sem CN), exportar (PEM, DER, PKCS#12 com modo de compatibilidade 3DES/SHA-1 para Android 15 e anteriores, macOS 14 e anteriores, Windows e Java mais antigos, JKS; por padrão a cadeia omite a raiz autoassinada, com a opção **Incluir AC raiz** quando o destino de empacotamento ou importação a exige), operações em lote, filtro por status / emissor / origem (ACME, SCEP, EST, AD CS, importação…), incluindo os registros **arquivados** por uma renovação ou reinscrição e mantidos para o histórico, e um **comentário** em texto simples em cada certificado, encontrado pela lista e pela busca global
- **Verificação de conformidade (lint)** -- verificações por certificado contra a RFC 5280, os Baseline Requirements do CA/Browser Forum e a ETSI EN 319 412 via pkilint (e zlint quando disponível), apenas informativas
- **Gerenciamento de CSR** -- Criar, importar e assinar requisições de assinatura de certificado com **OIDs de EKU extras personalizados** (RFC 5280 §4.2.1.12), **validação tipada de SAN** (DNS / IP / E-mail / URI / UPN), curvas NIST P-256 / P-384 / P-521 e Brainpool P256r1 / P384r1 / P512r1, e um **caminho de retorno de AC externa**: um certificado emitido em outro lugar para uma CSR gerada no UCM conclui essa CSR na importação e mantém a chave privada; **nomes adicionados na assinatura** (o endereço de e-mail de uma requisição S/MIME de um smart card que traz apenas um CN, sob as mesmas restrições de nome, políticas e aprovação) e **assinar novamente** a partir do histórico, para dispositivos que não conseguem produzir a requisição duas vezes
- **Modelos de certificado** -- Perfis predefinidos para servidor, cliente, assinatura de código, e-mail e logon por smart card do Windows; tipos de chave RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool e **pós-quânticas ML-DSA-44/65/87** (Ed25519/Ed448 para ACs), **extensões X.509 personalizadas por OID**, **qcStatements (ETSI EN 319 412-5) e OIDs de política de certificado**, e valores padrão do assunto (e-mail incluído) preenchidos no formulário de emissão; exportação e importação JSON que preservam todas as configurações, um ou vários modelos por arquivo
- **Descoberta de certificados** -- Varredura de rede, perfis de varredura, varreduras agendadas, importação de certificados
- **Repositório de confiança** -- Gerencie certificados de ACs raiz confiáveis com alertas de vencimento e remoção em lote
- **Reparo de cadeia** -- Validação de cadeia baseada em AKI/SKI com agendador de reparo automático
- **Certificados SSH** -- Gerenciamento de autoridade certificadora SSH, assinatura de certificados de host/usuário, importação de ACs e certificados, ACs SSH com **chave em HSM** (RSA ou NIST ECDSA, a chave privada nunca sai do token), scripts de configuração compatíveis com curl; IDs de chave definidos pela AC (`principals@nome da AC`) ou deixados a cargo do solicitante

### Protocolos
- **ACME** -- RFC 8555, inscrição e renovação automáticas, desafios DNS-01/HTTP-01/TLS-ALPN-01, suporte a curingas, **identificadores IP (RFC 8738)**, **verificação CAA com vínculo a conta/método (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **arquivos de desafio HTTP-01 servidos pelo UCM** (encaminhe `/.well-known/acme-challenge/` a partir da porta 80, verificados antes do envio e renovados automaticamente), **escolha do resolvedor DNS-01** (automático, somente do sistema ou somente os resolvedores listados, para redes sem acesso a resolvedores públicos) para split-horizon, ACME em IPs internos/privados (incluindo upstream de loopback opcional para uma AC no mesmo host), **gerenciamento de várias ACs** (seleção da AC por requisição, fixada no pedido para que as renovações reutilizem a mesma AC: Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…), **CSR externa e reutilização da chave na renovação**, **simulação de pré-verificação em staging**, **proxy multi-AC** (domínios upstream pré-validados passam direto, endpoints por AC em `/acme/proxy/<slug>/directory`, incluindo revogação upstream), **cadeia de certificados preferida** (alternativas da RFC 8555 §7.4.2, por conta de AC), **perfis de certificado** (draft-ietf-acme-profiles: políticas de emissão nomeadas, anunciadas no diretório e selecionáveis por pedido, cada uma opcionalmente vinculada a um modelo de certificado cujo key usage e EKU passam a governar o certificado emitido, além de um **perfil padrão** e um digest de assinatura padrão para pedidos que não indicam nenhum), **gerenciamento de pedidos do servidor local** (visão de pedidos com limpeza e remoção agendada dos pedidos expirados); o proxy também publica os valores TXT dns-01 do lado do cliente para que as pré-verificações de propagação dos clientes (lego, Traefik, Caddy) passem sem ajustes, reutiliza o pedido ainda pendente de uma conta nas novas tentativas, e um **listener DNS UPDATE (RFC 2136)** opcional permite que solvers rfc2136 padrão, como o do cert-manager, respondam ao DNS-01 através do proxy com chaves TSIG por conta
- **SCEP** -- RFC 8894, inscrição automática de dispositivos com fluxos de aprovação, GetCert/GetCRL, GetNextCACert assinado, opcionalmente na porta HTTP simples para clientes como o sscep (fora do modo FIPS, que aceita apenas transporte de chave RSA-OAEP), renovações autenticadas pelo certificado do dispositivo, criptografia AES-128 com alternativa baseada em senha (PBKDF2) para clientes não RSA; uma requisição aprovada manualmente é emitida com o modelo do perfil pelo qual chegou, exatamente como na aprovação automática; perfis nomeados validam os desafios do **Microsoft Intune** na API do Intune do tenant, e dispositivos Windows (transporte de chave RSAES-OAEP) e Apple se inscrevem por eles, veja [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, incluindo geração de chave no servidor (CMS §4.4) e **rótulos de AC** (§3.2.2: atender várias ACs a partir de um único endpoint)
- **OCSP** -- RFC 6960, status de certificado em tempo real, requisições com vários certificados, suporte a nonce, validação de respondedor delegado com renovação automática do certificado do respondedor, validade de resposta configurável
- **TSA (RFC 3161)** -- autoridade de carimbo de tempo com OID de política configurável; assina com um **certificado de assinatura de entidade final dedicado** (RFC 3161, exigido por padrão e por verificadores estritos como `openssl ts -verify` e jarsigner), escolhido entre os certificados emitidos ou gerado com um clique (EKU timeStamping crítico e exclusivo); renovações acompanhadas automaticamente, cadeia do emissor incorporada nos tokens, modo estrito de assinante dedicado, saúde e vencimento do assinante exibidos na visão geral
- **CRL/CDP** -- Distribuição de listas de revogação de certificados com suporte a Delta CRL (RFC 5280 §5.2.4), agenda por AC (validade desacoplada da cadência de publicação) e digest de assinatura configurável, URLs nomeadas opcionais (slug com o nome da AC nos caminhos CDP/AIA, pode ser ativado em ACs existentes), **envio de CRL assinada externamente para ACs offline / sem chave** (validada contra o certificado da AC com monotonicidade do número da CRL, servida no endpoint CDP existente e consultada pelo OCSP)
- **AIA CA Issuers** -- Download do certificado da AC por Authority Information Access (RFC 5280 §4.2.2.1)

### Integrações
- **Microsoft ADCS** -- Ciclo de vida completo sobre o AD CS: assinatura de CSR, descoberta de modelos, EOBO (Enroll On Behalf Of), renovação/revogação pelo conector e um canal administrativo WinRM opcional para sincronização de revogações da CRL, importação do inventário de ACs e aprovação/negação de requisições pendentes, com um painel de saúde da AC
- **Inscrição automática do Windows e Active Directory Connector** -- Política e inscrição MS-XCEP/WSTEP para máquinas e usuários ingressados no domínio, sob o modelo indicado na requisição; no vínculo Kerberos, os modelos de máquina e derivados do AD obtêm o assunto do Active Directory (o nome de host DNS do computador, ou o DN e o UPN do usuário), em vários controladores de domínio com failover e uma verificação de saúde agendada por DC, nunca com bind anônimo; a inscrição é configurada em **perfis por realm** (`/api/v2/windows-profiles`), cada um com sua própria AC, modelos, keytab Kerberos, grupo do AD e conector, e uma requisição Kerberos é atendida pelo perfil habilitado do realm do seu principal (o vínculo UsernamePassword pelo perfil padrão, quando habilitado, uma renovação vinculada a certificado pelo perfil registrado no certificado apresentado), com **vários conectores do Active Directory** (um por floresta ou domínio)
- **Microsoft Intune** -- Validação de desafios SCEP para dispositivos gerenciados pelo Intune, registros de aplicativo do Entra definidos uma só vez em SCEP › Registros de aplicativo do Intune e escolhidos por perfil, com um guia passo a passo em `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM incluído, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit; **ACs em HSM** com chaves de assinatura não exportáveis, RSA-PSS e Brainpool em PKCS#11, e uma certificação de dispositivo declarada (Common Criteria, EUCC, FIPS 140-3) verificada pelo perfil de conformidade da UE; um teste de conexão mostra o que um módulo PKCS#11 informa (biblioteca, fabricante, firmware)
- **Kubernetes / cert-manager** -- Manifestos de referência para ClusterIssuer (HTTP-01 + DNS-01 com EAB), Certificate de exemplo e modelo de Secret em `examples/kubernetes/cert-manager/`
- **Provedores de DNS** -- Cloudflare, Route53, Azure DNS, Plesk e outros para desafios ACME DNS-01
- **Webhooks** -- Notificações orientadas a eventos do ciclo de vida de certificados (mais de 15 tipos de evento), **histórico de entregas por endpoint com nova tentativa manual**, fila de entrega assíncrona durável com backoff exponencial e uma janela de retenção do histórico para que ele não cresça indefinidamente

### Segurança e acesso
- **Autenticação** -- Senha, WebAuthn/FIDO2 (também como segundo fator, junto com o TOTP ou no lugar dele), TOTP 2FA, mTLS, chaves de API (`X-API-Key` ou `Authorization: Bearer`)
- **Bloqueio de sessão** -- Bloqueie a sessão pelo menu da conta ou com Alt+Shift+L: todas as abas são bloqueadas e o servidor a mantém bloqueada até que a própria conta a desbloqueie com sua senha, certificado de cliente ou passkey
- **SSO** -- LDAP (LDAPS ou StartTLS), OAuth2 (Azure/Google/GitHub), SAML single sign-on com Single Logout, mapeamento de papéis para papéis internos e **papéis personalizados** (grupos SAML lidos da asserção, incluindo claims do Entra ID e do AD FS) e formato de NameID configurável; **rastreamento de `auth_source` por usuário** e sincronização de papéis no login por adesão; login **multi-tenant do Microsoft Entra** com uma lista de tenants aceitos, um **login de teste** que mostra a identidade, os grupos e o papel que um provedor daria antes de ser ativado, e uma conta que **vários provedores** podem abrir
- **RBAC** -- 4 papéis internos (Admin, Operator, Auditor, Viewer) mais papéis personalizados com permissões granulares; **grupos concedem permissões adicionais** além do papel do usuário (nunca de administrador)
- **Políticas e aprovações** -- Políticas de emissão de certificados com fluxos de aprovação e regras aplicadas (tipos de chave e hashes de assinatura permitidos, limite de SANs DNS, limite de validade, com escopo por AC, modelo ou padrão de DNS), valendo para **todos os caminhos do operador** (o formulário de emissão, a assinatura de uma requisição armazenada individualmente ou em lote, e a renovação) e, para tipos de chave e hashes, também para ACME, SCEP, EST, WSTEP e a criação de ACs; uma política que exige aprovação mantém as **requisições ACME, EST, SCEP e WSTEP** na fila de aprovação, e cada cliente é informado nos termos do seu protocolo (ACME `processing`, EST 202 com Retry-After, SCEP PENDING, WSTEP pending); uma política também pode submeter **revogações e renovações** à aprovação; uma requisição na fila é encerrada sozinha quando seu alvo é assinado, renovado, excluído ou revogado nesse meio-tempo
- **Padrões de chave e hash** -- Uma requisição que não indica chave nem hash segue um único padrão em todos os caminhos de emissão (RSA-2048 com SHA-256, a menos que um perfil ou uma política o recuse, então o primeiro tipo aceito), o hash acompanha a chave de assinatura, e uma nova AC intermediária nunca recebe um hash inferior ao da sua AC superior
- **Logs de auditoria** -- Registro de ações com verificação de integridade, encaminhamento remoto por syslog e período de retenção opcional
- **Criptografia de chaves privadas** -- AES-128 (Fernet, HMAC-SHA256) em repouso sob uma chave mestra criada na primeira inicialização (em um contêiner, quando `/etc/ucm` é um volume) ou fornecida como `KEY_ENCRYPTION_KEY`, cobrindo chaves de ACs e de certificados, chaves de ACs SSH e de destinos de implantação, chaves de conta ACME e EAB, desafios SCEP e senhas de bind LDAP, com **Criptografar chaves restantes** para segredos armazenados antes da ativação; com a criptografia ativada, nenhum arquivo de chave em texto simples é mantido em disco (os espelhos existentes são removidos na ativação e na inicialização, os arquivos de certificado públicos permanecem), e os arquivos de chave são recriados quando ela é desativada
- **Alta disponibilidade** -- Execute dois ou mais nós em um único banco PostgreSQL com `UCM_HA=1` (Docker, Docker Compose, DEB/RPM ou `ha.enabled` do chart Helm): um nó eleito executa as tarefas agendadas, alterações de configurações e de criptografia chegam a todos os nós, backups e restaurações funcionam a partir de qualquer nó, e as atualizações de pacotes são feitas um nó por vez, e as sessões são compartilhadas, de modo que apenas os endpoints de inscrição Kerberos exigem afinidade por endereço de origem (veja [docs/HA.md](docs/HA.md))
- **Modo FIPS** -- a imagem Docker `-fips` executa a criptografia do UCM no OpenSSL FIPS Provider 3.5.9 (certificado CMVP #5586), que aprova ML-DSA, Ed25519 e Ed448, de modo que assinaturas pós-quânticas e EdDSA estão disponíveis no modo FIPS com a imagem; os pacotes DEB e RPM construídos com `UCM_FIPS_BUILD=1` rodam no módulo FIPS do RHEL 9 (#5573) ou do Ubuntu 24.04 Pro (#5115), que não os oferecem. Com `UCM_FIPS=1`, o UCM só inicia sobre um módulo ativo e autotestado, gera chaves por meio dele, permite um algoritmo somente quando o módulo carregado o aprova e recusa o restante (MD5, 3DES, scrypt, Argon2id, PKCS#12 legado, NTLM), e uma verificação de prontidão lista de antemão o que uma instância perderia. O UCM em si não é um módulo validado, e o Debian 13 e o arm64 não estão entre as configurações testadas do certificado #5586
- **Perfis de conformidade** -- políticas por AC alinhadas à ANSSI PG-083, ao BSI TR-02102-1 e aos mecanismos criptográficos acordados do ECCG (tipos de chave, hashes, esquemas de assinatura, horizontes de validade, chaves de AC em HSM, assinante de timestamp EC), com recusas onde o texto impõe e avisos onde ele recomenda, e uma pré-verificação somente leitura antes de anexar um perfil a uma AC existente; o UCM não é certificado nem qualificado por nenhum desses órgãos
- **SBOM** -- um SBOM CycloneDX para cada pacote e plataforma de imagem de cada versão, vinculado ao hash do arquivo ou ao digest da imagem, listando o que ela traz com versões e licenças declaradas e o que um pacote resolve na instalação ([docs/SBOM.md](docs/SBOM.md))
- **Hardening** -- HSTS configurável pelo operador (Configurações → Segurança ou variável de ambiente), controle de proxies confiáveis para os cabeçalhos de certificado de cliente, permissões de chave de API limitadas às do próprio criador; os proxies confiáveis podem ser informados como redes CIDR e, com o suporte a proxy ativado, os cabeçalhos `X-Forwarded-*` só são aceitos deles, de modo que um cliente que alcança o backend diretamente não consegue falsificar seu endereço; a interface web e a API de gerenciamento podem ser **restritas a endereços IP e redes listados**, enquanto os endpoints dos protocolos PKI continuam acessíveis

### Operações e monitoramento
- **Visão geral** -- Quatro números principais, etapas de configuração da primeira execução e nove cartões independentes (fila de trabalho com ações de renovar, tentar novamente e publicar, saúde da automação, emissões por origem, horizonte de vencimento, conformidade, cobertura de revogação, hierarquia, últimas operações, autoridades e HSM), exibidos, ocultados e reordenados com predefinições de layout salvas por usuário, recarregados sozinhos quando os dados mudam
- **Relatórios** -- Relatórios PDF agendados, resumos executivos, certificados revogados, modelos personalizados
- **Caixa de ferramentas de certificados** -- Verificador de SSL, decodificador de CSR/certificado, comparador de chaves, conversor de formatos
- **Notificações por e-mail** -- SMTP com STARTTLS ou TLS implícito (porta 465), **OAuth2 (XOAUTH2)** para Gmail, Outlook.com e Microsoft 365, modelos HTML/texto personalizáveis, alertas de vencimento de certificados com vários limites em dias (um e-mail por limite e período de validade, no estilo escalonado 30/14/7/1), com a opção de deixar de fora os certificados que os clientes ACME renovam sozinhos
- **Deploy Hooks** -- Envie certificados emitidos e renovados, e CRLs regeneradas (DER ou um bundle PEM com as CRLs superiores), a hosts remotos por SSH/SFTP, com caminhos de destino e um comando de recarga opcional por vínculo: autenticação por chave (ed25519 gerada ou chave importada, criptografada em repouso), fixação da chave do host na primeira conexão, caminhos de destino por vínculo (certificado / chave / cadeia completa, a cadeia sem a raiz autoassinada, a menos que o vínculo a peça, gravados de forma atômica), fila de entrega durável com novas tentativas e histórico por entrega, uma **predefinição para o mesmo host** para serviços executados ao lado do UCM, e **destinos de API HTTP** que enviam um certificado a um firewall, balanceador de carga ou API de nuvem em uma única requisição montada a partir de um modelo de corpo (URL, método, cabeçalhos criptografados, variáveis no estilo `{{cert_pem|json}}`, chave privada somente com adesão explícita por HTTPS verificado)
- **Backup e restauração** -- Backups criptografados manuais e agendados com políticas de retenção e um limite opcional para o espaço ocupado pelos arquivos armazenados; os arquivos são fluxos de blocos autenticados de forma independente, então criá-los e verificá-los antes de uma restauração não os mantém inteiros na memória; os arquivos incluem pedidos de cliente ACME e requisições pendentes, restauram em modo de mesclagem ou substituição, associam linhas por nome entre instalações e reaplicam as migrações de reparo
- **Pacote de logs de diagnóstico** -- Download com um clique (Configurações → Sobre → Diagnóstico) dos logs da aplicação, do log de erros, do journal do systemd e de um diagnóstico do sistema sem segredos, em um ZIP, com tokens sensíveis ocultados
- **Visualizador de logs do sistema** -- Navegue pelos logs da aplicação, de acesso, de erros e do journal do systemd na interface, filtrados por nível, janela de tempo e texto, com segredos ocultados
- **Métricas do Prometheus** -- endpoint `/metrics` opcional, protegido por bearer, que expõe contadores de certificados, ACs, agendador, webhooks e ACME
- **Agendador** -- visão administrativa das tarefas em segundo plano (verificações de vencimento, atualização de CRL, entrega de webhooks, backups, renovação automática) com status e execução imediata, executado em um processo próprio sob o gunicorn
- **HTTPS autoatendido** -- aplique qualquer certificado emitido à interface web; o vínculo acompanha as renovações automaticamente (arquivos regravados, serviço reiniciado)
- **Padrões de rede seguros** -- escuta dual-stack (`HOST=::` atende IPv6 e IPv4 em um único socket) e salvaguardas da Base URL administrativa (verificação de alcançabilidade antes de aplicar, o redirecionamento canônico se afasta quando o host deixa de resolver, chave de recuperação `UCM_DISABLE_CANONICAL_REDIRECT=1`)
- **Atualizações de software** -- Verificador de atualizações integrado com instalação em um clique, verificação diária agendada em um canal estável ou de release candidate e instalação autônoma opcional (DEB/RPM) com verificação SHA256 obrigatória e eventos de resultado fiéis (instalado somente depois que a instalação real é verificada pela versão), além de uma janela opcional, uma única vez por usuário, com as notas da versão após uma atualização
- **Busca global** -- Busca entre recursos e paleta de comandos (Ctrl+K)

### Plataforma
- **Temas** -- Atelier e Aurore, cada um escuro ou claro, ou seguindo o sistema; **preferências por usuário persistidas no servidor** (idioma, tema, modo)
- **i18n** -- 10 idiomas (EN, FR, DE, ES, IT, PT, UK, RU, ZH, JA)
- **Estado da interface persistido** -- As seleções de filtro persistem entre recarregamentos nas principais páginas de lista (certificados, ACs, modelos, políticas, logs de auditoria, repositório de confiança, usuários, SSH)
- **Banco de dados** -- SQLite (padrão) ou **backend PostgreSQL nativo** com interface de migração bidirecional
- **Interface responsiva** -- React 18 + Radix UI, adequada a dispositivos móveis
- **Inspetor e janelas destacadas** -- Cada objeto abre em um inspetor acoplado com uma aba por objeto, ou destacado em uma janela própria que permanece entre as páginas; **Comparar** mostra de dois a quatro certificados lado a lado, com as linhas diferentes marcadas
- **Tempo real** -- Atualizações ao vivo por WebSocket: uma alteração feita por outro operador atualiza as listas que a exibem, e uma reconexão após uma queda as recarrega em vez de deixar linhas obsoletas na tela
- **Multiplataforma** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm), Kubernetes pelo chart Helm (`oci://ghcr.io/neyslim/charts/ucm`); os pacotes instalam a rotação de logs para os logs de acesso e de erros
- **Pronto para proxy reverso** -- Portas públicas independentes das portas de escuta (um `:80` ou `:443` explícito nas URLs base é anunciado como digitado), proxies confiáveis por IP ou rede CIDR e valores `proxy.*` do chart Helm para um Ingress na frente do UCM

---

## Início rápido

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

Também disponível no GitHub Container Registry: `ghcr.io/neyslim/ultimate-ca-manager`. A variante FIPS recebe a tag `<version>-fips` (execute-a com `UCM_FIPS=1`). Fixe `3` (ou `3-fips`) para acompanhar apenas as versões 3.x.

### Debian/Ubuntu

Baixe o pacote `.deb` da [última versão](https://github.com/NeySlim/ultimate-ca-manager/releases/latest):

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Baixe o pacote `.rpm` da [última versão](https://github.com/NeySlim/ultimate-ca-manager/releases/latest): `ucm-VERSION-1.fc43.noarch.rpm` para Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` para RHEL, Rocky Linux e AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` para as mesmas distribuições na versão 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Acesso:** `https://localhost:8443` ou `https://your-server-fqdn:8443`
**Primeiro login:** `admin`, com a senha gerada na primeira inicialização: `sudo cat /opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat /opt/ucm/data/initial-admin-password`). Ela deve ser alterada no primeiro login. Veja [Primeiro acesso](docs/installation/README.md#first-access) para definir a sua.

Veja o [Guia de instalação](docs/installation/README.md) para todos os métodos, incluindo Docker Compose e instalação a partir do código-fonte.

---

## Documentação

| Recurso | Link |
|----------|------|
| Wiki (documentação completa) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Instalação | [docs/installation/](docs/installation/README.md) |
| Guia do usuário | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Guia do administrador | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| Clientes do proxy ACME | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| Referência da API | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Segurança | [docs/SECURITY.md](docs/SECURITY.md) |
| Guia de atualização | [UPGRADE.md](UPGRADE.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

---

## Pilha tecnológica

| Componente | Tecnologia |
|-----------|------------|
| Frontend | React 18, Vite, Radix UI |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Banco de dados | SQLite ou PostgreSQL |
| Servidor | Gunicorn + gevent WebSocket |
| Criptografia | pyOpenSSL, cryptography |
| Autenticação | Cookies de sessão, WebAuthn/FIDO2, TOTP, mTLS |

---

## Locais de arquivos

| Item | Caminho |
|------|------|
| Aplicação | `/opt/ucm/` |
| Dados e banco | `/opt/ucm/data/` |
| Configuração (DEB/RPM) | `/etc/ucm/ucm.env` |
| Logs (DEB/RPM) | `/var/log/ucm/` |
| Serviço | `systemctl status ucm` |

Docker: dados em `/opt/ucm/data/` (monte como volume), configuração por variáveis de ambiente, logs na saída padrão (stdout).

---

## Contribuindo

Os pull requests têm como alvo `dev`, e o primeiro pede que você assine o
[CLA](CLA.md) uma única vez. Veja o [CONTRIBUTING.md](CONTRIBUTING.md) para o restante: como
relatar um bug de forma útil, como é um pull request revisável e as regras sobre
testes, traduções e migrações.

---

## Licença

O UCM é software livre sob a [GNU AGPL v3.0 only](LICENSE). Executá-lo, em qualquer escala e comercialmente, não custa nada; uma [licença comercial](COMMERCIAL-LICENSE.md) está disponível para quem o modifica e não pode publicar suas alterações.

As versões anteriores à 2.243 permanecem sob a licença original, BSD 3-Clause com a Commons Clause.

---

## Suporte

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

Se você acha o UCM útil, considere apoiar o seu desenvolvimento:

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
