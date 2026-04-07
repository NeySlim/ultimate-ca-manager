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
    ],
    tips: [
      'Use senhas de desafio únicas por CA para melhor rastreabilidade de auditoria',
      'Auto-aprovação é conveniente, mas revise solicitações manualmente em ambientes de alta segurança',
      'Formato da URL SCEP: https://seu-servidor:porta/scep',
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

## URL SCEP

\`\`\`
https://seu-servidor:8443/scep
\`\`\`

Os dispositivos precisam desta URL mais o identificador de CA para se inscrever.

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

### Microsoft Intune / JAMF
Configure o perfil SCEP com:
- URL do servidor: \`https://seu-servidor:8443/scep\`
- Desafio: a senha do UCM
`
  }
}
