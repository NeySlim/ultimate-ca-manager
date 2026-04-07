export default {
  helpContent: {
    title: 'Minha Conta',
    subtitle: 'Configurações pessoais e segurança',
    overview: 'Gerencie seu perfil, configurações de segurança e chaves de API. Ative a autenticação de dois fatores e registre chaves de segurança para proteção aprimorada da conta.',
    sections: [
      {
        title: 'Perfil',
        items: [
          { label: 'Nome Completo', text: 'Seu nome de exibição mostrado em toda a aplicação' },
          { label: 'E-mail', text: 'Usado para notificações e recuperação de conta' },
          { label: 'Informações da Conta', text: 'Data de criação, último login, total de logins' },
        ]
      },
      {
        title: 'Segurança',
        items: [
          { label: 'Senha', text: 'Alterar sua senha atual' },
          { label: '2FA (TOTP)', text: 'Ativar senhas únicas baseadas em tempo via aplicativo autenticador' },
          { label: 'Chaves de Segurança', text: 'Registrar chaves WebAuthn/FIDO2 (YubiKey, impressão digital, etc.)' },
          { label: 'mTLS', text: 'Gerenciar certificados de cliente para autenticação TLS mútua' },
        ]
      },
      {
        title: 'Chaves de API',
        items: [
          { label: 'Criar Chave', text: 'Gerar uma nova chave de API com expiração opcional' },
          { label: 'Permissões', text: 'As chaves de API herdam as permissões do seu perfil' },
          { label: 'Revogar', text: 'Invalidar imediatamente uma chave de API' },
        ]
      },
    ],
    tips: [
      'Ative pelo menos um segundo fator (TOTP ou Chave de Segurança) para contas de administrador',
      'As chaves de API podem ter uma data de expiração para integrações de curta duração',
      'Escaneie o QR code com qualquer aplicativo TOTP: Google Authenticator, Authy, 1Password, etc.',
    ],
  },
  helpGuides: {
    title: 'Minha Conta',
    content: `
## Visão Geral

Gerencie seu perfil pessoal, configurações de segurança e chaves de API.

## Perfil

- **Nome Completo** — Seu nome de exibição mostrado em todo o UCM
- **E-mail** — Usado para notificações, recuperação de senha e registro ACME
- **Informações da Conta** — Data de criação, data do último login, total de logins

## Segurança

### Alteração de Senha
Altere sua senha atual. Deve estar em conformidade com a política de senhas do sistema (comprimento mínimo, requisitos de complexidade).

### Autenticação de Dois Fatores (TOTP)
Adicione uma senha única baseada em tempo usando qualquer aplicativo autenticador:

1. Clique em **Ativar 2FA**
2. Escaneie o QR code com seu aplicativo autenticador (Google Authenticator, Authy, 1Password, etc.)
3. Digite o código de 6 dígitos para confirmar
4. Salve os **códigos de recuperação** — eles são mostrados apenas uma vez

> ⚠ Se você perder acesso ao seu autenticador e códigos de recuperação, um administrador deverá desativar seu 2FA.

### Chaves de Segurança (WebAuthn/FIDO2)
Registre chaves de segurança de hardware ou autenticadores biométricos:
- YubiKey
- Leitor de impressão digital
- Windows Hello
- Touch ID

1. Clique em **Registrar Chave de Segurança**
2. Digite um nome para a chave
3. Siga o prompt do navegador para autenticar
4. A chave aparece na sua lista de credenciais registradas

### Certificados mTLS
Gerencie certificados de cliente para autenticação TLS mútua:
- Enviar um certificado de cliente
- Baixar seus certificados registrados
- Excluir certificados antigos

## Chaves de API

### Criando uma Chave de API
1. Clique em **Criar Chave de API**
2. Digite um **nome** (descritivo, ex.: "Pipeline CI/CD")
3. Opcionalmente defina uma **data de expiração**
4. Clique em **Criar**
5. Copie a chave imediatamente — ela é mostrada apenas uma vez

### Usando Chaves de API
Inclua a chave no cabeçalho \`X-API-Key\`:

\`\`\`
X-API-Key: <sua-chave-de-api>
\`\`\`

### Permissões
As chaves de API herdam as permissões do perfil do seu usuário. Elas não podem ter mais acesso do que sua conta.

### Revogando Chaves
Clique em **Excluir** para invalidar imediatamente uma chave de API. Sessões ativas usando a chave serão encerradas.

> 💡 Use chaves de API de curta duração com datas de expiração para CI/CD e automação.
`
  }
}
