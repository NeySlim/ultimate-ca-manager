export default {
  helpContent: {
    title: 'Login Único',
    subtitle: 'Integração SAML, OAuth2 e LDAP',
    overview: 'Configure Login Único para permitir que os usuários se autentiquem através do provedor de identidade da sua organização. Suporta os protocolos SAML 2.0, OAuth2/OIDC e LDAP.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Provedor de Identidade', text: 'Configurar URL de metadados do IDP ou enviar XML' },
          { label: 'URL de Metadados SP', text: 'Forneça esta URL ao seu IDP para configurar automaticamente o UCM como provedor de serviço' },
          { label: 'Certificado SP', text: 'Certificado HTTPS do UCM incluído nos metadados — deve ser confiável pelo IDP ou os metadados serão rejeitados' },
          { label: 'Entity ID', text: 'Identificador de entidade do provedor de serviço UCM' },
          { label: 'URL ACS', text: 'URL de callback do Assertion Consumer Service' },
          { label: 'Mapeamento de Atributos', text: 'Mapear atributos do IDP para campos de usuário UCM' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'URL de Autorização', text: 'Endpoint de autorização OAuth2' },
          { label: 'URL de Token', text: 'Endpoint de token OAuth2' },
          { label: 'Client ID/Secret', text: 'Credenciais de cliente OAuth2 do seu IDP' },
          { label: 'Escopos', text: 'Escopos OAuth2 a solicitar (openid, profile, email)' },
          { label: 'Criação Automática de Usuários', text: 'Criar automaticamente contas UCM no primeiro login SSO' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Servidor', text: 'Hostname e porta do servidor LDAP (389 ou 636 para SSL)' },
          { label: 'Bind DN', text: 'Distinguished Name para autenticação de bind LDAP' },
          { label: 'Base DN', text: 'Base de pesquisa para busca de usuários' },
          { label: 'Filtro de Usuário', text: 'Filtro LDAP para corresponder usuários (ex.: (uid={username}))' },
          { label: 'Mapeamento de Atributos', text: 'Mapear atributos LDAP para nome de usuário, e-mail, nome completo' },
        ]
      },
    ],
    tips: [
      'Teste o SSO com uma conta não administrativa primeiro para evitar bloqueios',
      'Mantenha o login de administrador local disponível como fallback',
      'Mapeie o atributo de e-mail do IDP para garantir identificação única de usuários',
      'Use a URL de Metadados SP para configurar automaticamente seu IDP (SAML)',
      'O certificado HTTPS do UCM deve ser confiável pelo IDP para que os metadados SAML sejam aceitos',
    ],
    warnings: [
      'SSO mal configurado pode bloquear todos os usuários — sempre mantenha um administrador local',
    ],
  },
  helpGuides: {
    title: 'Login Único',
    content: `
## Visão Geral

SSO permite que os usuários se autentiquem usando o Provedor de Identidade (IDP) da sua organização, eliminando a necessidade de credenciais UCM separadas. O UCM suporta **SAML 2.0**, **OAuth2/OIDC** e **LDAP**.

## SAML 2.0

### URL de Metadados SP

O UCM fornece uma **URL de Metadados do Service Provider (SP)** que você pode dar ao seu IDP para configuração automática:

\`\`\`
https://seu-host-ucm:8443/api/v2/sso/saml/metadata
\`\`\`

Esta URL retorna um documento XML compatível com SAML 2.0 contendo:
- **Entity ID** — Identificador do provedor de serviço UCM
- **URL ACS** — Endpoint do Assertion Consumer Service (HTTP-POST)
- **URL SLO** — Endpoint do serviço de Single Logout
- **Certificado de Assinatura** — Certificado HTTPS do UCM para verificação de assinatura
- **Formato NameID** — Formato de identificador de nome solicitado

Copie esta URL na configuração "Adicionar Service Provider" ou "Aplicação SAML" do seu IDP.

> ⚠️ **Importante:** O certificado HTTPS do UCM deve ser **confiável pelo IDP**. Se o IDP não puder validar o certificado (ex.: autoassinado ou emitido por uma CA privada), ele rejeitará os metadados como inválidos. Importe o certificado da CA do UCM no armazenamento de confiança do IDP, ou use um certificado assinado por uma CA publicamente confiável.

### Configuração
1. Obtenha a URL de metadados do IDP ou arquivo XML do seu provedor de identidade
2. No UCM, vá para **Configurações → SSO**
3. Clique em **Adicionar Provedor** → SAML
4. Insira a **URL de Metadados do IDP** — o UCM preenche automaticamente Entity ID, URLs SSO/SLO e certificado
5. Ou cole o XML de metadados do IDP diretamente
6. Configure o **mapeamento de atributos** (nome de usuário, e-mail, grupos)
7. Clique em **Salvar** e **Ativar**

### Mapeamento de Atributos
Mapeie atributos SAML do IDP para campos de usuário UCM:
- \`username\` → Nome de usuário UCM (obrigatório)
- \`email\` → E-mail UCM (obrigatório)
- \`groups\` → Associação a grupos UCM (opcional)

## OAuth2 / OIDC

### Configuração
1. Registre o UCM como cliente no seu provedor OAuth2/OIDC
2. Defina o **URI de Redirecionamento** como: \`https://seu-host-ucm:8443/api/v2/sso/callback/oauth2\`
3. Copie o **Client ID** e **Client Secret**
4. No UCM, vá para **Configurações → SSO**
5. Clique em **Adicionar Provedor** → OAuth2
6. Insira a **URL de Autorização** e **URL de Token**
7. Insira a **URL de Informações do Usuário** (para buscar atributos do usuário após login)
8. Insira Client ID e Secret
9. Configure escopos (openid, profile, email)
10. Clique em **Salvar** e **Ativar**

### Criação Automática de Usuários
Quando ativada, uma nova conta de usuário UCM é criada automaticamente no primeiro login SSO, usando os atributos fornecidos pelo IDP. A função padrão é atribuída.

## LDAP

### Configuração
1. No UCM, vá para **Configurações → SSO**
2. Clique em **Adicionar Provedor** → LDAP
3. Insira o **Servidor LDAP** hostname e **Porta** (389 para LDAP, 636 para LDAPS)
4. Ative **Usar SSL** para conexões criptografadas
5. Insira o **Bind DN** e **Senha de Bind** (credenciais da conta de serviço)
6. Insira o **Base DN** (base de pesquisa para busca de usuários)
7. Configure o **Filtro de Usuário** (ex.: \`(uid={username})\` ou \`(sAMAccountName={username})\` para AD)
8. Mapeie atributos LDAP: **nome de usuário**, **e-mail**, **nome completo**
9. Clique em **Testar Conexão** para verificar, depois **Salvar** e **Ativar**

### Active Directory
Para Microsoft Active Directory, use:
- Porta: **389** (ou 636 com SSL)
- Filtro de Usuário: \`(sAMAccountName={username})\`
- Atributo de nome de usuário: \`sAMAccountName\`
- Atributo de e-mail: \`mail\`
- Atributo de nome completo: \`displayName\`

## Fluxo de Login
1. O usuário clica em **Login com SSO** na página de login do UCM (ou insere credenciais LDAP)
2. Para SAML/OAuth2: o usuário é redirecionado para o IDP, autentica-se e é redirecionado de volta
3. Para LDAP: as credenciais são verificadas diretamente no servidor LDAP
4. O UCM cria ou atualiza a conta de usuário
5. O usuário está logado

> ⚠ Sempre mantenha pelo menos uma conta de administrador local como fallback caso a configuração SSO bloqueie todos.

> 💡 Teste o SSO com uma conta não administrativa primeiro antes de torná-lo o método principal de autenticação.

> 💡 Use o botão **Testar Conexão** para verificar sua configuração antes de ativar um provedor.
`
  }
}
