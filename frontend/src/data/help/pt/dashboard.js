export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
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
