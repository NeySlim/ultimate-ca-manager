export default {
  helpContent: {
    title: 'Relatórios',
    subtitle: 'Relatórios de conformidade e inventário PKI',
    overview: 'Gere, baixe e agende relatórios para auditoria de conformidade. Os relatórios cobrem inventário de certificados, certificados expirando, hierarquia de CA, atividade de auditoria e status de conformidade com políticas. Baixe um relatório PDF executivo para revisão gerencial.',
    sections: [
      {
        title: 'Tipos de Relatório',
        items: [
          { label: 'Inventário de Certificados', text: 'Lista completa de todos os certificados com status' },
          { label: 'Certificados Expirando', text: 'Certificados expirando dentro de uma janela de tempo especificada' },
          { label: 'Hierarquia de CA', text: 'Estrutura da Autoridade Certificadora e estatísticas' },
          { label: 'Resumo de Auditoria', text: 'Eventos de segurança e resumo de atividades dos usuários' },
          { label: 'Status de Conformidade', text: 'Conformidade com políticas e resumo de violações' },
        ]
      },
      {
        title: 'Relatório PDF Executivo',
        items: [
          { label: 'Baixar PDF', text: 'Relatório PDF profissional com um clique para gestores e auditores' },
          { label: 'Conteúdo', text: 'Resumo executivo, avaliação de risco, inventário de certificados, pontuações de conformidade, infraestrutura de CA, atividade de auditoria e recomendações' },
          { label: 'Gráficos e Visuais', text: 'Inclui medidor de risco, distribuição de status, linha do tempo de expiração e detalhamento de conformidade' },
        ]
      },
      {
        title: 'Agendamento',
        items: [
          { label: 'Relatório de Expiração', text: 'E-mail diário com certificados expirando em breve' },
          { label: 'Relatório de Conformidade', text: 'E-mail semanal com status de conformidade com políticas' },
        ]
      },
    ],
    tips: [
      'Use o relatório PDF executivo para revisões gerenciais e auditorias de conformidade.',
      'Baixe relatórios como CSV para análise em planilhas ou JSON para automação.',
      'Use o recurso de envio de teste para verificar a entrega de e-mail antes de ativar agendamentos.',
    ],
  },
  helpGuides: {
    title: 'Relatórios',
    content: `
## Visão Geral

Gere, baixe e agende relatórios de conformidade PKI. Os relatórios fornecem visibilidade sobre sua infraestrutura de certificados para auditoria, conformidade e planejamento operacional.

## Tipos de Relatório

### Inventário de Certificados
Lista completa de todos os certificados gerenciados pelo UCM. Inclui sujeito, emissor, número de série, datas de validade, tipo de chave e status atual. Use para auditorias de conformidade e documentação de infraestrutura.

### Certificados Expirando
Certificados expirando dentro de uma janela de tempo especificada (padrão: 30 dias). Crítico para evitar interrupções — revise este relatório regularmente ou agende-o para entrega diária.

### Hierarquia de CA
Estrutura da Autoridade Certificadora mostrando relações pai-filho, contagens de certificados por CA e status da CA. Útil para entender sua topologia PKI.

### Resumo de Auditoria
Eventos de segurança e resumo de atividades dos usuários. Inclui tentativas de login, operações de certificado, violações de políticas e alterações de configuração. Essencial para auditorias de segurança.

### Status de Conformidade
Conformidade com políticas e resumo de violações. Mostra quais certificados estão em conformidade com suas políticas e quais as violam. Necessário para conformidade regulatória.

## Relatório PDF Executivo

Clique em **Baixar PDF** no canto superior direito para gerar um relatório executivo profissional adequado para revisões gerenciais, apresentações ao conselho e auditorias de conformidade.

### Conteúdo
O relatório PDF inclui 9 seções:
1. **Página de Capa** — Métricas principais, medidor de risco e descobertas principais de relance
2. **Índice** — Navegação rápida
3. **Resumo Executivo** — Saúde geral da PKI, distribuição de certificados e nível de risco
4. **Avaliação de Risco** — Descobertas críticas, certificados expirando, algoritmos fracos
5. **Inventário de Certificados** — Detalhamento por status, tipo de chave e CA emissora
6. **Análise de Conformidade** — Distribuição de pontuações, detalhamento de notas, pontuações por categoria
7. **Ciclo de Vida de Certificados** — Linha do tempo de expiração e taxa de automação
8. **Infraestrutura de CA** — Detalhes de CAs raiz e intermediárias, hierarquia
9. **Recomendações** — Itens acionáveis baseados no estado atual da PKI

### Gráficos e Visuais
O relatório inclui elementos visuais: barra de medidor de risco, distribuição de status, detalhamento de notas de conformidade e linha do tempo de expiração — projetado para partes interessadas não técnicas.

> 💡 O relatório PDF é gerado a partir de dados ao vivo. Baixe-o antes de reuniões para o snapshot mais atual.

## Gerando Relatórios

1. Encontre o relatório desejado na lista
2. Clique em **▶ Gerar** para criar uma prévia
3. A prévia aparece abaixo como uma tabela formatada
4. Clique em **Fechar** para dispensar a prévia

## Baixando Relatórios

Cada linha de relatório tem botões de download:
- **CSV** — Formato de planilha para Excel, Google Sheets ou LibreOffice
- **JSON** — Dados estruturados para automação e integração

> 💡 Relatórios CSV são mais fáceis para partes interessadas não técnicas. JSON é melhor para scripts e integrações de API.

## Agendando Relatórios

### Relatório de Expiração (Diário)
Envia automaticamente um relatório de expiração de certificados todos os dias para destinatários configurados. Ative para detectar certificados expirando antes que causem interrupções.

### Relatório de Conformidade (Semanal)
Envia um resumo de conformidade com políticas toda semana. Útil para monitoramento contínuo de conformidade sem esforço manual.

### Configuração
1. Clique em **Agendar Relatórios** no canto superior direito
2. Ative os relatórios que deseja agendar
3. Adicione endereços de e-mail dos destinatários (pressione Enter ou clique em Adicionar)
4. Clique em Salvar

### Envio de Teste
Antes de ativar agendamentos, use o botão ✈️ em qualquer linha de relatório para enviar um relatório de teste para um endereço de e-mail específico. Isso verifica se o SMTP está configurado corretamente e se o formato do relatório atende suas necessidades.

> ⚠ Relatórios agendados requerem SMTP configurado em **Configurações → E-mail**. O envio de teste falhará se o SMTP não estiver configurado.

## Permissões

- **read:reports** — Gerar e baixar relatórios
- **read:audit + export:audit** — Baixar relatório PDF executivo
- **write:settings** — Configurar agendamentos de relatórios

> 💡 Agende o relatório de expiração primeiro — é o mais valioso operacionalmente e ajuda a prevenir interrupções relacionadas a certificados.
`
  }
}
