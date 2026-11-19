export default {
  helpContent: {
    title: 'Painel',
    subtitle: 'Visão geral e monitoramento do sistema',
    overview: 'Visão geral em tempo real da sua infraestrutura PKI. Os widgets exibem o status dos certificados, alertas de expiração, saúde do sistema e atividade recente. O layout é totalmente personalizável com arrastar e soltar.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Estatísticas', text: 'Total de certificados (expirados e revogados incluídos), CAs, CSRs pendentes e contas ACME, mais os certificados SSH quando existe uma CA SSH' },
          { label: 'Atividade de Certificados', text: 'Certificados emitidos, revogados e expirados por dia no período escolhido' },
          { label: 'Distribuição de Status', text: 'Gráfico de pizza: válidos / expirando / expirados / revogados' },
          { label: 'Próxima Expiração', text: 'Os seis certificados válidos que expiram primeiro, qualquer que seja a data; o assinante TSA dedicado configurado é assinalado com uma etiqueta "TSA signer" (v2.218)' },
          { label: 'Status do Sistema', text: 'Saúde dos serviços: ACME, SCEP, EST, OCSP, CRL/CDP, TSA (v2.218), renovação automática, SMTP e webhooks. Os emblemas mostram um estado de aviso âmbar distinto (assinante TSA perto de expirar, SMTP configurado mas desativado) e sua mensagem de status ao passar o mouse' },
          { label: 'Atividade Recente', text: 'Últimas operações realizadas no sistema, com read:audit; sem essa permissão, apenas os seus próprios eventos' },
          { label: 'Certificados Recentes', text: 'Certificados emitidos ou importados recentemente' },
          { label: 'Autoridades Certificadoras', text: 'Últimas CAs, cada uma marcada como Root ou Sub' },
          { label: 'Contas ACME', text: 'Contas de clientes ACME registradas' },
          { label: 'Expiração do Trust Store', text: 'Certificados confiáveis que expiram primeiro' },
        ]
      },
    ],
    tips: [
      'Clique em Editar layout no cabeçalho e arraste os widgets para reorganizá-los',
      'Clique no botão Personalizar painel (ícone de controles deslizantes) no cabeçalho e, em seguida, no olho ao lado de um widget para mostrá-lo ou ocultá-lo',
      'O painel é atualizado em tempo real via WebSocket: não é necessário atualizar manualmente',
      'O layout é salvo neste navegador, para todas as contas que entram a partir dele',
    ],
  },
  helpGuides: {
    title: 'Painel',
    content: `
## Visão Geral

O Painel é o seu centro de monitoramento. Ele exibe métricas em tempo real, gráficos e alertas sobre toda a sua infraestrutura PKI através de widgets personalizáveis.

## Widgets

### Cartão de Estatísticas
Exibe estes contadores:
- **Certificados**: todos os certificados, expirados e revogados incluídos
- **CAs**: Autoridades Certificadoras Raiz e Intermediárias
- **CSRs**: Requisições de Assinatura de Certificado aguardando assinatura
- **ACME**: contas ACME registradas
- **Certificados SSH**: exibido quando existe uma CA SSH

### Atividade de Certificados
Um gráfico de área dos certificados emitidos, revogados e expirados por dia no período escolhido. Passe o mouse sobre os pontos para ver contagens exatas.

### Distribuição de Status
Gráfico de pizza mostrando a distribuição dos estados dos certificados:
- **Válido**: Dentro do período de validade e não revogado
- **Expirando**: Expira dentro de 30 dias
- **Expirado**: Passou da data "Não Depois"
- **Revogado**: Explicitamente revogado

### Próxima Expiração
Lista os seis certificados válidos que expiram primeiro, qualquer que seja a data. Clique em qualquer certificado para navegar até seus detalhes.

### Status do Sistema
Mostra a saúde dos serviços do UCM:
- Servidor ACME (ativado/desativado)
- Servidor SCEP
- Protocolo EST (ativado/desativado, CA atribuída)
- Regeneração automática de CRL com contagem de CDP
- Respondedor OCSP
- TSA, SMTP e webhooks
- Status de renovação automática

O painel Saúde do Sistema mostra também a conexão WebSocket, o banco de dados, a API e a hora da última atualização.

### Atividade Recente
Um feed ao vivo das últimas operações: emissão de certificados, revogações, importações, logins de usuários. Atualiza em tempo real via WebSocket. O feed completo exige **read:audit**, como a página Logs de Auditoria; sem essa permissão, você vê apenas os seus próprios eventos.

### Autoridades Certificadoras
Visualização rápida das últimas CAs, cada uma marcada como Root ou Sub.

### Expiração do Trust Store
Certificados confiáveis que expiram primeiro.

### Contas ACME
Lista as contas de clientes ACME registradas e suas contagens de pedidos.

## Personalização

### Reorganizando Widgets
Clique em **Editar layout** no cabeçalho da página e arraste qualquer widget pelo seu cabeçalho para reposicioná-lo. O layout usa uma grade responsiva que se adapta ao tamanho da sua tela.

### Mostrando/Ocultando Widgets
Clique em **Personalizar painel** (ícone de controles deslizantes) no cabeçalho da página e, em seguida, no olho ao lado de um widget para alternar a sua visibilidade. Widgets ocultos são lembrados entre sessões.

### Persistência do Layout
Seu layout é salvo no navegador, não na sua conta: todas as contas que entram a partir do mesmo perfil de navegador o compartilham, e outro navegador começa com o layout padrão.

## Atualizações em Tempo Real
O painel recebe atualizações ao vivo via WebSocket. Não é necessário atualizar manualmente: novos certificados, mudanças de status e entradas de atividade aparecem automaticamente.

> 💡 O ponto verde na barra lateral indica uma conexão WebSocket ativa e desaparece quando ela cai. Os dados serão atualizados na reconexão.
`
  }
}
