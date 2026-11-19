export default {
  helpContent: {
    title: 'Armazenamento de Confiança',
    subtitle: 'Gerenciar certificados confiáveis',
    overview: 'Mantenha certificados de CA raiz e intermediários confiáveis. A vista de cadeia de um certificado e as suas exportações completam a cadeia com um certificado do armazenamento de confiança cujo sujeito corresponde ao nome do emissor. O armazenamento pode ser preenchido a partir do armazenamento de confiança do sistema operacional ou das CAs gerenciadas pelo UCM.',
    sections: [
      {
        title: 'Tipos de Certificado',
        definitions: [
          { term: 'CA Raiz', description: 'Âncora de confiança autoassinada de nível superior' },
          { term: 'Intermediário', description: 'Certificado de CA assinado por uma raiz ou outro intermediário' },
          { term: 'Sistema', description: 'Importado do armazenamento de confiança do sistema operacional' },
          { term: 'Assinatura de Código', description: 'Certificado usado para verificação de assinatura de código' },
          { term: 'E-mail', description: 'Certificado usado para S/MIME' },
          { term: 'Personalizado', description: 'Certificado confiável categorizado manualmente' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Adicionar', text: 'Adicionar certificados das CAs gerenciadas pelo UCM. Um certificado externo é adicionado pela API (POST /api/v2/truststore com PEM, ou /api/v2/truststore/import com um arquivo PEM ou DER)' },
          { label: 'Sincronizar do Sistema', text: 'Importar CAs confiáveis do SO para o UCM, até a quantidade escolhida (500 por padrão, 1000 no máximo)' },
          { label: 'Exportar', text: 'Baixar certificados confiáveis individualmente' },
          { label: 'Eliminar seleção', text: 'Selecione vários certificados e remova-os em conjunto, por exemplo as CAs do sistema filtradas como expiradas; só são removidas as linhas que os filtros atuais mostram' },
        ]
      },
    ],
    tips: [
      'Use "Sincronizar do Sistema" para popular rapidamente o armazenamento de confiança com CAs do SO',
      'Filtre por finalidade para focar em categorias específicas de certificados',
    ],
  },
  helpGuides: {
    title: 'Armazenamento de Confiança',
    content: `
## Visão Geral

O Armazenamento de Confiança mantém certificados de CA confiáveis. Preencha-o a partir das CAs gerenciadas pelo UCM ou do armazenamento de confiança do sistema operacional.

## Categorias de Certificados

- **CA Raiz**: Âncoras de confiança autoassinadas
- **Intermediário**: CAs assinadas por raiz ou outros intermediários
- **Sistema**: Importado do armazenamento de confiança do sistema operacional
- **Assinatura de Código**: Certificados para verificação de assinatura de código
- **E-mail**: Certificados para S/MIME
- **Personalizado**: Certificados categorizados manualmente

## Adicionando Certificados

### De CAs gerenciadas
**Adicionar** lista as CAs gerenciadas pelo UCM: selecione as que deseja tornar confiáveis.

### Certificados externos
A página não tem formulário de envio para um certificado de fora do UCM. Adicione-o pela API: \`POST /api/v2/truststore\` com o seu PEM, ou \`POST /api/v2/truststore/import\` com um arquivo PEM ou DER.

### Sincronizar do Sistema
Importe as CAs confiáveis do armazenamento de confiança do sistema operacional (ex.: pacote CA do Mozilla no Linux), até a quantidade escolhida: 500 por padrão, 1000 no máximo.

> 💡 Sincronizar do Sistema é uma importação única. Alterações no armazenamento de confiança do SO não são refletidas automaticamente.

## Gerenciando Entradas

- **Filtrar por finalidade**: Restringir a lista por categoria de certificado
- **Pesquisar**: Encontrar certificados pelo nome do sujeito
- **Exportar**: Baixar certificados individuais em formato PEM
- **Excluir**: Remover um certificado do armazenamento de confiança
- **Eliminar seleção**: Selecione vários certificados e remova-os em conjunto, por exemplo as CAs do sistema filtradas como expiradas; só são removidas as linhas que os filtros atuais mostram

## Casos de Uso

### Cadeias
A vista de cadeia de um certificado, e as suas exportações com a cadeia, usam um certificado do armazenamento de confiança cujo sujeito corresponde ao nome do emissor para completar a cadeia. Nenhuma assinatura é verificada contra o armazenamento de confiança.

O armazenamento de confiança não participa da autenticação de cliente mTLS (que usa a CA confiável escolhida em Configurações › Segurança) nem da conexão do cliente ACME com a sua CA.
`
  }
}
