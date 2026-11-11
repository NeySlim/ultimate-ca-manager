export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Protocolo Simples de Inscrição de Certificados',
    overview: 'O SCEP permite que dispositivos de rede (roteadores, switches, firewalls) e soluções MDM solicitem e obtenham certificados automaticamente. Os dispositivos se autenticam usando uma senha de desafio.',
    sections: [
      {
        title: 'Abas',
        items: [
          { label: 'Solicitações', text: 'Solicitações de inscrição SCEP pendentes, aprovadas e rejeitadas' },
          { label: 'Configuração', text: 'Configurações do servidor SCEP: seleção de CA, auto-aprovação' },
          { label: 'Perfis', text: 'Endpoints de inscrição nomeados, cada um com URL, CA, modelo e desafio próprios' },
          { label: 'Registros de aplicativo do Intune', text: 'Registros de aplicativo no Entra (ID do locatário, ID do cliente, segredo do cliente) compartilhados pelos perfis que validam desafios do Intune; um segredo vazio na edição mantém o atual, Testar conexão solicita um token e descobre o serviço sem consumir nenhum desafio, e um app ainda usado por um perfil não pode ser excluído' },
          { label: 'Desafios', text: 'Ver e regenerar as senhas de desafio para inscrição de dispositivos' },
          { label: 'Informações', text: 'URLs de endpoints SCEP e instruções de integração' },
        ]
      },
      {
        title: 'Configuração',
        items: [
          { label: 'CA Assinante', text: 'Selecione qual CA assina os certificados inscritos via SCEP. Os dispositivos cifram a solicitação para esta CA, que deve portanto ter uma chave RSA em software: CAs EC, com HSM, sem chave, offline e revogadas não são listadas (v2.248)' },
          { label: 'Auto-Aprovação', text: 'Aprovar automaticamente solicitações com senhas de desafio válidas, ou renovações assinadas por um certificado emitido pelo mesmo ponto de acesso' },
          { label: 'Servir em HTTP simples', text: 'Desativado por padrão. Responde também ao SCEP na porta do protocolo HTTP (8080 por padrão), em http://seu-servidor:8080/scep/pkiclient.exe e nas URLs de perfil, para clientes como o sscep que não podem usar HTTPS. RFC 8894 §7.10: as mensagens SCEP já são protegidas, o envelope CMS mantém a senha de desafio privada' },
          { label: 'Senha de Desafio', text: 'Segredo compartilhado que dispositivos usam para autenticar a inscrição. Uma renovação (RenewalReq) assinada por um certificado que o mesmo ponto de acesso (perfil ou global) emitiu é autenticada por esse certificado, portanto o seu desafio não é verificado e rotacionar o segredo não impede os dispositivos já inscritos de renovar (RFC 8894 §2.4). Qualquer outro certificado continua a precisar do desafio do ponto de acesso' },
          { label: 'Chaves do dispositivo (v2.248)', text: 'Um dispositivo assina o seu pedido com uma chave RSA, ECDSA, Ed25519 ou ML-DSA; uma assinatura ML-DSA segue a RFC 9882 (resumo SHA-512). Ed448 é recusado, e ML-DSA também em modo FIPS' },
          { label: 'Nomes do pedido', text: 'Um pedido cujo sujeito ou nomes DNS violem a RFC 5280 (um CN com mais de 64 caracteres, um nome DNS com espaço, apóstrofo ou sublinhado, como o nome de um dispositivo iOS) é recusado com o seu motivo, depois de verificado o desafio e antes de entrar na fila, e o Intune é informado da recusa; uma renovação mantém os nomes que o seu certificado já tem. Construa o SAN DNS do Intune a partir de um valor seguro para DNS' },
        ]
      },
      {
        title: 'Perfis',
        items: [
          { label: 'Segmento de URL', text: 'Cada perfil é servido em /scep/<segment>/pkiclient.exe, aponte cada frota de dispositivos ou perfil MDM para o seu próprio URL' },
          { label: 'Modelo de certificado', text: 'Quando um modelo está vinculado, os seus KU/EKU e validade governam cada certificado emitido pelo perfil' },
          { label: 'Digest de assinatura (v2.251)', text: 'Os certificados emitidos através de um perfil são assinados com o digest do seu modelo, elevado ao que corresponde à chave da CA, como preferência que as políticas podem sobrepor. Sem modelo, aplica-se o digest da chave da CA' },
          { label: 'Desafio por perfil', text: 'Cada perfil tem sua própria senha de desafio, armazenada criptografada, com a mesma janela de expiração do desafio global' },
          { label: 'Endpoint padrão', text: 'O endpoint /scep/pkiclient.exe sem segmento continua servindo a configuração global' },
          { label: 'Validação Microsoft Intune', text: 'Um perfil pode validar contra o desafio SCEP próprio do Intune por dispositivo em vez de uma senha estática: escolha um registro de aplicativo na aba Registros de aplicativo do Intune (permissões SCEP challenge validation + Application.Read.All), a auto-aprovação continua obrigatória; na atualização, cada perfil existente recebe um app com o seu nome, deduplicado por locatário e cliente' },
          { label: 'Aprovação manual', text: 'Uma solicitação que chegou por um perfil é aprovada com o modelo desse perfil (validade, key usages), exatamente como a auto-aprovação a emitiria' },
          { label: 'Finalidades que nenhum inscrito pode ter', text: 'Um modelo vinculado a um perfil não pode conter assinatura OCSP, carimbo de tempo, qualquer finalidade ou Smartcard Logon, e uma renovação SCEP nunca os transfere; Smartcard Logon é permitido quando o perfil valida contra o Intune, que atesta a identidade' },
        ]
      },
    ],
    tips: [
      'Use senhas de desafio únicas por CA para melhor rastreabilidade de auditoria',
      'Auto-aprovação é conveniente, mas revise solicitações manualmente em ambientes de alta segurança',
      'Formato da URL SCEP: https://seu-servidor:porta/scep',
      'Perfis com Intune precisam da auto-aprovação ativada: a inscrição no Intune é uma ida e volta síncrona de validação e emissão, sem fila de aprovação do lado do Intune',
    ],
    warnings: [
      'Senhas de desafio são transmitidas na solicitação SCEP: use HTTPS para segurança de transporte',
    ],
  },
  helpGuides: {
    title: 'Servidor SCEP',
    content: `
## Visão Geral

O Simple Certificate Enrollment Protocol (SCEP) permite que dispositivos de rede: roteadores, switches, firewalls, endpoints gerenciados por MDM, solicitem e obtenham certificados automaticamente.

## Abas

### Solicitações
Visualize todas as solicitações de inscrição SCEP:
- **Pendente**: Aguardando aprovação manual (se auto-aprovação estiver desativada)
- **Aprovada**: Emitida com sucesso
- **Rejeitada**: Negada por um administrador

### Configuração
Configure o servidor SCEP:
- **Ativar/Desativar**: Alternar o serviço SCEP
- **CA Assinante**: Selecione qual CA assina os certificados inscritos via SCEP. Os dispositivos cifram a solicitação para esta CA, que deve portanto ter uma chave RSA em software: CAs EC, com HSM, sem chave, offline e revogadas não são listadas (v2.248)
- **Auto-Aprovação**: Aprovar automaticamente solicitações com senhas de desafio válidas, ou renovações assinadas por um certificado que o mesmo ponto de acesso emitiu
- **Servir em HTTP simples**: desativado por padrão. Responde também ao SCEP na porta do protocolo HTTP (8080 por padrão) para clientes que não podem usar HTTPS, como o sscep. RFC 8894 §7.10: as mensagens SCEP já são protegidas, portanto o TLS não é obrigatório; o envelope CMS mantém a senha de desafio privada

### Perfis
Endpoints de inscrição nomeados, cada um servido em sua própria URL:

\`\`\`
https://seu-servidor:8443/scep/<perfil>/pkiclient.exe
\`\`\`

Cada perfil está vinculado a:
- **Sua própria CA**: frotas de dispositivos diferentes podem se inscrever em CAs diferentes
- **Um modelo de certificado opcional**: quando vinculado, o key usage, extended key usage e validade do modelo governam cada certificado emitido pelo perfil
- **Finalidades que nenhum inscrito pode ter**: um modelo vinculado a um perfil não pode conter assinatura OCSP, carimbo de tempo, qualquer finalidade ou Smartcard Logon, e uma renovação SCEP nunca os transfere; Smartcard Logon é permitido quando o perfil valida contra o Intune, que atesta a identidade
- **Uma senha de desafio por perfil**: armazenada criptografada, com a mesma janela de expiração do desafio global (ou validação do Microsoft Intune, veja abaixo)
- **Uma política de aprovação**: auto-aprovação ou revisão manual por perfil

Aponte cada frota de dispositivos, perfil MDM ou tenant para sua própria URL de perfil. O endpoint \`/scep/pkiclient.exe\` sem segmento continua servindo a configuração global inalterada.

### Senhas de Desafio
A aba **Desafios** mostra as senhas de desafio. Os dispositivos devem incluir uma senha de desafio válida em sua solicitação de inscrição para autenticação.

- **Ver senha**: Mostrar o desafio atual para uma CA
- **Regenerar**: Criar uma nova senha de desafio (invalida a anterior para novas inscrições)

Uma renovação (RenewalReq) assinada por um certificado que o mesmo ponto de acesso (perfil ou global) emitiu é autenticada por esse certificado: a sua senha de desafio não é verificada, portanto um segredo regenerado não impede os dispositivos já inscritos de renovar (RFC 8894 §2.4).

### Informações
Exibe a URL do endpoint SCEP e instruções de integração.

## Fluxo de Inscrição SCEP

1. Dispositivo envia uma solicitação **GetCACert** para obter o certificado da CA
2. Dispositivo gera um par de chaves e cria um CSR
3. Dispositivo envolve o CSR com a **senha de desafio** e envia um **PKCSReq**
4. O UCM valida a senha de desafio
5. Se auto-aprovação estiver ativada, o UCM assina e retorna o certificado
6. Se auto-aprovação estiver desativada, um administrador revisa e aprova/rejeita

### Chaves do dispositivo
O dispositivo assina o seu PKCSReq com a sua própria chave: RSA, ECDSA, Ed25519 ou ML-DSA. Uma assinatura ML-DSA é verificada conforme a RFC 9882 (resumo SHA-512, o identificador de algoritmo da própria chave, sem parâmetros). As assinaturas Ed448 são recusadas, e as ML-DSA também em modo FIPS. O pedido continua cifrado para a CA assinante RSA.

## URLs SCEP

\`\`\`
https://seu-servidor:8443/scep/pkiclient.exe            (CA configurada)
https://seu-servidor:8443/scep/<perfil>/pkiclient.exe   (endpoint por perfil)
https://seu-servidor:8443/cgi-bin/pkiclient.exe         (CA configurada, caminho legado)
http://seu-servidor:8080/scep/pkiclient.exe             (com Servir em HTTP simples)
\`\`\`

Os dispositivos precisam da URL para se inscrever; \`/scep\` sozinho é a interface web, não um endpoint SCEP. Use uma URL de perfil para direcionar a CA, o modelo e a senha de desafio daquele perfil.

### Troca de CA (GetNextCACert)
O GetNextCACert serve a sucessora da CA do endpoint, assinada pela CA atual: outra CA com o mesmo pai e o mesmo DN de sujeito, não revogada, não offline, com chave RSA em software e que expira mais tarde. Uma CA que apenas compartilha o nome de exibição nunca é servida; sem sucessora, a resposta é 404.

## Aprovando/Rejeitando Solicitações

Para solicitações pendentes (auto-aprovação desativada):
1. Revise os detalhes da solicitação (sujeito, ID da transação, status, CSR)
2. Clique em **Aprovar** para assinar e emitir o certificado
3. Ou clique em **Rejeitar** com um motivo

Uma solicitação que chegou por um perfil é emitida com o modelo desse perfil (validade, key usages), exatamente como a auto-aprovação faria.

> A senha de desafio fica no CSR, que viaja dentro do envelope CMS cifrado para a CA (RFC 8894 §2.4), portanto o HTTP simples não a expõe. Um cliente que a envia como atributo assinado fora do envelope a expõe: mantenha esses clientes em HTTPS.

## Integração com Dispositivos

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://seu-servidor:8443/scep/pkiclient.exe
  password <senha-de-desafio>
\`\`\`

### JAMF
Configure o perfil SCEP com:
- URL do servidor: \`https://seu-servidor:8443/scep/pkiclient.exe\`, ou o \`/scep/<perfil>/pkiclient.exe\` de um perfil
- Desafio: a senha do UCM

### Microsoft Intune
O Intune não suporta uma senha de desafio estática: ele emite o seu próprio desafio cifrado por dispositivo que só a API do Intune consegue validar. Num **perfil** SCEP (não o endpoint global), ative **Validação de desafio SCEP do Microsoft Intune** e forneça o ID do locatário, ID do cliente e segredo do cliente de um registro de aplicativo no Entra:

1. No Microsoft Entra ID, registre um aplicativo e conceda-lhe as permissões de aplicativo **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) e **Microsoft Graph → Application.Read.All**, ambas com consentimento de administrador
2. Em **Registros de aplicativo do Intune**, adicione o registro de aplicativo uma única vez (nome, ID do locatário, ID do cliente, segredo do cliente) e clique em **Testar conexão** para confirmar que o UCM consegue alcançar o Intune; depois escolha-o no seletor **Registro de aplicativo** do perfil. Os perfis do mesmo locatário o compartilham, então o segredo é rotacionado em um único lugar
3. No Intune, aponte a URL do servidor do perfil SCEP do dispositivo para o endpoint \`/scep/<segment>/pkiclient.exe\` deste perfil

Perfis com Intune ativado devem ter a **auto-aprovação** ativada: a inscrição no Intune é uma ida e volta síncrona de validação e emissão, sem fila do lado do Intune para revisão manual.
`
  }
}
