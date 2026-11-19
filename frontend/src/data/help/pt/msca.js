export default {
  helpContent: {
    title: 'Integração Microsoft AD CS',
    subtitle: 'Assinar certificados com Autoridade Certificadora Microsoft',
    overview: 'Conecte o UCM ao Microsoft Active Directory Certificate Services (AD CS) para assinar CSRs usando sua infraestrutura PKI Windows e gerenciar o ciclo de vida completo dos certificados. Suporta autenticação por certificado (mTLS), Kerberos e Basic, além de um canal de administração WinRM opcional para revogação, CRL, inventário e gerenciamento de solicitações pendentes.',
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
          { label: 'Aprovação do Gerente', text: 'Alguns modelos requerem aprovação do gerente, o UCM rastreia a solicitação pendente' },
          { label: 'Solicitações pendentes', text: 'Uma solicitação que a CA mantém para o seu gerente continua Pendente no UCM, e a página não oferece verificação de status: depois de emitida na CA, importe o certificado, ou deixe a Sincronização de inventário pelo canal de administração WinRM importar os certificados que o UCM ainda não conhece' },
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
      {
        title: 'Ciclo de Vida: Renovar e Revogar',
        items: [
          { label: 'Renovar', text: 'Renovar um certificado emitido pelo AD CS reenvia o CSR original à mesma conexão e ao mesmo modelo, quem assina é a CA emissora, não o UCM.' },
          { label: 'Revogar', text: 'Revogar um certificado emitido pelo AD CS é local ao UCM, a menos que o canal de administração WinRM esteja configurado, nesse caso, é propagado para a CA Windows.' },
          { label: 'Renovação pendente', text: 'Se a CA retiver a renovação para aprovação do gerente, o UCM a rastreia como qualquer outra solicitação pendente.' },
        ]
      },
      {
        title: 'Canal de Administração WinRM (opcional)',
        items: [
          { label: 'Propósito', text: 'Executa operações de gerenciamento na CA Windows (revogar, desfazer revogação, publicar CRL, inventário, aprovar/negar) via PowerShell remoting + certutil, coisas que a inscrição web do AD CS não pode fazer.' },
          { label: 'Transporte', text: 'NTLM ou Kerberos sobre HTTP/HTTPS. Recomenda-se Kerberos + HTTPS; Kerberos reutiliza o keytab da conexão.' },
          { label: 'Credenciais', text: 'Reutiliza por padrão as da própria conexão. Conexões mTLS devem definir uma conta WinRM dedicada (oficial "Emitir e Gerenciar Certificados" com privilégios mínimos).' },
          { label: 'Requisito', text: 'WinRM habilitado na CA e o pacote opcional pywinrm instalado. Operações de gerenciamento exigem admin:system; propagar uma revogação ou a retirada de uma suspensão para a CA segue o write:certificates do certificado.' },
        ]
      },
      {
        title: 'Sincronização de Revogações via CRL',
        items: [
          { label: 'Sincronização unidirecional', text: 'Busca periodicamente a CRL da CA e marca como revogados no UCM os certificados revogados na CA. Nunca desfaz uma revogação.' },
          { label: 'Fonte da CRL', text: 'Uma URL de CRL explícita, ou detectada automaticamente do ponto de distribuição de CRL dos certificados emitidos.' },
          { label: 'Verificada', text: 'A assinatura da CRL é verificada contra o certificado da CA antes de qualquer aplicação.' },
        ]
      },
      {
        title: 'Inventário da CA e Painel de Controle',
        items: [
          { label: 'Sincronização de inventário', text: 'Importa certificados emitidos diretamente na CA que o UCM ainda não conhece (incremental por id de solicitação); a reconciliação está disponível pela API.' },
          { label: 'Solicitações pendentes', text: 'Listar, aprovar (reenvio + importação automática) ou negar solicitações aguardando aprovação do gerente da CA.' },
          { label: 'Saúde da CA', text: 'Status do serviço da CA, expiração do certificado da CA, próxima atualização da CRL e contagem de solicitações pendentes em um relance.' },
        ]
      },
    ],
    tips: [
      'Teste a conexão primeiro para verificar a autenticação e descobrir modelos disponíveis.',
      'Ative EOBO marcando a caixa de seleção no modal de assinatura: os campos são preenchidos automaticamente dos dados do CSR.',
      'A autenticação por certificado de cliente é recomendada para produção: não requer ingressar no domínio.',
      'Habilite o canal de administração WinRM para propagar revogações à CA e gerenciar solicitações pendentes a partir do UCM.',
    ],
    warnings: [
      'Kerberos requer que a máquina esteja ingressada no domínio ou um keytab configurado: não disponível no Docker.',
      'EOBO requer um certificado de agente de inscrição configurado no servidor AD CS.',
      'Sem o canal de administração WinRM, revogar um certificado AD CS apenas o marca como revogado no UCM: a CA Windows não é notificada.',
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
4. Opcionalmente insira o **Nome Comum da CA** (o hostname do servidor é usado se vazio)
5. Selecione o **Método de Autenticação**
6. Insira as credenciais para o método escolhido
7. Clique em **Testar Conexão** para verificar
8. Defina um **Modelo Padrão** e clique em **Salvar**

## Métodos de Autenticação

| Método | Requisitos | Melhor Para |
|--------|-----------|-------------|
| **Certificado de Cliente (mTLS)** | PEM cert/chave do cliente da CA | Produção: não requer ingressar no domínio |
| **Basic Auth** | Usuário + senha, HTTPS | Configurações simples: ative basic auth no IIS certsrv |
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
O UCM salva a solicitação como **Pendente** e rastreia o ID da solicitação da MS CA. A página não oferece verificação de status para ela: depois de emitida na CA Windows, importe o certificado, ou deixe a **Sincronização de inventário** pelo canal de administração WinRM importar os certificados que o UCM ainda não conhece.

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
   - **DN do Inscrito**: do sujeito do CSR (ex.: CN=João Silva,OU=Usuários,DC=corp,DC=local)
   - **UPN do Inscrito**: do e-mail SAN do CSR (ex.: joao.silva@corp.local)
4. Ajuste os valores se necessário
5. Clique em **Assinar**

O UCM passa isso como atributos de solicitação ADCS:
- EnrolleeObjectName:<DN>: identifica o usuário alvo no AD
- EnrolleePrincipalName:<UPN>: o nome de login do usuário

### EOBO vs Inscrição Direta

| Recurso | Inscrição Direta | EOBO |
|---------|------------------|------|
| Quem assina | O próprio usuário | Agente de inscrição em nome dele |
| Chave privada | Máquina do usuário | Pode estar no UCM (modelo CSR) |
| Permissão do modelo | Inscrição padrão | Requer direitos de agente de inscrição |
| Caso de uso | Autoatendimento | Gerenciamento PKI centralizado |

## Ciclo de Vida dos Certificados

### Renovar um certificado AD CS
A renovação **não** reassina localmente (a chave emissora reside na CA Windows). O UCM reenvia o CSR original do certificado: mesma chave, sujeito e SANs, à conexão e ao modelo que o emitiram, e atualiza o certificado no lugar. Se a CA retiver a renovação para aprovação do gerente, ela é rastreada como uma solicitação pendente.

### Revogar um certificado AD CS
A inscrição web do AD CS não tem endpoint de revogação. Revogar um certificado emitido pelo AD CS:
- **Sem o canal de administração WinRM**: marca como revogado apenas no UCM; a CA Windows não é notificada. Revogue-o também na CA.
- **Com o canal de administração WinRM**: o UCM propaga a revogação para a CA Windows (certutil -revoke + publicação da CRL). Remover um certificateHold também propaga o desfazer da revogação.

## Canal de Administração WinRM (opcional)

O canal de administração permite ao UCM executar na CA Windows operações de gerenciamento que a inscrição web não pode: revogar/desfazer revogação, publicar CRL, inventário e aprovar/negar solicitações pendentes. Usa PowerShell remoting + certutil.

### Requisitos
- **WinRM habilitado** na CA (Enable-PSRemoting; recomenda-se listener HTTPS na 5986)
- O pacote opcional **pywinrm** instalado no UCM (pip install pywinrm)
- Uma conta autorizada a **gerenciar certificados** na CA ("Issue and Manage Certificates")

### Configuração
1. Edite a conexão e habilite o **canal de administração WinRM**
2. Defina o host (por padrão, o servidor da conexão), a porta e o transporte
3. **Transporte**: Kerberos (recomendado, reutiliza o keytab da conexão) ou NTLM, sobre HTTP ou HTTPS
4. **Credenciais**: deixe vazio para reutilizar as da própria conexão (Basic/Kerberos). Conexões mTLS não têm credenciais WinRM reutilizáveis, defina uma conta dedicada
5. Clique em **Testar canal de administração**

| Modo de autenticação de inscrição | Reutiliza credenciais para WinRM? |
|-----------------------------------|------------------------------------|
| Kerberos (keytab) | Sim: mesmo principal/keytab |
| Basic (usuário/senha) | Sim: senha para NTLM/Kerberos |
| Certificado (mTLS) | Não: defina uma conta WinRM dedicada |

## Sincronização de Revogações via CRL

Habilite **Sincronizar revogações a partir da CRL da CA** na conexão para que o UCM busque periodicamente a CRL da CA e marque como revogados no UCM os certificados revogados na CA. É estritamente unidirecional (da CA para o UCM) e nunca desfaz a revogação de um certificado revogado no UCM. A URL da CRL vem da conexão ou é detectada automaticamente do ponto de distribuição de CRL dos certificados emitidos, e sua assinatura é verificada contra o certificado da CA antes de qualquer aplicação. Executa a cada hora, além de uma ação **Sincronizar CRL agora**.

## Sincronização de Inventário da CA

Habilite **Importar certificados emitidos diretamente na CA** para trazer ao repositório do UCM os certificados emitidos fora do UCM (ferramentas nativas, autoenrollment, ou anteriores ao UCM), de modo que o UCM rastreie todo o ciclo de vida. Lê o banco de dados da CA com certutil -view, importa os certificados que o UCM ainda não tem (deduplicados por número de série) e é incremental por id de solicitação (com opção de nova varredura completa). Uma visão de **reconciliação** lista os certificados presentes na CA mas não no UCM, e vice-versa. Executa a cada 6 horas, além de uma ação **Importar da CA agora**. Requer o canal de administração WinRM.

## Painel de Controle da CA

O painel de controle (aberto a partir da conexão, requer o canal de administração) gerencia as solicitações aguardando aprovação do gerente da CA e mostra a saúde da CA:
- **Solicitações pendentes**: listar, **Aprovar** (certutil -resubmit; o certificado emitido é importado automaticamente) ou **Negar** (certutil -deny)
- **Saúde**: status do serviço da CA, expiração do certificado da CA, próxima atualização da CRL e contagem de solicitações pendentes

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Teste de conexão falha | Verifique hostname, porta 443 e se certsrv está acessível |
| Nenhum modelo encontrado | Verifique se a conta UCM tem permissões de inscrição na CA |
| EOBO negado | Verifique certificado de agente de inscrição e permissões do modelo |
| Solicitação presa em pendente | Aprove-a no Painel de Controle da CA, ou no console da CA Windows e depois atualize o status no UCM |
| Teste do canal de administração falha | Verifique se o WinRM está habilitado na CA, a porta/transporte e se o pywinrm está instalado |
| Revogação não chega à CA | Habilite o canal de administração WinRM: sem ele, a revogação é local ao UCM |
| Pendente não detectado (CA em outro idioma) | Corrigido na v2.192: o UCM agora reconhece páginas de pendência localizadas do AD CS |

> 💡 Use o botão **Testar Conexão** para verificar a autenticação e descobrir modelos disponíveis antes de assinar. Habilite o **canal de administração WinRM** para gerenciar revogação, CRLs, inventário e solicitações pendentes diretamente do UCM.
`
  }
}
