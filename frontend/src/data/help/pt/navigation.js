export default {
  helpContent: {
    title: 'Navegação',
    subtitle: 'A barra superior, o menu Módulos e os módulos fixados',
    overview: 'A barra superior reúne as páginas principais, até três módulos que você fixa, o menu Módulos, a pesquisa e a sua conta. O menu Módulos lista todas as páginas que você pode abrir, em quatro grupos; as páginas às quais você não tem direito não são exibidas.',
    sections: [
      {
        title: 'Menu Módulos',
        items: [
          { label: 'Abrir', text: 'Selecione Módulos, ou pressione a seta para baixo no botão; o foco passa para a primeira página' },
          { label: 'Mover', text: 'As setas para cima e para baixo, Home e End permitem passar de uma página para outra; Esc fecha o menu e volta ao botão' },
          { label: 'Fixar', text: 'O botão de fixar ao lado de uma página a mantém na barra superior; no máximo três, e o menu avisa quando você tenta uma quarta' },
        ]
      },
      {
        title: 'Pesquisa e atalhos',
        items: [
          { label: 'Pesquisa', text: 'Pressione Ctrl K (Cmd K no macOS) ou selecione o campo de pesquisa para ir a uma página ou encontrar um certificado' },
          { label: 'Ajuda', text: 'Pressione ? fora de um campo de texto para abrir a ajuda da página atual' },
          { label: 'Largura de telefone', text: 'A barra superior exibe uma única lista de páginas em vez dos links e do menu' },
        ]
      },
      {
        title: 'Menu da conta',
        items: [
          { label: 'Conta', text: 'O seu perfil e as configurações, o idioma e o encerramento da sessão' },
        ]
      },
      {
        title: 'Menu de tema',
        items: [
          { label: 'Escolher', text: 'O botão de sol ou lua define o tema de cores e o modo; Sistema segue o seu dispositivo, e o ícone mostra o modo aplicado' },
          { label: 'Teclado', text: 'As setas para cima e para baixo percorrem as opções em ciclo; Esc ou Tab fecha o menu e volta ao botão' },
          { label: 'Salvo', text: 'A escolha é a de Configurações, Aparência, e acompanha você em todos os navegadores' },
        ]
      },
      {
        title: 'Notificações',
        items: [
          { label: 'Sino', text: 'O contador é o número de itens não lidos do painel: itens críticos e aprovações da fila da visão geral, e backups agendados falhados, restaurações falhadas ou sessões revogadas do log de auditoria' },
          { label: 'Ordem', text: 'Os itens da fila vêm primeiro, depois os do log de auditoria, do mais recente ao mais antigo' },
          { label: 'Direitos', text: 'Você só vê itens das fontes que pode ler; uma fonte sobre a qual você não tem direito não mostra nada' },
          { label: 'Lido', text: 'Marque um item ou todos como lidos; as marcas são salvas com as suas preferências, e um item resolvido sai do painel' },
          { label: 'Abrir', text: 'Abrir leva à página do item; nada é aprovado ou repetido a partir do painel' },
        ]
      },
    ],
    tips: [
      'Os seus itens fixados acompanham você em todos os navegadores e dispositivos onde você inicia sessão',
      'Uma página fixada que você perde o direito de abrir fica oculta, e volta se o direito for restabelecido antes de você alterar os seus itens fixados',
    ],
  },
}
