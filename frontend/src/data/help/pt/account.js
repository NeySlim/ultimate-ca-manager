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
          { label: '2FA (TOTP)', text: 'Ativar senhas únicas baseadas em tempo via aplicativo autenticador. Ativá-lo de novo enquanto já está ativo é recusado: desative-o primeiro' },
          { label: 'Chaves de Segurança', text: 'Registrar chaves WebAuthn/FIDO2 (YubiKey, impressão digital, etc.)' },
          { label: 'mTLS', text: 'Gerenciar certificados de cliente para autenticação TLS mútua' },
        ]
      },
      {
        title: 'Chaves de API',
        items: [
          { label: 'Criar Chave', text: 'Gerar uma nova chave de API com expiração opcional' },
          { label: 'Permissões', text: 'Uma chave tem o escopo escolhido na criação, nunca mais do que as suas próprias permissões. Uma chave só pode criar ou regenerar uma chave cujas permissões ela própria possui' },
          { label: 'Revogar', text: 'Invalidar imediatamente uma chave de API' },
          { label: 'Usuários desativados', text: 'Chaves de API pertencentes a um usuário desativado são rejeitadas mesmo que a própria chave ainda seja válida' },
          { label: 'Somente sessão interativa', text: 'As chaves de API, mesmo as de Acesso total, não podem alterar seu perfil, senha, 2FA, chaves de segurança, certificados mTLS ou sessões, nem alcançar sua própria conta pelas ações de administração de usuários: entre de forma interativa' },
        ]
      },
      {
        title: 'Preferências (sincronizadas no servidor)',
        content: 'Seu idioma, família de tema e modo são persistidos no banco de dados e seguem você através de navegadores e dispositivos:',
        items: [
          { label: 'Armazenado', text: 'Em users.preferences (JSON). Novos endpoints GET/PUT /api/v2/account/preferences' },
          { label: 'Auto-aplicado', text: '/api/v2/auth/verify retorna suas preferências e elas são aplicadas em cada carregamento de página' },
          { label: 'Navegador novo', text: 'Login a partir de um novo dispositivo ou após limpar dados do site → seu idioma e tema escolhidos são restaurados' },
        ]
      },

    ],
    tips: [
      'Ative pelo menos um segundo fator (TOTP ou Chave de Segurança) para contas de administrador',
      'As chaves de API podem ter uma data de expiração para integrações de curta duração',
      'Chaves API também podem ser criadas sem expiração para automação de longo prazo',
      'Escaneie o QR code com qualquer aplicativo TOTP: Google Authenticator, Authy, 1Password, etc.',
      'As seleções de filtro em cada página de lista (Certificados, CAs, Auditoria, etc.) são persistidas automaticamente entre recargas',
    ],
  },
  helpGuides: {
    title: 'Minha Conta',
    content: `
## Visão Geral

Gerencie seu perfil pessoal, configurações de segurança e chaves de API.

## Perfil

- **Nome Completo**: Seu nome de exibição mostrado em todo o UCM
- **E-mail**: Usado para notificações, recuperação de senha e registro ACME
- **Informações da Conta**: Data de criação, data do último login, total de logins

## Segurança

### Alteração de Senha
Altere sua senha atual. Deve estar em conformidade com a política de senhas do sistema (comprimento mínimo, requisitos de complexidade).

Quando o UCM pede uma nova senha no login (a conta \`admin\` do primeiro boot, por exemplo), a alteração vem antes de qualquer outra coisa: enquanto ela não for feita, o servidor recusa todas as outras requisições dessa sessão, API incluída.

### Autenticação de Dois Fatores (TOTP)
Adicione uma senha única baseada em tempo usando qualquer aplicativo autenticador:

1. Clique em **Ativar 2FA**
2. Escaneie o QR code com seu aplicativo autenticador (Google Authenticator, Authy, 1Password, etc.)
3. Digite o código de 6 dígitos para confirmar
4. Salve os **códigos de recuperação**: eles são mostrados apenas uma vez

> ⚠ Se você perder acesso ao seu autenticador e códigos de recuperação, um administrador deverá desativar seu 2FA.

Para mover o 2FA para um novo autenticador, desative-o primeiro: ativá-lo de novo enquanto já está ativo é recusado.

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

Com 2FA ativada ou obrigatória, uma chave registrada também pode concluir a segunda etapa de um login com senha: escolha **Usar uma chave de segurança**.

Sem um aplicativo autenticador, ative **Chave de segurança como segundo fator** na seção de autenticação de dois fatores: cada login com senha passa a pedir uma das suas chaves, e a última chave não pode ser removida enquanto a opção estiver ativa.

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
5. Copie a chave imediatamente: ela é mostrada apenas uma vez

### Usando Chaves de API
Inclua a chave no cabeçalho \`X-API-Key\`:

\`\`\`
X-API-Key: <sua-chave-de-api>
\`\`\`

Ou envie-a como token bearer: \`Authorization: Bearer <sua-chave-de-api>\`.

### Permissões
Cada chave tem o escopo escolhido na criação (**Acesso total**, **Somente leitura**, **Leitura e escrita**, **Apenas certificados**) e nunca mais acesso do que sua conta. Uma chave só pode criar ou regenerar uma chave cujas permissões ela própria possui.

As chaves de API, mesmo as de Acesso total, não podem alterar seu perfil, senha, 2FA, chaves de segurança, certificados mTLS ou sessões, nem alcançar sua própria conta pelas ações de administração de usuários: isso exige uma sessão interativa.

### Revogando Chaves
Clique em **Excluir** para invalidar imediatamente uma chave de API. Sessões ativas usando a chave serão encerradas.

> 💡 Use chaves de API de curta duração com datas de expiração para CI/CD e automação.
`
  }
}
