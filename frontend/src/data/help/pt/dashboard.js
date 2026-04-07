export default {
  helpContent: {
    title: 'Painel',
    subtitle: 'Visão geral e monitoramento do sistema',
    overview: 'Visão geral em tempo real da sua infraestrutura PKI. Os widgets exibem o status dos certificados, alertas de expiração, saúde do sistema e atividade recente. O layout é totalmente personalizável com arrastar e soltar.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Estatísticas', text: 'Total de CAs, certificados ativos, CSRs pendentes e contagens de certificados expirando em breve' },
          { label: 'Tendência de Certificados', text: 'Gráfico do histórico de emissão ao longo do tempo' },
          { label: 'Distribuição de Status', text: 'Gráfico de pizza: válidos / expirando / expirados / revogados' },
          { label: 'Próxima Expiração', text: 'Certificados expirando nos próximos 30 dias' },
          { label: 'Status do Sistema', text: 'Saúde dos serviços: ACME, SCEP, EST, OCSP, CRL/CDP, status de renovação automática' },
          { label: 'Atividade Recente', text: 'Últimas operações realizadas no sistema' },
          { label: 'Certificados Recentes', text: 'Certificados emitidos ou importados recentemente' },
          { label: 'Autoridades Certificadoras', text: 'Lista de CAs com informações da cadeia' },
          { label: 'Contas ACME', text: 'Contas de clientes ACME registradas' },
        ]
      },
    ],
    tips: [
      'Arraste os widgets para reorganizar o layout do seu painel',
      'Clique no ícone de olho no cabeçalho para mostrar/ocultar widgets específicos',
      'O painel é atualizado em tempo real via WebSocket — não é necessário atualizar manualmente',
      'O layout é salvo por usuário e persiste entre sessões',
    ],
  },
  helpGuides: {
    title: 'Painel',
    content: `
## Visão Geral

O Painel é o seu centro de monitoramento. Ele exibe métricas em tempo real, gráficos e alertas sobre toda a sua infraestrutura PKI através de widgets personalizáveis.

## Widgets

### Cartão de Estatísticas
Exibe quatro contadores principais:
- **Total de CAs** — Autoridades Certificadoras Raiz e Intermediárias
- **Certificados Ativos** — Certificados válidos e não revogados
- **CSRs Pendentes** — Requisições de Assinatura de Certificado aguardando aprovação
- **Expirando em Breve** — Certificados expirando nos próximos 30 dias

### Tendência de Certificados
Um gráfico de linha mostrando a emissão de certificados ao longo do tempo. Passe o mouse sobre os pontos para ver contagens exatas.

### Distribuição de Status
Gráfico de pizza mostrando a distribuição dos estados dos certificados:
- **Válido** — Dentro do período de validade e não revogado
- **Expirando** — Expira dentro de 30 dias
- **Expirado** — Passou da data "Não Depois"
- **Revogado** — Explicitamente revogado

### Próxima Expiração
Lista os certificados que expiram mais cedo. Clique em qualquer certificado para navegar até seus detalhes. Configure o limite em **Configurações → Geral**.

### Status do Sistema
Mostra a saúde dos serviços do UCM:
- Servidor ACME (ativado/desativado)
- Servidor SCEP
- Protocolo EST (ativado/desativado, CA atribuída)
- Regeneração automática de CRL com contagem de CDP
- Respondedor OCSP
- Status de renovação automática
- Tempo de atividade do serviço

### Atividade Recente
Um feed ao vivo das últimas operações: emissão de certificados, revogações, importações, logins de usuários. Atualiza em tempo real via WebSocket.

### Autoridades Certificadoras
Visualização rápida de todas as CAs com seu tipo (Raiz/Intermediária) e contagem de certificados.

### Contas ACME
Lista as contas de clientes ACME registradas e suas contagens de pedidos.

## Personalização

### Reorganizando Widgets
Arraste qualquer widget pelo seu cabeçalho para reposicioná-lo. O layout usa uma grade responsiva que se adapta ao tamanho da sua tela.

### Mostrando/Ocultando Widgets
Clique no **ícone de olho** no cabeçalho da página para alternar a visibilidade de widgets individuais. Widgets ocultos são lembrados entre sessões.

### Persistência do Layout
Sua configuração de layout é salva por usuário no navegador. Ela persiste entre sessões e dispositivos que compartilham o mesmo perfil de navegador.

## Atualizações em Tempo Real
O painel recebe atualizações ao vivo via WebSocket. Não é necessário atualizar manualmente — novos certificados, mudanças de status e entradas de atividade aparecem automaticamente.

> 💡 Se o WebSocket estiver desconectado, um indicador amarelo aparece na barra lateral. Os dados serão atualizados na reconexão.
`
  }
}
