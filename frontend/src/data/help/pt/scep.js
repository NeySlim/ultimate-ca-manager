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
          { label: 'Configuração', text: 'Configurações do servidor SCEP: seleção de CA, identificador de CA, auto-aprovação' },
          { label: 'Perfis', text: 'Endpoints de inscrição nomeados, cada um com URL, CA, modelo e desafio próprios' },
          { label: 'Senhas de Desafio', text: 'Gerenciar senhas de desafio por CA para inscrição de dispositivos' },
          { label: 'Informações', text: 'URLs de endpoints SCEP e instruções de integração' },
        ]
      },
      {
        title: 'Configuração',
        items: [
          { label: 'CA Assinante', text: 'Selecionar qual CA assina certificados inscritos via SCEP' },
          { label: 'Auto-Aprovação', text: 'Aprovar automaticamente solicitações com senhas de desafio válidas' },
          { label: 'Senha de Desafio', text: 'Segredo compartilhado que dispositivos usam para autenticar a inscrição' },
        ]
      },
      {
        title: 'Perfis',
        items: [
          { label: 'Segmento de URL', text: 'Cada perfil é servido em /scep/<segment>/pkiclient.exe — aponte cada frota de dispositivos ou perfil MDM para o seu próprio URL' },
          { label: 'Modelo de certificado', text: 'Quando um modelo está vinculado, os seus KU/EKU e validade governam cada certificado emitido pelo perfil' },
          { label: 'Desafio por perfil', text: 'Cada perfil tem sua própria senha de desafio, armazenada criptografada, com a mesma janela de expiração do desafio global' },
          { label: 'Endpoint padrão', text: 'O endpoint /scep/pkiclient.exe sem segmento continua servindo a configuração global' },
          { label: 'Validação Microsoft Intune', text: 'Um perfil pode validar contra o desafio SCEP próprio do Intune por dispositivo em vez de uma senha estática — requer um registro de aplicativo no Entra (permissões SCEP challenge validation + Application.Read.All) e auto-aprovação ativada' },
        ]
      },
    ],
    tips: [
      'Use senhas de desafio únicas por CA para melhor rastreabilidade de auditoria',
      'Auto-aprovação é conveniente, mas revise solicitações manualmente em ambientes de alta segurança',
      'Formato da URL SCEP: https://seu-servidor:porta/scep',
      'Perfis com Intune precisam da auto-aprovação ativada — a inscrição no Intune é uma ida e volta síncrona de validação e emissão, sem fila de aprovação do lado do Intune',
    ],
    warnings: [
      'Senhas de desafio são transmitidas na solicitação SCEP — use HTTPS para segurança de transporte',
    ],
  },
  helpGuides: {
    title: 'Servidor SCEP',
    content: `
## Visão Geral

O Simple Certificate Enrollment Protocol (SCEP) permite que dispositivos de rede — roteadores, switches, firewalls, endpoints gerenciados por MDM — solicitem e obtenham certificados automaticamente.

## Abas

### Solicitações
Visualize todas as solicitações de inscrição SCEP:
- **Pendente** — Aguardando aprovação manual (se auto-aprovação estiver desativada)
- **Aprovada** — Emitida com sucesso
- **Rejeitada** — Negada por um administrador

### Configuração
Configure o servidor SCEP:
- **Ativar/Desativar** — Alternar o serviço SCEP
- **CA Assinante** — Selecionar qual CA assina certificados inscritos via SCEP
- **Identificador de CA** — O identificador que dispositivos usam para localizar a CA correta
- **Auto-Aprovação** — Aprovar automaticamente solicitações com senhas de desafio válidas

### Perfis
Endpoints de inscrição nomeados, cada um servido em sua própria URL:

\`\`\`
https://seu-servidor:8443/scep/<perfil>/pkiclient.exe
\`\`\`

Cada perfil está vinculado a:
- **Sua própria CA** — frotas de dispositivos diferentes podem se inscrever em CAs diferentes
- **Um modelo de certificado opcional** — quando vinculado, o key usage, extended key usage e validade do modelo governam cada certificado emitido pelo perfil
- **Uma senha de desafio por perfil** — armazenada criptografada, com a mesma janela de expiração do desafio global
- **Uma política de aprovação** — auto-aprovação ou revisão manual por perfil

Aponte cada frota de dispositivos, perfil MDM ou tenant para sua própria URL de perfil. O endpoint \`/scep/pkiclient.exe\` sem segmento continua servindo a configuração global inalterada.

### Senhas de Desafio
Gerencie senhas de desafio por CA. Os dispositivos devem incluir uma senha de desafio válida em sua solicitação de inscrição para autenticação.

- **Ver senha** — Mostrar o desafio atual para uma CA
- **Regenerar** — Criar uma nova senha de desafio (invalida a anterior)

### Informações
Exibe a URL do endpoint SCEP e instruções de integração.

## Fluxo de Inscrição SCEP

1. Dispositivo envia uma solicitação **GetCACert** para obter o certificado da CA
2. Dispositivo gera um par de chaves e cria um CSR
3. Dispositivo envolve o CSR com a **senha de desafio** e envia um **PKCSReq**
4. O UCM valida a senha de desafio
5. Se auto-aprovação estiver ativada, o UCM assina e retorna o certificado
6. Se auto-aprovação estiver desativada, um administrador revisa e aprova/rejeita

## URLs SCEP

\`\`\`
https://seu-servidor:8443/scep                          (endpoint global)
https://seu-servidor:8443/scep/<perfil>/pkiclient.exe   (endpoint por perfil)
\`\`\`

Os dispositivos precisam da URL mais o identificador de CA para se inscrever. Use uma URL de perfil para direcionar a CA, o modelo e a senha de desafio daquele perfil.

## Aprovando/Rejeitando Solicitações

Para solicitações pendentes (auto-aprovação desativada):
1. Revise os detalhes da solicitação (sujeito, tipo de chave, desafio)
2. Clique em **Aprovar** para assinar e emitir o certificado
3. Ou clique em **Rejeitar** com um motivo

> ⚠ Senhas de desafio são transmitidas na solicitação SCEP. Sempre use HTTPS para o endpoint SCEP.

## Integração com Dispositivos

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://seu-servidor:8443/scep
  password <senha-de-desafio>
\`\`\`

### JAMF
Configure o perfil SCEP com:
- URL do servidor: \`https://seu-servidor:8443/scep\`
- Desafio: a senha do UCM

### Microsoft Intune
O Intune não suporta uma senha de desafio estática — ele emite o seu próprio desafio cifrado por dispositivo que só a API do Intune consegue validar. Num **perfil** SCEP (não o endpoint global), ative **Validação de desafio SCEP do Microsoft Intune** e forneça o ID do locatário, ID do cliente e segredo do cliente de um registro de aplicativo no Entra:

1. No Microsoft Entra ID, registre um aplicativo e conceda-lhe as permissões de aplicativo **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) e **Microsoft Graph → Application.Read.All**, ambas com consentimento de administrador
2. Insira o ID do locatário, ID do cliente e segredo do cliente no perfil e clique em **Testar conexão** para confirmar que o UCM consegue alcançar o Intune antes de salvar
3. No Intune, aponte a URL do servidor do perfil SCEP do dispositivo para o endpoint \`/scep/<segment>/pkiclient.exe\` deste perfil

Perfis com Intune ativado devem ter a **auto-aprovação** ativada — a inscrição no Intune é uma ida e volta síncrona de validação e emissão, sem fila do lado do Intune para revisão manual.
`
  }
}
