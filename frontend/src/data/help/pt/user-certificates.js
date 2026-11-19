export default {
  helpContent: {
    title: 'Certificados de Usuário',
    subtitle: 'Gerenciar certificados de cliente mTLS',
    overview: 'Gerenciamento dedicado dos certificados de cliente mTLS inscritos via página Conta. Visualize, exporte, revogue e exclua certificados emitidos para usuários para autenticação TLS mútua.',
    sections: [
      {
        title: 'Status do Certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro do período de validade e não revogado' },
          { term: 'Expirando', description: 'Expirará dentro de 30 dias' },
          { term: 'Expirado', description: 'Passou da data "Não Depois"' },
          { term: 'Revogado', description: 'Explicitamente revogado por um operador ou administrador' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Exportar', text: 'Baixar como PEM (com chave e cadeia) ou PKCS#12 (protegido por senha)' },
          { label: 'Revogar', text: 'Revogar com um motivo, o certificado aparecerá na CRL' },
          { label: 'Excluir', text: 'Remover o certificado e sua associação de usuário do UCM' },
        ]
      },
      {
        title: 'Permissões',
        items: [
          { label: 'Viewers', text: 'Podem ver apenas seus próprios certificados' },
          { label: 'Operators', text: 'Podem visualizar, exportar, revogar e excluir todos os certificados de usuário; exportar a chave privada do certificado de outro usuário exige read:private_keys, que a função não possui' },
          { label: 'Admins', text: 'Acesso completo, chaves privadas incluídas' },
          { label: 'Auditors', text: 'Podem visualizar e exportar certificados, sem a chave privada' },
        ]
      },
    ],
    tips: [
      'Inscreva novos certificados mTLS em Conta → aba mTLS',
      'Os certificados são armazenados e gerenciados pelo UCM como qualquer outro certificado',
      'Use a barra de estatísticas para filtrar rapidamente por status',
      'Clique em uma linha para ver os detalhes completos do certificado em uma janela flutuante',
    ],
    warnings: [
      'Revogar um certificado de usuário impede imediatamente o login mTLS com esse certificado',
      'A exclusão remove o certificado permanentemente: ele não pode ser recuperado',
    ],
  },
  helpGuides: {
    title: 'Certificados de Usuário',
    content: `
## Visão Geral

A página Certificados de Usuário gerencia os certificados de cliente mTLS inscritos via aba **Conta → mTLS**. Diferentemente dos certificados comuns, eles são especificamente vinculados a contas de usuário para autenticação TLS mútua.

Os certificados aqui são totalmente gerenciados pelo UCM: são armazenados no banco de dados com as chaves privadas e podem ser exportados, revogados ou excluídos a qualquer momento.

## Inscrevendo um Certificado

1. Vá para a aba **Conta → mTLS**
2. Clique em **Inscrever Certificado**
3. O sistema gera um par de chaves e emite um certificado de cliente assinado pela sua CA mTLS
4. O certificado aparece nesta página e pode ser usado para login mTLS

## Status do Certificado

- **Válido**: Dentro do período de validade e não revogado
- **Expirando**: Expirará dentro de 30 dias
- **Expirado**: Passou da data "Não Depois"
- **Revogado**: Explicitamente revogado, publicado na CRL

## Exportando um Certificado

1. Selecione um certificado → **Exportar**
2. Escolha o formato:
   - **PEM**: Certificado + chave privada + cadeia da CA em formato texto
   - **PKCS#12**: Pacote binário, protegido por senha (mínimo de 8 caracteres)
3. Clique em **Baixar**

O arquivo exportado pode ser importado em navegadores, sistemas operacionais ou clientes de API para autenticação mTLS.

> ⚠ A senha do PKCS#12 deve ter pelo menos 8 caracteres.

## Revogando um Certificado

1. Selecione um certificado → **Revogar**
2. Escolha um motivo de revogação:
   - Comprometimento de Chave
   - Mudança de Afiliação
   - Substituído
   - Cessação de Operação
   - Não especificado
3. Confirme a revogação

> ⚠ Revogar um certificado impede imediatamente o login mTLS com esse certificado. A revogação é permanente.

## Excluindo um Certificado

A exclusão remove tanto o certificado quanto a associação usuário-certificado. Apenas admins e operators podem excluir.

> ⚠ A exclusão é permanente e não pode ser desfeita.

## Permissões

| Função | Visualizar | Exportar | Revogar | Excluir |
|------|------|--------|--------|--------|
| Admin | Todos | Todos | Todos | Todos |
| Operator | Todos | Todos (a chave privada de outro usuário exige read:private_keys) | Todos | Todos |
| Auditor | Todos | Só o certificado, sem chave privada | ✗ | ✗ |
| Viewer | Apenas os próprios | Apenas os próprios | ✗ | ✗ |

### Permissões Necessárias

- **read:user_certificates**: Visualizar a lista e os detalhes dos certificados
- **write:user_certificates**: Revogar certificados
- **delete:user_certificates**: Excluir certificados

> 💡 Inscreva novos certificados mTLS na página Conta. Esta página serve para gerenciar certificados existentes.
`
  }
}
