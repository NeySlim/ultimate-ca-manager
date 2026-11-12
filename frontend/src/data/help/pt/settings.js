export default {
  helpContent: {
    title: 'Configurações',
    subtitle: 'Configuração do sistema',
    overview: 'Configure todos os aspectos do sistema UCM. As configurações são organizadas por categoria: geral, aparência, e-mail, segurança, SSO, backup, auditoria, banco de dados, HTTPS, atualizações e webhooks.',
    sections: [
      {
        title: "Métricas Prometheus",
        content: "Endpoint /metrics opcional que expõe contadores (certificados, CA, agendador, webhooks, ACME) em formato Prometheus.",
        items: [
          { label: "Ativação", text: "Defina um token de métricas em Definições › Geral; sem token, o endpoint retorna 404 (desativado)" },
          { label: "Autenticação", text: "Faça scrape com Authorization: Bearer <token>" },
          { label: "Contadores", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Vhost ACME público",
        content: "Definições › Geral: hostname e porta públicos para URL do diretório ACME atrás de um reverse proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com, GUI e API (mTLS conforme política)" },
          { label: "ACME", text: "acme.ucm.example.com, /acme/* e /acme/proxy/* (sem mTLS de cliente)" },
          { label: "TLS wildcard", text: "Hostname concreto (ex.: acme.ucm.example.com). Um SAN *.ucm.example.com no certificado cobre TLS de admin e ACME, não use *.ucm.example.com como vhost" },
          { label: "Antes de salvar", text: "Tenha DNS e TLS prontos para o vhost ACME, clientes mudam as URL do diretório imediatamente" },
          { label: "ID certificado TLS", text: "Metadados do certificado no vhost ACME (ex. wildcard)" },
        ]
      },
      {
        title: "Histórico de entrega de webhooks",
        content: "Cada endpoint de webhook mantém um registo de entrega com estado, tentativas e nova tentativa manual.",
        items: [
          { label: "Estados", text: "pending / delivered / failed, com o último código HTTP e erro" },
          { label: "Repetir", text: "Recolocar manualmente em fila um evento falhado ou já entregue" },
          { label: "Assíncrono", text: "As entregas partem de uma fila durável com recuo exponencial (até 5 tentativas)" },
        ]
      },
      {
        title: "Vista do agendador",
        content: "Definições › Agendador lista as tarefas em segundo plano com o seu estado e última execução.",
        items: [
          { label: "Tarefas", text: "Verificações de expiração, atualização de CRL, entrega de webhooks, backups agendados, renovação automática, etc." },
          { label: "Executar agora", text: "Acionar qualquer tarefa a pedido" },
          { label: "Visibilidade", text: "Última execução, última duração e número de falhas por tarefa" },
          { label: "Processo do agendador (v2.251)", text: "As tarefas rodam num processo próprio do agendador, iniciado com o serviço e reiniciado em poucos segundos após uma falha ou um reload, de modo que uma tarefa longa não atrasa nem pedidos nem workers. Ocupa cerca de 150 MB de memória" },
          { label: "Estado desatualizado (v2.251)", text: "Quando o processo do agendador não reporta há algum tempo, o separador avisa que o estado mostrado pode estar desatualizado" },
          { label: "Tarefas longas (v2.251)", text: "Executar agora espera até 30 segundos pelo resultado. Uma tarefa ainda em curso nesse momento é indicada como iniciada e ainda em execução, e o seu resultado aparece numa atualização posterior" },
        ]
      },
      {
        title: "Backups agendados",
        content: "Backups automáticos e cifrados da base de dados, com cadência configurável e retenção.",
        items: [
          { label: "Cadência", text: "Diária / semanal / mensal" },
          { label: "Retenção", text: "Os backups mais antigos que o número de dias definido (30 por padrão) são removidos" },
          { label: "Cifragem", text: "Os backups são cifrados com a palavra-passe de backup configurada" },
          { label: "Derivação de chave", text: "Automática (Argon2id quando disponível, PBKDF2 no modo FIPS), PBKDF2-HMAC-SHA256 ou Argon2id. Os arquivos gravados com Argon2id não podem ser restaurados numa instância em modo FIPS" },
        ]
      },
      {
        title: 'Restauração (v2.251)',
        items: [
          { label: 'Substituir ou mesclar', text: 'Restore from Backup substitui os dados daqui pelos do arquivo e remove o que o arquivo não contém; a entrada de auditoria lista o que foi removido. A API também aceita mode=merge, que adiciona o arquivo aos dados daqui' },
          { label: 'Bloqueio compartilhado', text: 'Backups e restaurações compartilham um só bloqueio: uma restauração é recusada (409) enquanto um backup está em curso, e um backup manual espera por uma restauração em curso' },
          { label: 'Limite de envio', text: 'Uma restauração aceita um arquivo de até BACKUP_MAX_UPLOAD_MB (512 MB por padrão), definido no ambiente do servidor, e a recusa indica essa configuração. Um reverse proxy à frente do UCM mantém o seu próprio limite de corpo' },
          { label: 'O que um arquivo contém', text: 'Os arquivos incluem pedidos do cliente ACME, pedidos de aprovação e pedidos de recuperação de chaves. Restaurar um arquivo gravado antes desta versão deixa essas linhas daqui como estão' },
          { label: 'Mesmos nomes', text: 'Um provedor DNS, conta CA ACME ou webhook cujo nome outra linha já tem aqui é restaurado como "nome (2)", e o resultado da restauração devolvido pela API o lista' },
          { label: 'Configurações que nomeiam uma linha', text: 'As CAs emissoras de SCEP e ACME, os responders OCSP e configurações semelhantes seguem as linhas do arquivo. Num arquivo mais antigo restaurado noutra instalação, ficam vazias e devem ser escolhidas de novo' },
        ]
      },
      {
        title: 'Atualizações automáticas (v2.215)',
        content: 'Definições › Atualizações: uma verificação diária em segundo plano de novas versões e uma instalação não assistida opcional.',
        items: [
          { label: "Canal", text: "Stable segue apenas as releases finais; Release candidates aceita adicionalmente somente versões rcN, nunca alfa/beta" },
          { label: 'Notificação', text: 'Uma nova versão disponível dispara o evento webhook/e-mail system.update_available, uma vez por versão' },
          { label: 'Instalação automática', text: 'Desativada por padrão. Quando ativada, o UCM baixa, verifica e instala a atualização na hora escolhida e depois reinicia, apenas instalações DEB/RPM' },
          { label: 'Checksum', text: 'Uma instalação não assistida exige o SHA256 publicado da release para verificação; uma instalação manual também verifica sempre que um checksum é publicado' },
          { label: 'Docker', text: 'Os containers não podem se atualizar sozinhos, a verificação e a notificação continuam funcionando; faça pull da nova imagem para atualizar' },
          { label: 'Popup pós-atualização', text: 'Opcional (v2.217): mostra uma vez as notas da versão após a instalação de uma atualização, por utilizador. Desativado por predefinição' },
        ]
      },
      {
        title: "HSTS (Strict Transport Security)",
        content: "Política HSTS configurável pelo operador para que instâncias com certificados autoassinados durante a configuração inicial possam se excluir totalmente.",
        items: [
          { label: "Padrão", text: "HSTS ativado, includeSubDomains, max-age 1 ano (compatível com versões anteriores)" },
          { label: "Desativar", text: "Desative para instâncias com certificados autoassinados durante a configuração inicial (evita bloqueio do navegador)" },
          { label: "Variável de ambiente", text: "UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE em /etc/ucm/ucm.env prevalecem sobre o BD" },
          { label: "Subdomínios", text: "Remover includeSubDomains quando os subdomínios hospedarem serviços separados com certificados próprios" },
        ]
      },
      {
        title: 'Categorias',
        items: [
          { label: 'Geral', text: 'Nome de host do syslog (enviado como HOSTNAME nas mensagens syslog encaminhadas), URLs base e padrões do sistema' },
          { label: 'Aparência', text: 'Seleção de tema (claro/escuro/sistema), cor de destaque, modo desktop' },
          { label: 'E-mail (SMTP)', text: 'Servidor SMTP, credenciais, editor de modelo de e-mail e notificações de alerta de expiração' },
          { label: 'Segurança', text: 'Política de senha, duração da sessão, lista de acesso administrativo, mTLS, criptografia de chaves privadas; o tempo limite de inatividade e o bloqueio de conta estão em Geral' },
          { label: 'SSO', text: 'Integração de login único SAML 2.0, OAuth2/OIDC e LDAP' },
          { label: 'Backup', text: 'Backups manuais e agendados do banco de dados' },
          { label: 'Auditoria', text: 'Retenção de logs, encaminhamento syslog, verificação de integridade' },
          { label: 'Banco de Dados', text: 'Backend ativo (SQLite ou PostgreSQL), tamanho, número de tabelas, testar/alternar/migrar entre backends' },
          { label: 'Esquema PostgreSQL (v2.251)', text: 'Uma URL PostgreSQL cujo search_path indica um esquema diferente de public é suportada: a verificação de integridade conta as tabelas desse esquema, e uma migração para ele realinha as suas sequências' },
          { label: 'HTTPS', text: 'Certificado TLS para a interface web do UCM. O certificado aplicado é lembrado e reaplicado quando é renovado (v2.217); o certificado vinculado é exibido com um botão de desvinculação para deixar de seguir as renovações (v2.218)' },
          { label: 'Atualizações', text: 'Verificar novas versões, visualizar changelog, verificação diária agendada com instalação não assistida opcional (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP para eventos de certificado (emissão, revogação, expiração). Autenticação de saída opcional: Bearer, Basic, API key ou cabeçalho personalizado' },
          { label: 'Nomes de webhook únicos (v2.251)', text: 'Um nome de webhook já em uso é recusado (409), na criação e ao renomear. A atualização renomeou os duplicados anteriores para "nome (2)", "nome (3)", do mais antigo ao mais recente' },
          { label: 'Implantação', text: 'Os alvos de implantação fornecem conexões SSH/SFTP reutilizáveis, ou uma requisição a uma API HTTP (v2.252); as implantações de certificado e de CRL definem seus próprios caminhos e comandos de recarga opcionais (somente admin, v2.215)' },
          { label: 'Active Directory', text: 'Conexão própria do UCM com AD/LDAP para consultas relacionadas a certificados (resolução de entidade de segurança Kerberos, assuntos derivados do AD)' },
          { label: 'Autoinscrição do Windows', text: 'Inscrição nativa do Windows MS-XCEP/MS-WSTEP: descoberta de diretiva, emissão de certificados e vinculação Kerberos/SPNEGO' },
          { label: 'Sobre', text: 'Informações do sistema, Links e recursos e Apoiar o UCM levam ao Ko-fi (os administradores também veem um cartão Ko-fi dispensável uma vez por versão do UCM). Com admin:system, Verificar preparação para FIPS lista o que o modo FIPS recusaria nesta instância, com um remédio para cada item, e não altera nada' },
          { label: 'Perfis de conformidade', text: 'Em Sobre, com admin:system: Verificar perfil lista o que ANSSI, BSI ou EU ACM (regras alinhadas com um texto de referência) recusariam ou desaconselhariam nesta instância, sem alterar nada. Com admin:settings, Perfil predefinido para novas CAs define o perfil que uma CA recebe quando nenhum é escolhido; as CAs existentes não são alteradas' },
        ]
      },
      {
        title: 'Hooks de implantação (v2.215)',
        content: 'Configurações › Implantação (somente admin): conexões SSH/SFTP reutilizáveis, ou requisições a uma API HTTP, para as implantações de certificados e de CRL. Os caminhos e o comando de recarga opcional são configurados em cada implantação SSH.',
        items: [
          { label: 'Alvo', text: 'Host, porta, usuário SSH. O UCM gera uma chave ed25519 (instale a chave pública exibida no alvo) ou aceita uma chave privada importada, armazenada criptografada' },
          { label: 'Alvo de API HTTP (v2.252)', text: "URL, método (POST, PUT, PATCH), cabeçalhos da requisição armazenados criptografados e nunca exibidos novamente, e um modelo de corpo com {{cert_pem}}, {{fullchain_pem}}, {{cn}}, {{serial}}... mais os filtros |json, |jsonstr, |b64 e |urlencode. Um corpo JSON é validado ao salvar. A chave privada ({{key_pem}}) só sai com a autorização explícita do alvo e uma URL https; o certificado TLS é sempre verificado, contra uma âncora de confiança colada se o appliance for autoassinado. Redirecionamentos são recusados, endereços de metadados de nuvem e de loopback bloqueados. Somente certificados: as CRLs permanecem nos alvos SSH" },
          { label: 'Host key', text: 'Fixada na primeira conexão bem-sucedida (trust-on-first-use); qualquer mudança posterior falha de forma segura. Alterar o host refaz a fixação' },
          { label: 'Comando de recarga', text: 'Um comando opcional, configurado em cada vínculo de certificado ou de CRL e executado após um envio bem-sucedido (ex.: systemctl reload nginx): exit 0 = sucesso, sem templating' },
          { label: 'Vínculos', text: 'Os certificados são anexados a partir da visão de detalhe do certificado; as CRLs, em CRL e OCSP. Cada vínculo tem seus próprios caminhos, opções de arquivo e comando de recarga' },
          { label: 'Entrega', text: 'Os envios são executados de forma assíncrona por uma fila durável com tentativas e backoff; status por entrega, implantar agora e repetir manualmente, trilha de auditoria completa' },
          { label: 'Privilégio mínimo', text: 'Use uma conta SSH dedicada em cada alvo: acesso de escrita aos caminhos dos certificados e permissão para recarregar o serviço, nada mais' },
        ]
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content: 'Autenticação OAuth2 moderna para correio de saída, substituindo os fluxos legados de app-password que Microsoft e Google estão depreciando:',
        items: [
          { label: 'Gmail', text: 'Configurar um cliente OAuth2 do Google Cloud com escopo https://mail.google.com/' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Registrar um app Azure AD com permissão delegada SMTP.Send' },
          { label: 'Refresh tokens', text: 'UCM armazena o refresh token e renova access tokens automaticamente antes de cada envio' },
          { label: 'Fallback', text: 'A autenticação por senha continua suportada quando OAuth2 não está configurado' },
        ]
      },
      {
        title: 'Conector do Active Directory',
        content: 'Conexão LDAP própria do UCM com o Active Directory, independente de qualquer provedor LDAP configurado em SSO -- aquele serve para fazer login no UCM, este para consultas de AD relacionadas a certificados.',
        items: [
          { label: 'Finalidade', text: 'Resolve uma entidade de segurança de máquina ou usuário Kerberos para seu objeto AD, para que o UCM possa derivar um assunto/SAN de certificado, da mesma forma que uma CA Windows real faria' },
          { label: 'Campos', text: 'Controladores de domínio (um por linha, cada um pelo seu próprio nome de host, tentados em ordem com failover), porta, LDAPS com verificação de CA opcional, DN Base, DN de Ligação e senha (ambos obrigatórios enquanto o conector estiver ativado)' },
          { label: 'Testar conexão', text: 'Verificar a conectividade e as credenciais antes de salvar' },
          { label: 'URLs de inscrição GPO', text: 'URLs de diretiva de inscrição de certificados Kerberos e Usuário/Senha para registrar na Diretiva de Grupo' },
          { label: 'Verificação de integridade', text: 'Cada controlador de domínio é testado com uma conexão real no Intervalo da verificação de integridade; um inacessível é ignorado no momento da inscrição até se recuperar. O veredito aparece na linha das definições e em cada DC' },
        ]
      },
      {
        title: 'Autoinscrição do Windows (XCEP/WSTEP)',
        content: 'Inscrição de certificados nativa do Windows via descoberta de diretiva MS-XCEP e emissão MS-WSTEP -- suporta inscrição manual MMC/certreq e autoinscrição GPO não assistida.',
        items: [
          { label: 'XCEP', text: 'Permite que os clientes Windows descubram os modelos de certificado disponíveis antes de se inscrever' },
          { label: 'WSTEP', text: 'Trata a solicitação e renovação do certificado depois que a diretiva é descoberta' },
          { label: 'Kerberos/SPNEGO', text: 'Vincula os endpoints autenticados por Kerberos usados para a autoinscrição GPO silenciosa (requer um SPN e um keytab do controlador de domínio)' },
          { label: 'Lista de verificação de configuração', text: 'A guia mostra uma lista de verificação em tempo real do que está configurado versus o que ainda falta, tanto para a inscrição manual quanto para a não assistida' },
          { label: 'Assuntos derivados do AD', text: 'Os modelos podem optar por derivar seu assunto/SAN do Active Directory (via conector AD) para a inscrição não assistida' },
          { label: 'Modelos ML-DSA (v2.248)', text: 'Anunciados pelo OID do seu algoritmo de chave com o Microsoft Software Key Storage Provider, ainda não testados com um cliente Windows real, e ocultos em modo FIPS. A renovação por certificado não pode usar um certificado ML-DSA (XML-DSig não tem assinatura ML-DSA): inscreva um novo' },
          { label: 'Modelos ECDSA (v2.251)', text: 'Anunciados no esquema de diretiva 3 com a sua curva (ECDSA_P256, ECDSA_P384, ECDSA_P521) como chave de assinatura e um hash de pedido, o mais forte entre o digest do modelo e o que corresponde à curva. Os modelos RSA fora do modo FIPS permanecem no esquema 2' },
          { label: 'Modelo e chave (v2.251)', text: 'A chave do pedido deve caber no modelo sob o qual é emitida: a mesma curva ou o mesmo conjunto ML-DSA, ou uma chave RSA pelo menos igual em tamanho, de modo que um pedido P-384 já não é emitido sob um modelo P-256 com o mesmo EKU. O envelope de pedido que o Windows assina com uma chave ECDSA é aceito' },
          { label: 'Renovação a partir do Windows (v2.248)', text: 'certreq ... Renew autentica-se com o certificado a renovar como certificado de cliente TLS: requer mTLS ativado com a CA WSTEP, ou uma das suas ancestrais, como confiável. Uma renovação mantém o modelo e os EKUs do certificado que renova' },
          { label: 'Kerberos no Docker (v2.251)', text: 'As imagens Docker incluem o backend Kerberos do pyspnego, de modo que a vinculação Kerberos funciona num contêiner como nas instalações DEB e RPM' },
        ]
      },
      {
        title: 'Renovação automática',
        items: [
          { label: 'Fontes', text: 'O agendador renova os certificados cuja chave privada o servidor detém: por padrão os emitidos pelo formulário ou por uma solicitação assinada ("manual") e as inscrições SCEP, ACME e EST com chave gerada pelo servidor. Os dispositivos que detêm a própria chave renovam pelo seu protocolo' },
          { label: 'Aguardando aprovação', text: 'Um certificado cuja renovação está na fila de aprovação é deixado a essa decisão, desde que ela possa ocorrer antes de o certificado expirar' },
          { label: 'Renovado entretanto', text: 'Um certificado que um operador renovou durante o lote não é renovado uma segunda vez; um excluído durante o lote é ignorado' },
          { label: 'Certificados de curta duração', text: 'A renovação nunca começa antes do último terço da validade de um certificado: um certificado de 27 dias é renovado quando faltam 9, e não desde a emissão' },
          { label: 'Executar agora', text: 'Executa uma passagem de renovação imediatamente e informa os certificados prestes a expirar que deixou de lado, contados por motivo: ainda não no último terço da validade, chave privada não detida pelo servidor, fonte não selecionada' },
          { label: 'Digest de assinatura (v2.251)', text: 'Uma renovação mantém o digest do certificado original enquanto ele for pelo menos o que corresponde à chave da CA e as políticas o permitirem; caso contrário segue a regra de emissão: sob uma CA P-384 ou P-521, um original SHA-256 é renovado com SHA-384 ou SHA-512' },
        ]
      },

    ],
    tips: [
      'Use o widget de Status do Sistema no topo para verificar rapidamente a saúde dos serviços',
      'Teste as configurações SMTP antes de depender de notificações por e-mail',
      'Personalize o modelo de e-mail com sua marca usando o editor HTML/Texto integrado',
      'Agende backups automáticos para ambientes de produção',
      'A troca SQLite ↔ PostgreSQL é bidirecional: a UI executa verificações de segurança (driver carregado, destino acessível, destino vazio) antes da migração',
    ],
    warnings: [
      'Alterar o certificado HTTPS requer reinicialização do serviço',
      'Modificar configurações de segurança pode bloquear usuários: verifique o acesso antes de salvar',
    ],
  },
  helpGuides: {
    title: 'Configurações',
    content: `
## Visão Geral

Configuração de todo o sistema organizada em abas. As alterações entram em vigor imediatamente, salvo indicação contrária.

## Geral

- **Nome de host do syslog**: Enviado como HOSTNAME nas mensagens syslog encaminhadas; vazio, usa o nome de host da máquina
- **URL Base**: URL HTTPS canônica da interface de administração e da API; outros nomes de host e IPs são redirecionados para ela
- **URL base do protocolo**: URL base escrita nos endereços CDP e OCSP; use http:// para evitar loops de verificação TLS, ou deixe vazio para usar a URL Base
- **Porta HTTP protocolo**: Porta HTTP simples que serve CDP e OCSP; 0 a desativa, uma alteração exige reinício
- **Vhost ACME público**: Hostname concreto nas URLs do diretório ACME (ex.: \`acme.ucm.example.com\`: não \`*.ucm.example.com\`). Um **SAN do certificado TLS** curinga \`*.ucm.example.com\` cobre tanto \`admin.ucm.example.com\` quanto \`acme.ucm.example.com\`. Configure o DNS e o TLS para o vhost ACME **antes** de salvar: os clientes que releem o diretório mudam de URL imediatamente.

## Aparência

- **Tema**: Claro, Escuro ou Sistema (segue a preferência do SO)
- **Cor de Destaque**: Cor principal usada para botões, links e destaques
- **Forçar Modo Desktop**: Desativar layout responsivo móvel

## E-mail (SMTP)

Configure SMTP para notificações por e-mail (alertas de expiração, convites de usuário):
- **Host SMTP** e **Porta**
- **Usuário** e **Senha**
- **Criptografia**: Nenhuma, STARTTLS ou SSL/TLS
- **Endereço do Remetente**: Endereço de e-mail do remetente
- **Tipo de Conteúdo**: HTML, Texto Simples ou Ambos
- **Destinatários de Alertas**: Adicionar múltiplos destinatários usando a entrada de tags

Clique em **Testar** para enviar um e-mail de teste e verificar a configuração.

### Editor de Modelo de E-mail

Clique em **Editar Modelo** para abrir o editor de modelo em painel dividido em uma janela flutuante:
- **Aba HTML**: Edite o modelo de e-mail HTML com prévia ao vivo à direita
- **Aba Texto Simples**: Edite a versão em texto simples para clientes de e-mail que não suportam HTML
- Variáveis disponíveis: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Clique em **Restaurar Padrão** para restaurar o modelo UCM integrado
- A janela é redimensionável e arrastável para edição confortável

### Alertas de Expiração

Quando o SMTP está configurado, ative alertas automáticos de expiração de certificados:
- Alternar alertas ativados/desativados
- Selecionar limites de aviso (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Executar **Verificar Agora** para acionar uma verificação imediata
- **Ignorar certificados emitidos por ACME**: deixa de fora os certificados emitidos pelo servidor ACME do UCM, que seus clientes renovam; desativado por padrão

## Segurança

### Política de Senha
- Comprimento mínimo (6-32 caracteres)
- Exigir maiúsculas, números, caracteres especiais

### Gerenciamento de Sessão
- Duração da sessão (horas, qualquer que seja a atividade); o tempo limite de inatividade está em Geral

### Bloqueio de Conta
- Máx. de tentativas de login e duração do bloqueio, em Geral: bloqueiam a conta, não o endereço IP

### Lista de Acesso Administrativo
Limite a interface web e a API de gestão aos endereços IP e redes CIDR listados; os protocolos PKI continuam acessíveis de qualquer lugar. Veja o guia de Configurações de Segurança.

### Aplicação de 2FA
Exigir que todos os usuários ativem autenticação de dois fatores.

### Criptografia de Chaves Privadas
Criptografe todas as chaves privadas armazenadas no banco de dados com AES-256, protegidas por um arquivo de chave mestra. A seção mostra o status da criptografia e os contadores de chaves **criptografadas / não criptografadas**. Duas variáveis de ambiente opcionais tornam a ausência de chave fatal na inicialização: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (criptografia de segredos de integração) e \`UCM_REQUIRE_KEY_ENCRYPTION\` (criptografia de chaves privadas).

> 💡 Configurações sensíveis à segurança (sessão, bloqueio, HSTS, URL pública, política de senha) requerem a permissão **admin:settings**: os campos ficam bloqueados para operators.

> ⚠ Uma lista que não inclui o seu próprio endereço é recusada. Se mesmo assim perder o acesso, defina \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` e reinicie o UCM.

## SSO (Login Único)

### SAML 2.0
- Forneça ao seu IDP a **URL de Metadados SP**: \`/api/v2/sso/saml/metadata\`
- Ou configure manualmente: envie/vincule o XML de metadados do IDP, configure Entity ID e URL ACS
- Mapeie atributos do IDP para campos de usuário UCM (nome de usuário, e-mail, função)

### OAuth2 / OIDC
- URL de Autorização e URL de Token
- Client ID e Client Secret
- URL de Informações do Usuário (para recuperação de atributos)
- Escopos (openid, profile, email)
- Criar usuários automaticamente no primeiro login SSO

### LDAP
- Hostname do servidor, porta (389/636), alternância SSL
- Bind DN e senha (conta de serviço)
- Base DN e filtro de usuário
- Mapeamento de atributos (nome de usuário, e-mail, nome completo)

> 💡 Sempre mantenha uma conta de administrador local como fallback caso o SSO falhe.

## Backup

### Backup Manual
Clique em **Criar Backup** para gerar um snapshot do banco de dados. Os backups incluem os certificados, CAs, chaves e configurações; o log de auditoria e outras tabelas de histórico não são incluídos.

### Backup Agendado
Configure backups automáticos:
- Frequência (diária, semanal, mensal)
- Retenção em dias: os backups mais antigos são removidos (30 por padrão)
- **Derivação de chave**: Automática (Argon2id quando disponível, PBKDF2 no modo FIPS), PBKDF2-HMAC-SHA256 ou Argon2id. Os arquivos gravados com Argon2id não podem ser restaurados numa instância em modo FIPS

### Restauração
Envie um arquivo de backup para restaurar o UCM a um estado anterior.

- Backups e restaurações compartilham um só bloqueio: uma restauração é recusada (409) enquanto um backup está em curso, e um backup manual espera por uma restauração em curso
- O envio é aceito até \`BACKUP_MAX_UPLOAD_MB\` (512 MB por padrão, definido no ambiente do servidor); um reverse proxy à frente do UCM mantém o seu próprio limite de corpo
- Os arquivos contêm pedidos do cliente ACME, pedidos de aprovação e pedidos de recuperação de chaves (v2.251)
- Um provedor DNS, conta CA ACME ou webhook cujo nome outra linha já tem aqui é restaurado como \`nome (2)\`
- A API também aceita \`mode=merge\`, que adiciona o arquivo aos dados daqui em vez de os substituir

> ⚠ Restaurar um backup substitui TODOS os dados atuais.

## Auditoria

- **Retenção de logs**: Limpeza automática de logs antigos após N dias
- **Encaminhamento syslog**: Enviar eventos para um servidor syslog remoto (UDP/TCP/TLS)
- **Verificação de integridade**: Verificar a cadeia de hash que liga cada entrada de auditoria; a cadeia está sempre ativa, não há nada a ativar

## Banco de Dados

UCM suporta dois backends de banco de dados:

- **SQLite** (padrão): baseado em arquivo, sem configuração, ideal para nó único
- **PostgreSQL 13+**: recomendado para alta disponibilidade, multi-instância ou se você já opera um cluster PG gerenciado

O backend ativo é selecionado pela variável de ambiente \`DATABASE_URL\`. Se não definida, o UCM usa SQLite em \`DATA_DIR/ucm.db\`.

### Painel de status
- Backend ativo (sqlite / postgresql) e a versão do seu motor
- Tamanho do banco e número de tabelas

### Testar conexão
Valide uma \`DATABASE_URL\` (ex.: \`postgresql://user:pass@host:5432/ucm\`) antes de alternar. O teste abre uma conexão real e relata qualquer erro. Servidores PostgreSQL anteriores à versão 13 são rejeitados, o UCM requer PostgreSQL 13 ou mais recente.

### Alternar backend
Persiste \`DATABASE_URL\` em \`/etc/ucm/ucm.env\` (DEB/RPM) e reinicia o UCM. Apenas as tabelas de contas, funções, SSO e MFA são copiadas para o novo backend, para que você ainda possa entrar; use **Migrar** primeiro se quiser manter seus outros dados.

### Migrar dados
Copia todas as linhas do backend atual para o backend de destino. Funciona em ambas as direções (SQLite ↔ PostgreSQL):

1. O banco de origem é salvo em \`/opt/ucm/data/backups/db_migration/\`
2. O esquema é criado no destino via SQLAlchemy
3. Restrições de FK são desativadas durante a carga em massa
4. As colunas são associadas pelo nome; só as colunas legadas conhecidas são descartadas, e qualquer outra coluna que o destino não tenha recusa a migração
5. As sequências do PostgreSQL são reiniciadas após a carga
6. O serviço reinicia automaticamente (DEB/RPM): no Docker, defina \`DATABASE_URL\` no seu arquivo compose e reinicie o container manualmente


**Verificações de segurança (falha rápida, origem intacta):**
- O destino deve estar vazio. Se alguma das suas tabelas já contiver linhas, a migração é recusada com HTTP 409 e uma dica de limpeza:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - PostgreSQL num esquema diferente de \`public\` (um \`search_path\` na URL): a dica indica esse esquema, cujas sequências a migração realinha (v2.251)
  - SQLite: exclua o arquivo \`.db\` de destino
- Se a migração falhar no meio do caminho, a origem permanece intacta e a mensagem de erro aponta para o backup da origem. Reinicialize o destino antes de tentar novamente.

> ⚠ Sempre faça um backup completo do UCM (Configurações → Backup) antes de migrar entre backends.

## HTTPS

Gerencie o certificado TLS usado pela interface web do UCM:
- Visualizar detalhes do certificado atual
- Importar um novo certificado (PEM ou PKCS#12)
- Gerar um certificado autoassinado

> ⚠ Alterar o certificado HTTPS requer reinicialização do serviço.

## Atualizações

- Verificar novas versões do UCM nos releases do GitHub
- Visualizar o changelog das atualizações disponíveis
- Versão atual e informações de build
- **Atualização automática**: em instalações suportadas (DEB/RPM), clique em **Instalar Atualização** para baixar e instalar a versão mais recente automaticamente
- **Canal de atualização**: estável, pré-release (release candidates) ou dev

## Webhooks

Configure webhooks HTTP para notificar sistemas externos sobre eventos:

### Eventos Suportados
- Certificado emitido, revogado, renovado, prestes a expirar, expirado, importado, excluído
- CA criada, atualizada, excluída
- CSR enviado, aprovado, rejeitado
- Modelo criado, atualizado
- Preflight ACME, falha de renovação, falha de revogação
- Atualização disponível, iniciada, instalada, com falha

As importações de certificados e as alterações de modelos feitas pela interface web não emitem o seu evento.

### Autenticação

Autenticação de saída opcional (aplica-se além da assinatura HMAC opcional):

- **Nenhuma**: Sem cabeçalho de autenticação (webhooks públicos)
- **Bearer**: Authorization: Bearer {token}
- **Basic**: Authorization: Basic base64(usuário:senha)
- **API Key**: Cabeçalho personalizado (p.ex. X-Api-Key: {token})
- **Personalizada**: Authorization: {esquema} {token} (p.ex. auth-key VALOR)

Os tokens são armazenados criptografados e nunca retornados na UI.

### Criando um Webhook
1. Clique em **Adicionar Webhook**
2. Insira a **URL** (HTTPS recomendado; http:// é aceito)
3. Selecione os **eventos** para se inscrever
4. Escolha o **tipo de autenticação** e forneça as credenciais (opcional)
5. Opcionalmente defina um **segredo** para verificação de assinatura HMAC
6. Clique em **Criar**

### Teste
Clique em **Testar** para enviar um evento de exemplo para a URL do webhook e verificar se está acessível.
## Métricas Prometheus

Endpoint **\`/metrics\`** opcional e protegido por token.

- Ative-o definindo um token de métricas (Definições › Geral); sem token → 404
- Faça scrape com o cabeçalho \`Authorization: Bearer <token>\`
- Expõe \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\`

## Histórico de entrega de webhooks

Abra o histórico (ícone de relógio) num webhook para ver as suas entregas.

- Estados **pending / delivered / failed** com último código HTTP e erro
- **Repetir** uma entrega manualmente
- Fila durável com recuo exponencial (até 5 tentativas)

## Vista do agendador

Definições › Agendador mostra as tarefas em segundo plano.

- Lista de tarefas com **estado**, **última execução**, **duração** e **falhas**
- **Executar agora** em qualquer tarefa: espera até 30 segundos, e uma tarefa ainda em curso nesse momento é indicada como iniciada, com o resultado numa atualização posterior
- Cobre expiração, CRL, entrega de webhooks, backups, renovação automática…
- **Processo do agendador** (v2.251): as tarefas rodam num processo próprio, iniciado com o serviço e reiniciado em poucos segundos após uma falha ou um reload, de modo que uma tarefa longa não atrasa nem pedidos nem workers. Um aviso aparece quando ele não reporta há algum tempo

## Renovação automática
As definições de renovação automática comandam o agendador de renovação.
- **Fontes**: o agendador renova os certificados cuja chave privada o servidor detém: por padrão os emitidos pelo formulário ou por uma solicitação assinada ("manual") e as inscrições SCEP, ACME e EST com chave gerada pelo servidor. Os dispositivos que detêm a própria chave renovam pelo seu protocolo
- **Aguardando aprovação**: um certificado cuja renovação está na fila de aprovação é deixado a essa decisão, desde que ela possa ocorrer antes de o certificado expirar
- **Renovado entretanto**: um certificado que um operador renovou durante o lote não é renovado uma segunda vez; um excluído durante o lote é ignorado
- **Certificados de curta duração**: a renovação nunca começa antes do último terço da validade de um certificado: um certificado de 27 dias é renovado quando faltam 9, e não desde a emissão
- **Executar agora**: executa uma passagem de renovação imediatamente e informa os certificados prestes a expirar que deixou de lado, contados por motivo: ainda não no último terço da validade, chave privada não detida pelo servidor, fonte não selecionada

## Backups agendados

Definições › Backup ativa backups automáticos.

- Cadência **diária / semanal / mensal**
- **Retenção**: os backups mais antigos que o número de dias definido são removidos
- Backups **cifrados** com a palavra-passe de backup


## Conector do Active Directory

Conexão LDAP própria do UCM com o Active Directory, independente de qualquer provedor LDAP configurado em SSO. Aquele serve para fazer login no UCM; este é usado para consultas de AD relacionadas a certificados e funciona independentemente de o SSO estar configurado ou não.

- **Finalidade**: Resolve uma entidade de segurança de máquina ou usuário Kerberos para seu objeto AD, para que o UCM possa derivar um assunto/SAN de certificado da mesma forma que uma CA Windows real faria
- **Controladores de domínio**: Um por linha, cada um pelo seu próprio nome de host, tentados em ordem: as consultas passam para o seguinte quando um DC está inativo. Um nome de domínio simples falha na verificação do certificado, pois o certificado de um controlador de domínio nomeia apenas o seu próprio host
- **LDAPS**: Ativar para usar LDAP sobre SSL/TLS; **Verificar certificado SSL** valida o certificado do DC (opcionalmente em relação a um pacote de CA personalizado quando não é publicamente confiável)
- **DN Base** e **DN de Ligação / Senha**: Credenciais da conta de serviço usadas para as consultas; o DN de Ligação e a senha são ambos obrigatórios enquanto o conector estiver ativado
- **Testar conexão**: Verificar a conectividade e as credenciais antes de salvar
- **Intervalo da verificação de integridade**: Cada controlador de domínio é testado com uma conexão real neste intervalo; um inacessível é ignorado no momento da inscrição até se recuperar. O veredito aparece na linha das definições e em cada DC

### URLs de diretiva de inscrição GPO

Depois de configurado, registre uma das URLs exibidas como servidor de Diretiva de Inscrição de Certificados na Diretiva de Grupo (Diretivas de Chave Pública → Cliente de Serviços de Certificados – Diretiva de Inscrição de Certificados), junto com Cliente de Serviços de Certificados – Inscrição Automática:
- **Kerberos**: Sem solicitação de credenciais; requer um cliente ingressado no domínio e o tipo de autenticação da GPO definido como Kerberos
- **Usuário/Senha**: Solicita credenciais; apenas para inscrição interativa "Solicitar Novo Certificado"

## Autoinscrição do Windows (XCEP/WSTEP)

Inscrição de certificados nativa do Windows via **MS-XCEP** (descoberta de diretiva) e **MS-WSTEP** (emissão e renovação de certificados) -- os mesmos protocolos que um ADCS real usa para a inscrição interativa "Solicitar Novo Certificado" no MMC, \`certreq\`, e a autoinscrição GPO não assistida.

### Lista de verificação de configuração

A guia rastreia o que está configurado versus o que ainda falta, tanto para o caminho de inscrição manual quanto para o não assistido -- uma Autoridade de Certificação, Descoberta de Diretiva (XCEP), Emissão de Certificados (WSTEP) e, para a autoinscrição GPO não assistida, um Conector do Active Directory, Kerberos/SPNEGO e pelo menos um modelo com a autoinscrição permitida.

### Descoberta de Diretiva (XCEP)

- **Autoridade de Certificação**: A CA cujos modelos são anunciados e que emite certificados por meio desta configuração
- **Validade (dias)**: Validade dos certificados emitidos via WSTEP quando o pedido não corresponde a nenhum modelo; caso contrário, aplica-se a validade do modelo correspondente

Um modelo com tipo de chave **ML-DSA** é anunciado pelo OID do seu algoritmo de chave, com o Microsoft Software Key Storage Provider e um key spec só de assinatura. Fica oculto em modo FIPS, e a inscrição a partir de um cliente Windows real ainda não foi testada.

Um modelo **ECDSA** é anunciado no esquema de diretiva 3 com a sua curva (\`ECDSA_P256\`, \`ECDSA_P384\`, \`ECDSA_P521\`) como chave de assinatura e um hash de pedido, o mais forte entre o digest do modelo e o que corresponde à curva; os modelos RSA fora do modo FIPS permanecem no esquema 2. A chave do pedido deve caber no modelo sob o qual é emitida: a mesma curva ou o mesmo conjunto ML-DSA, ou uma chave RSA pelo menos igual em tamanho (v2.251).

### Kerberos / SPNEGO

Vincula os endpoints XCEP/WSTEP autenticados por Kerberos usados para a autoinscrição GPO silenciosa, para que máquinas e usuários sejam autenticados por seu tíquete Kerberos em vez de uma solicitação de credenciais:
- **Nome da Entidade de Serviço (SPN)**: por exemplo, \`HTTP/ucm.exemplo.com@EXEMPLO.COM\`
- **Keytab**: Gerado com \`ktpass\` ou \`ktutil\` no controlador de domínio para o SPN acima

> ⚠ Se a biblioteca SPNEGO do lado do servidor não estiver instalada, a autenticação Kerberos não funcionará mesmo se habilitada aqui -- um aviso é exibido na guia.

As imagens Docker incluem esse backend desde a v2.251.

### URLs de diretiva de inscrição

- **Usuário/Senha**: Solicita credenciais; para inscrição interativa "Solicitar Novo Certificado", não requer Active Directory
- **Kerberos**: Sem solicitação de credenciais; requer um cliente ingressado no domínio e configuração de GPO

### Vinculação de renovação por certificado

Além de Usuário/Senha e Kerberos, o WSTEP suporta a **renovação por certificado de cliente**, espelhando os endpoints CES do ADCS real: a solicitação de renovação (RST) deve ser assinada em XML-DSig com a chave privada de um certificado **emitido pelo próprio UCM**. O certificado apresentado é comparado **byte a byte** com o certificado armazenado para a CA configurada, número de série ou assunto sozinhos nunca são suficientes. Isso permite que clientes Windows renovem de forma não assistida usando seu certificado atual, sem credenciais nem tíquete Kerberos.
XML-DSig não tem método de assinatura ML-DSA, portanto um certificado **ML-DSA** não pode renovar assim: o UCM nomeia a chave na recusa, e o cliente inscreve um novo certificado.

O Windows também pode renovar com \`certreq ... Renew\`, autenticado pelo certificado a renovar como certificado de cliente TLS: ative o mTLS com a CA WSTEP, ou uma das suas ancestrais, como confiável. Uma renovação mantém o modelo e os EKUs do certificado que renova (v2.248).


### Extensão de segurança SID (KB5014754)

Na **emissão autenticada por Kerberos**, o UCM incorpora o SID do AD do solicitante na extensão de segurança SID da Microsoft (\`szOID_NTDS_CA_SECURITY_EXT\`) do certificado emitido. Os controladores de domínio a utilizam para o **mapeamento forte de certificados** (KB5014754): exigido desde a aplicação obrigatória do mapeamento forte no AD para a autenticação baseada em certificado (logon com smartcard, PKINIT). Uma renovação WSTEP, EST ou SCEP mantém a extensão SID do certificado que renova, nunca uma vinda da CSR; com o conector AD ativado, esse SID ainda precisa designar uma conta do diretório.

### Assuntos derivados do AD

Um modelo de certificado pode optar por **Criar assunto a partir do Active Directory** (Modelos → Inscrição): para a autoinscrição GPO não assistida, o assunto e o SAN são derivados do objeto AD do solicitante via o conector AD em vez de exigir que o cliente forneça um -- corresponde à forma como um modelo ADCS real é configurado para autoinscrição. De forma independente, **Permitir autoinscrição** anuncia o modelo como \`autoEnroll=true\` na Diretiva de Inscrição de Certificados, para que clientes autenticados por GPO/Kerberos o solicitem automaticamente no logon.

## Sobre

- **Informações do sistema**, **Links e recursos** e **Apoiar o UCM** levam ao Ko-fi. Os administradores também veem um cartão Ko-fi dispensável uma vez por versão do UCM
- **Verificar preparação para FIPS** (admin:system): lista o que o modo FIPS recusaria nesta instância (hashes de senha scrypt, autoridades Ed25519, backups Argon2id, PostgreSQL sem TLS...), com um remédio para cada item. Nada é alterado
`
  }
}
