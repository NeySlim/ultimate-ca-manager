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
    title: 'Visão geral',
    content: `
## Visão Geral

A Visão geral é a página inicial: seis cartões independentes sobre os dados ao vivo da sua PKI. Cada cartão é carregado por conta própria e mostra o seu próprio estado de carregamento, vazio, erro ou falta de permissão.

## Cartões

### A tratar
Os seis itens mais urgentes, os críticos primeiro, cada um com um link para o seu registro. Um nível recolhido dá o total por tipo; os quatro tipos de renovação abrem a lista de certificados.

### Saúde da automação
Por protocolo (ACME, SCEP, EST), os sucessos e as falhas do dia e a última operação, além do estado do agendador.

### Hierarquia
As autoridades em árvore sob a sua CA superior, com o estado da CRL e do OCSP, uma marca de offline ou de assinatura cruzada, e os certificados que cada uma emitiu em 7 dias. Cada autoridade abre a sua página.

### Horizonte de expiração
Os contadores de certificados a expirar e expirados, cada um abrindo a sua lista, e os cinco certificados que expiram em seguida.

### Conformidade
Certificados ativos por algoritmo de chave e por fragilidade: RSA abaixo de 3072 bits, hash de assinatura fraco, certificados de servidor com mais de 398 dias, cadeia incompleta, sem chave privada. Cada contador abre a lista correspondente.

### Últimas operações
As cinco operações mais recentes. Sem **read:audit**, você vê apenas os seus próprios eventos; com essa permissão, um link abre todo o histórico na página Logs de Auditoria.

## Abrindo uma lista filtrada
Todo contador que tem uma lista abre a página Certificados filtrada exatamente pelos certificados que ele conta. O filtro aparece como um chip acima da tabela; remova-o com o seu x.

## Escolhendo os cartões
Escolha a predefinição **Operador**, **Gestor** ou **Todos os cartões** no cabeçalho da página para definir quais cartões são exibidos. O layout é salvo na sua conta e acompanha você entre navegadores.

## Atualização
Os cartões são carregados quando a página abre; um cartão com erro oferece **Tentar novamente**. O ícone de conexão na barra superior mostra o estado do link ao vivo, e a barra de status na parte inferior mostra a versão e se o serviço responde.
`
  }
}
