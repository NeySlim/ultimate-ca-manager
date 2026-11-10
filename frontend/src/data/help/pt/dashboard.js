export default {
  helpContent: {
    title: 'Visão geral',
    subtitle: 'O que requer ação e o estado da PKI',
    overview: 'Seis cartões independentes sobre os dados ao vivo da sua PKI. Cada cartão é carregado por conta própria e mostra o seu próprio estado de carregamento, vazio, erro ou falta de permissão. Todo contador que tem uma lista abre a lista de certificados filtrada exatamente pelos certificados que ele conta.',
    sections: [
      {
        title: 'Cartões',
        items: [
          { label: 'A tratar', text: 'Os seis itens mais urgentes, os críticos primeiro, cada um com um link para o seu registro; um nível recolhido dá o total por tipo, e os quatro tipos de renovação abrem a lista de certificados' },
          { label: 'Saúde da automação', text: 'Por protocolo (ACME, SCEP, EST), os sucessos e as falhas do dia, e o estado do agendador' },
          { label: 'Hierarquia', text: 'As autoridades em árvore sob a sua CA superior, com o estado da CRL e do OCSP, uma marca de offline ou de assinatura cruzada, e os certificados que cada uma emitiu em 7 dias; cada autoridade abre a sua página' },
          { label: 'Horizonte de expiração', text: 'Os contadores de certificados a expirar e expirados, cada um abrindo a sua lista, e os cinco certificados que expiram em seguida' },
          { label: 'Conformidade', text: 'Certificados ativos por algoritmo de chave e por fragilidade (RSA abaixo de 3072 bits, hash de assinatura fraco, certificados de servidor com mais de 398 dias, cadeia incompleta, sem chave privada); cada contador abre a lista correspondente' },
          { label: 'Últimas operações', text: 'As cinco operações mais recentes; com a permissão de auditoria, um link abre todo o histórico' },
        ]
      },
    ],
    tips: [
      'Escolha a predefinição Operador, Gestor ou Todos os cartões no cabeçalho para definir quais cartões são exibidos',
      'O layout é salvo na sua conta e acompanha você entre navegadores',
      'Na lista de certificados, os filtros vindos da visão geral aparecem como chips; remova um com o seu x',
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
