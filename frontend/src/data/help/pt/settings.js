export default {
  helpContent: {
    title: 'Configurações',
    subtitle: 'Configuração do sistema',
    overview: 'Configure todos os aspectos do sistema UCM. As configurações são organizadas por categoria: geral, aparência, e-mail, segurança, SSO, backup, auditoria, banco de dados, HTTPS, atualizações e webhooks.',
    sections: [
      {
        title: 'Categorias',
        items: [
          { label: 'Geral', text: 'Nome da instância, hostname e padrões do sistema' },
          { label: 'Aparência', text: 'Seleção de tema (claro/escuro/sistema), cor de destaque, modo desktop' },
          { label: 'E-mail (SMTP)', text: 'Servidor SMTP, credenciais, editor de modelo de e-mail e notificações de alerta de expiração' },
          { label: 'Segurança', text: 'Políticas de senha, tempo limite de sessão, limitação de taxa, restrições de IP' },
          { label: 'SSO', text: 'Integração de login único SAML 2.0, OAuth2/OIDC e LDAP' },
          { label: 'Backup', text: 'Backups manuais e agendados do banco de dados' },
          { label: 'Auditoria', text: 'Retenção de logs, encaminhamento syslog, verificação de integridade' },
          { label: 'Banco de Dados', text: 'Caminho do banco de dados, tamanho e status de migração' },
          { label: 'HTTPS', text: 'Certificado TLS para a interface web do UCM' },
          { label: 'Atualizações', text: 'Verificar novas versões, visualizar changelog, atualização automática (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP para eventos de certificado (emissão, revogação, expiração)' },
        ]
      },
    ],
    tips: [
      'Use o widget de Status do Sistema no topo para verificar rapidamente a saúde dos serviços',
      'Teste as configurações SMTP antes de depender de notificações por e-mail',
      'Personalize o modelo de e-mail com sua marca usando o editor HTML/Texto integrado',
      'Agende backups automáticos para ambientes de produção',
    ],
    warnings: [
      'Alterar o certificado HTTPS requer reinicialização do serviço',
      'Modificar configurações de segurança pode bloquear usuários — verifique o acesso antes de salvar',
    ],
  },
  helpGuides: {
    title: 'Configurações',
    content: `
## Visão Geral

Configuração de todo o sistema organizada em abas. As alterações entram em vigor imediatamente, salvo indicação contrária.

## Geral

- **Nome da Instância** — Exibido no título do navegador e nos e-mails
- **Hostname** — O nome de domínio totalmente qualificado do servidor
- **Validade Padrão** — Período de validade padrão do certificado em dias
- **Limite de Aviso de Expiração** — Dias antes da expiração para acionar avisos

## Aparência

- **Tema** — Claro, Escuro ou Sistema (segue a preferência do SO)
- **Cor de Destaque** — Cor principal usada para botões, links e destaques
- **Forçar Modo Desktop** — Desativar layout responsivo móvel
- **Comportamento da Barra Lateral** — Recolhida ou expandida por padrão

## E-mail (SMTP)

Configure SMTP para notificações por e-mail (alertas de expiração, convites de usuário):
- **Host SMTP** e **Porta**
- **Usuário** e **Senha**
- **Criptografia** — Nenhuma, STARTTLS ou SSL/TLS
- **Endereço do Remetente** — Endereço de e-mail do remetente
- **Tipo de Conteúdo** — HTML, Texto Simples ou Ambos
- **Destinatários de Alertas** — Adicionar múltiplos destinatários usando a entrada de tags

Clique em **Testar** para enviar um e-mail de teste e verificar a configuração.

### Editor de Modelo de E-mail

Clique em **Editar Modelo** para abrir o editor de modelo em painel dividido em uma janela flutuante:
- **Aba HTML** — Edite o modelo de e-mail HTML com prévia ao vivo à direita
- **Aba Texto Simples** — Edite a versão em texto simples para clientes de e-mail que não suportam HTML
- Variáveis disponíveis: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Clique em **Restaurar Padrão** para restaurar o modelo UCM integrado
- A janela é redimensionável e arrastável para edição confortável

### Alertas de Expiração

Quando o SMTP está configurado, ative alertas automáticos de expiração de certificados:
- Alternar alertas ativados/desativados
- Selecionar limites de aviso (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Executar **Verificar Agora** para acionar uma verificação imediata

## Segurança

### Política de Senha
- Comprimento mínimo (8-32 caracteres)
- Exigir maiúsculas, minúsculas, números, caracteres especiais
- Expiração de senha (dias)
- Histórico de senha (impedir reutilização)

### Gerenciamento de Sessão
- Tempo limite de sessão (minutos de inatividade)
- Máximo de sessões simultâneas por usuário

### Limitação de Taxa
- Limite de tentativas de login por IP
- Duração do bloqueio após exceder o limite

### Restrições de IP
Permitir ou negar acesso de endereços IP específicos ou faixas CIDR.

### Aplicação de 2FA
Exigir que todos os usuários ativem autenticação de dois fatores.

> ⚠ Teste restrições de IP cuidadosamente antes de aplicá-las. Regras incorretas podem bloquear todos os usuários.

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
Clique em **Criar Backup** para gerar um snapshot do banco de dados. Os backups incluem todos os certificados, CAs, chaves, configurações e logs de auditoria.

### Backup Agendado
Configure backups automáticos:
- Frequência (diária, semanal, mensal)
- Contagem de retenção (número de backups a manter)

### Restauração
Envie um arquivo de backup para restaurar o UCM a um estado anterior.

> ⚠ Restaurar um backup substitui TODOS os dados atuais.

## Auditoria

- **Retenção de logs** — Limpeza automática de logs antigos após N dias
- **Encaminhamento syslog** — Enviar eventos para um servidor syslog remoto (UDP/TCP/TLS)
- **Verificação de integridade** — Ativar encadeamento de hash para detecção de adulteração

## Banco de Dados

Informações sobre o banco de dados do UCM:
- Caminho no disco
- Tamanho do arquivo
- Versão de migração
- Versão do SQLite

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
- **Atualização automática**: em instalações suportadas (DEB/RPM), clique em **Atualizar Agora** para baixar e instalar a versão mais recente automaticamente
- **Incluir pré-releases**: alterne para também verificar release candidates (rc)

## Webhooks

Configure webhooks HTTP para notificar sistemas externos sobre eventos:

### Eventos Suportados
- Certificado emitido, revogado, expirado, renovado
- CA criada, excluída
- Login e logout de usuário
- Backup criado

### Criando um Webhook
1. Clique em **Adicionar Webhook**
2. Insira a **URL** (deve ser HTTPS)
3. Selecione os **eventos** para se inscrever
4. Opcionalmente defina um **segredo** para verificação de assinatura HMAC
5. Clique em **Criar**

### Teste
Clique em **Testar** para enviar um evento de exemplo para a URL do webhook e verificar se está acessível.
`
  }
}
