export default {
  helpContent: {
    title: 'Armazenamento de Confiança',
    subtitle: 'Gerenciar certificados confiáveis',
    overview: 'Importe e gerencie certificados de CA raiz e intermediários confiáveis. O armazenamento de confiança é usado para validação de cadeia e pode ser sincronizado com o armazenamento de confiança do sistema operacional.',
    sections: [
      {
        title: 'Tipos de Certificado',
        definitions: [
          { term: 'CA Raiz', description: 'Âncora de confiança autoassinada de nível superior' },
          { term: 'Intermediário', description: 'Certificado de CA assinado por uma raiz ou outro intermediário' },
          { term: 'Autenticação de Cliente', description: 'Certificado usado para autenticação de cliente (mTLS)' },
          { term: 'Assinatura de Código', description: 'Certificado usado para verificação de assinatura de código' },
          { term: 'Personalizado', description: 'Certificado confiável categorizado manualmente' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Importar Arquivo', text: 'Enviar arquivos de certificado PEM, DER ou PKCS#7' },
          { label: 'Importar URL', text: 'Buscar um certificado de uma URL remota' },
          { label: 'Adicionar PEM', text: 'Colar texto de certificado codificado em PEM diretamente' },
          { label: 'Sincronizar do Sistema', text: 'Importar CAs confiáveis do SO para o UCM' },
          { label: 'Exportar', text: 'Baixar certificados confiáveis individualmente' },
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

O Armazenamento de Confiança gerencia certificados de CA confiáveis usados para validação de cadeia. Importe CAs raiz e intermediárias de fontes externas ou sincronize com o armazenamento de confiança do sistema operacional.

## Categorias de Certificados

- **CA Raiz** — Âncoras de confiança autoassinadas
- **Intermediário** — CAs assinadas por raiz ou outros intermediários
- **Autenticação de Cliente** — Certificados para autenticação de cliente mTLS
- **Assinatura de Código** — Certificados para verificação de assinatura de código
- **Personalizado** — Certificados categorizados manualmente

## Importando Certificados

### De Arquivo
Envie arquivos de certificado nestes formatos:
- **PEM** — Codificado em Base64 (único ou em pacote)
- **DER** — Formato binário
- **PKCS#7 (P7B)** — Cadeia de certificados

### De URL
Busque um certificado de um endpoint HTTPS remoto. O UCM baixa e importa a cadeia de certificados do servidor.

### Colar PEM
Cole texto de certificado codificado em PEM diretamente na área de texto.

### Sincronizar do Sistema
Importe todas as CAs confiáveis do armazenamento de confiança do sistema operacional. Isso popula o UCM com as mesmas CAs raiz confiáveis pelo SO (ex.: pacote CA do Mozilla no Linux).

> 💡 Sincronizar do Sistema é uma importação única. Alterações no armazenamento de confiança do SO não são refletidas automaticamente.

## Gerenciando Entradas

- **Filtrar por finalidade** — Restringir a lista por categoria de certificado
- **Pesquisar** — Encontrar certificados pelo nome do sujeito
- **Exportar** — Baixar certificados individuais em formato PEM
- **Excluir** — Remover um certificado do armazenamento de confiança

## Casos de Uso

### Validação de Cadeia
Ao verificar uma cadeia de certificados, o UCM verifica o armazenamento de confiança para CAs raiz reconhecidas.

### mTLS
Certificados de cliente apresentados durante autenticação TLS mútua são validados contra o armazenamento de confiança.

### ACME
Quando o UCM atua como cliente ACME (Let's Encrypt), o armazenamento de confiança é usado para verificar o certificado da CA ACME.
`
  }
}
