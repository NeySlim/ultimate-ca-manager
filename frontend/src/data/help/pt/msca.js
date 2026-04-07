export default {
  helpContent: {
    title: 'Integração Microsoft AD CS',
    subtitle: 'Assinar certificados com Autoridade Certificadora Microsoft',
    overview: 'Conecte o UCM ao Microsoft Active Directory Certificate Services (AD CS) para assinar CSRs usando sua infraestrutura PKI Windows. Suporta métodos de autenticação por certificado (mTLS), Kerberos e Basic.',
    sections: [
      {
        title: 'Métodos de Autenticação',
        items: [
          { label: 'Certificado de Cliente (mTLS)', text: 'Mais seguro. Gere um certificado de cliente na sua MS CA, exporte como PFX, envie PEM do certificado e da chave.' },
          { label: 'Basic Auth', text: 'Usuário/senha via HTTPS. Funciona sem ingressar no domínio. Ative basic auth no IIS certsrv.' },
          { label: 'Kerberos', text: 'Requer pacote requests-kerberos e máquina ingressada no domínio ou keytab configurado.' },
        ]
      },
      {
        title: 'Assinando CSRs',
        items: [
          { label: 'Seleção de Modelo', text: 'Escolha entre modelos de certificado disponíveis na MS CA' },
          { label: 'Auto-Aprovado', text: 'Modelos com autoenroll retornam o certificado imediatamente' },
          { label: 'Aprovação do Gerente', text: 'Alguns modelos requerem aprovação do gerente — o UCM rastreia a solicitação pendente' },
          { label: 'Consulta de Status', text: 'Verificar o status da solicitação pendente no painel de detalhes do CSR' },
        ]
      },
      {
        title: 'Inscrição em Nome de Outro (EOBO)',
        items: [
          { label: 'Visão Geral', text: 'Enviar CSR em nome de outro usuário usando certificados de agente de inscrição' },
          { label: 'DN do Inscrito', text: 'Distinguished Name do usuário alvo (preenchido automaticamente do sujeito do CSR)' },
          { label: 'UPN do Inscrito', text: 'User Principal Name do usuário alvo (preenchido automaticamente do e-mail SAN do CSR)' },
          { label: 'Requisitos', text: 'O modelo da CA deve permitir inscrição em nome de outros. A conta de serviço do UCM precisa de um certificado de agente de inscrição.' },
        ]
      },
    ],
    tips: [
      'Teste a conexão primeiro para verificar a autenticação e descobrir modelos disponíveis.',
      'Ative EOBO marcando a caixa de seleção no modal de assinatura — os campos são preenchidos automaticamente dos dados do CSR.',
      'A autenticação por certificado de cliente é recomendada para produção — não requer ingressar no domínio.',
    ],
    warnings: [
      'Kerberos requer que a máquina esteja ingressada no domínio ou um keytab configurado — não disponível no Docker.',
      'EOBO requer um certificado de agente de inscrição configurado no servidor AD CS.',
    ],
  },
  helpGuides: {
    title: 'Integração Microsoft AD CS',
    content: `
## Visão Geral

O UCM integra com o Microsoft Active Directory Certificate Services (AD CS) para assinar CSRs usando sua infraestrutura PKI Windows existente. Isso conecta sua CA interna com o gerenciamento de ciclo de vida de certificados do UCM.

## Configurando uma Conexão

1. Vá para **Configurações → Microsoft CA**
2. Clique em **Adicionar Conexão**
3. Insira o **Nome da Conexão** e o **Hostname do Servidor CA**
4. Opcionalmente insira o **Nome Comum da CA** (detectado automaticamente se vazio)
5. Selecione o **Método de Autenticação**
6. Insira as credenciais para o método escolhido
7. Clique em **Testar Conexão** para verificar
8. Defina um **Modelo Padrão** e clique em **Salvar**

## Métodos de Autenticação

| Método | Requisitos | Melhor Para |
|--------|-----------|-------------|
| **Certificado de Cliente (mTLS)** | PEM cert/chave do cliente da CA | Produção — não requer ingressar no domínio |
| **Basic Auth** | Usuário + senha, HTTPS | Configurações simples — ative basic auth no IIS certsrv |
| **Kerberos** | Máquina ingressada no domínio + keytab | Ambientes AD empresariais |

### Configuração de Certificado de Cliente (Recomendado)

1. Na sua CA Windows, crie um certificado para a conta de serviço do UCM
2. Exporte como PFX, depois converta para PEM:
   \`\`\`bash
   openssl pkcs12 -in cliente.pfx -out cliente-cert.pem -clcerts -nokeys
   openssl pkcs12 -in cliente.pfx -out cliente-key.pem -nocerts -nodes
   \`\`\`
3. Cole o conteúdo PEM do certificado e da chave no formulário de conexão do UCM

## Assinando CSRs via Microsoft CA

1. Navegue até **CSRs → Pendentes**
2. Selecione um CSR e clique em **Assinar**
3. Mude para a aba **Microsoft CA**
4. Selecione a conexão e o modelo de certificado
5. Clique em **Assinar**

### Modelos Auto-Aprovados
O certificado é retornado imediatamente e importado no UCM.

### Modelos com Aprovação do Gerente
O UCM salva a solicitação como **Pendente** e rastreia o ID da solicitação da MS CA. Uma vez aprovada na CA Windows, verifique o status no painel de detalhes do CSR para importar o certificado.

## Inscrição em Nome de Outro (EOBO)

EOBO permite que um agente de inscrição solicite certificados em nome de outros usuários. Isso é comum em ambientes empresariais onde um administrador PKI gerencia certificados para usuários finais.

### Pré-requisitos

- A conta de serviço do UCM precisa de um **certificado de agente de inscrição** emitido pela CA
- O modelo de certificado deve ter a permissão **"Inscrever em nome de outros usuários"** ativada
- A aba de segurança do modelo deve conceder ao agente de inscrição o direito de inscrever

### Usando EOBO no UCM

1. No modal de assinatura, selecione a conexão Microsoft CA e o modelo
2. Marque a caixa **Inscrição em Nome de Outro (EOBO)**
3. Os campos são preenchidos automaticamente do CSR:
   - **DN do Inscrito** — do sujeito do CSR (ex.: CN=João Silva,OU=Usuários,DC=corp,DC=local)
   - **UPN do Inscrito** — do e-mail SAN do CSR (ex.: joao.silva@corp.local)
4. Ajuste os valores se necessário
5. Clique em **Assinar**

O UCM passa isso como atributos de solicitação ADCS:
- EnrolleeObjectName:<DN> — identifica o usuário alvo no AD
- EnrolleePrincipalName:<UPN> — o nome de login do usuário

### EOBO vs Inscrição Direta

| Recurso | Inscrição Direta | EOBO |
|---------|------------------|------|
| Quem assina | O próprio usuário | Agente de inscrição em nome dele |
| Chave privada | Máquina do usuário | Pode estar no UCM (modelo CSR) |
| Permissão do modelo | Inscrição padrão | Requer direitos de agente de inscrição |
| Caso de uso | Autoatendimento | Gerenciamento PKI centralizado |

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Teste de conexão falha | Verifique hostname, porta 443 e se certsrv está acessível |
| Nenhum modelo encontrado | Verifique se a conta UCM tem permissões de inscrição na CA |
| EOBO negado | Verifique certificado de agente de inscrição e permissões do modelo |
| Solicitação presa em pendente | Aprove no console da CA Windows, depois atualize o status no UCM |

> 💡 Use o botão **Testar Conexão** para verificar a autenticação e descobrir modelos disponíveis antes de assinar.
`
  }
}
