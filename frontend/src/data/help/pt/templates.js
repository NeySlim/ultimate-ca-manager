export default {
  helpContent: {
    title: 'Modelos de Certificado',
    subtitle: 'Perfis de certificado reutilizáveis',
    overview: 'Defina perfis de certificado reutilizáveis com campos de sujeito, key usage, extended key usage, períodos de validade e outras extensões pré-configurados. Aplique modelos ao emitir ou assinar certificados.',
    sections: [
      {
        title: 'Tipos de Modelo',
        definitions: [
          { term: 'Entidade Final', description: 'Para certificados de servidor, cliente, assinatura de código e e-mail' },
          { term: 'CA', description: 'Para criar Autoridades Certificadoras intermediárias' },
        ]
      },
      {
        title: 'Recursos',
        items: [
          { label: 'Padrões de Sujeito', text: 'Pré-preencher Organização, OU, País, Estado, Cidade' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, etc.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Validade', text: 'Período de validade padrão em dias' },
          { label: 'Duplicar', text: 'Clonar um modelo existente e modificá-lo' },
          { label: 'Importar/Exportar', text: 'Compartilhar modelos como arquivos JSON entre instâncias UCM' },
        ]
      },
    ],
    tips: [
      'Crie modelos separados para servidores TLS, clientes e assinatura de código',
      'Use a ação Duplicar para criar variações rapidamente de um modelo',
    ],
  },
  helpGuides: {
    title: 'Modelos de Certificado',
    content: `
## Visão Geral

Modelos definem perfis de certificado reutilizáveis. Em vez de configurar manualmente Key Usage, Extended Key Usage, validade e campos de sujeito toda vez, aplique um modelo para pré-preencher tudo.

## Tipos de Modelo

### Modelos de Entidade Final
Para certificados de servidor, certificados de cliente, assinatura de código e proteção de e-mail. Esses modelos tipicamente definem:
- **Key Usage** — Digital Signature, Key Encipherment
- **Extended Key Usage** — Server Auth, Client Auth, Code Signing, Email Protection

### Modelos de CA
Para criar CAs Intermediárias. Esses definem:
- **Key Usage** — Certificate Sign, CRL Sign
- **Basic Constraints** — CA:TRUE, comprimento de caminho opcional

## Criando um Modelo

1. Clique em **Criar Modelo**
2. Insira um **nome** e descrição opcional
3. Selecione o **tipo** do modelo (Entidade Final ou CA)
4. Configure **padrões de Sujeito** (O, OU, C, ST, L)
5. Selecione flags de **Key Usage**
6. Selecione valores de **Extended Key Usage**
7. Defina o **período de validade** padrão em dias
8. Clique em **Criar**

## Usando Modelos

Ao emitir um certificado ou assinar um CSR, selecione um modelo no dropdown. O modelo pré-preenche:
- Campos de sujeito (você pode sobrescrevê-los)
- Key Usage e Extended Key Usage
- Período de validade

## Duplicando Modelos

Clique em **Duplicar** para criar uma cópia de um modelo existente. Modifique a cópia sem afetar o original.

## Importação e Exportação

### Exportar
Exporte modelos como JSON para compartilhar entre instâncias UCM.

### Importar
Importe de:
- **Arquivo JSON** — Envie um arquivo JSON de modelo
- **Colar JSON** — Cole JSON diretamente na área de texto

## Exemplos Comuns de Modelos

### Servidor TLS
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Validade: 365 dias

### Autenticação de Cliente
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Validade: 365 dias

### Assinatura de Código
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Validade: 365 dias
`
  }
}
