export default {
  helpContent: {
    title: 'Certificados',
    subtitle: 'Emitir, gerenciar e monitorar certificados',
    overview: 'Gerenciamento central de todos os certificados X.509. Emita novos certificados das suas CAs, importe certificados existentes, acompanhe datas de expiração e gerencie renovações e revogações.',
    sections: [
      {
        title: 'Status do Certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro do período de validade e não revogado' },
          { term: 'Expirando', description: 'Expirará dentro de 30 dias' },
          { term: 'Expirado', description: 'Passou da data "Não Depois"' },
          { term: 'Revogado', description: 'Explicitamente revogado (publicado na CRL)' },
          { term: 'Órfão', description: 'A CA emissora não existe mais no sistema' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Emitir', text: 'Criar um novo certificado assinado por uma das suas CAs' },
          { label: 'Importar', text: 'Importar um certificado existente (PEM, DER ou PKCS#12)' },
          { label: 'Renovar', text: 'Reemitir com o mesmo sujeito e um novo período de validade' },
          { label: 'Revogar', text: 'Marcar como revogado com um motivo — aparecerá na CRL' },
          { label: 'Remover Suspensão', text: 'Remover suspensão de um certificado revogado com motivo "Suspensão de Certificado" — restaura para status válido' },
          { label: 'Revogar e Substituir', text: 'Revogar e emitir imediatamente um substituto' },
          { label: 'Exportar', text: 'Baixar em formato PEM, DER ou PKCS#12' },
          { label: 'Comparar', text: 'Comparação lado a lado de dois certificados' },
        ]
      },
    ],
    tips: [
      'Marque com estrela ⭐ certificados importantes para adicioná-los à sua lista de favoritos',
      'Use filtros para encontrar rapidamente certificados por status, CA ou texto de pesquisa',
      'A renovação preserva o mesmo sujeito mas gera um novo par de chaves',
    ],
    warnings: [
      'A revogação é geralmente permanente — exceto "Suspensão de Certificado" que pode ser removida',
      'Excluir um certificado o remove do UCM mas não o revoga',
    ],
  },
  helpGuides: {
    title: 'Certificados',
    content: `
## Visão Geral

Gerenciamento central de todos os certificados X.509. Emita novos certificados, importe existentes, acompanhe datas de expiração, gerencie renovações e revogações.

## Status do Certificado

- **Válido** — Dentro do período de validade e não revogado
- **Expirando** — Expirará dentro de 30 dias (configurável)
- **Expirado** — Passou da data "Não Depois"
- **Revogado** — Explicitamente revogado, publicado na CRL
- **Órfão** — A CA emissora não existe mais no UCM

## Emitindo um Certificado

1. Clique em **Emitir Certificado**
2. Selecione a **CA Assinante** (deve ter chave privada)
3. Preencha o Sujeito (CN é obrigatório, outros campos opcionais)
4. Adicione Nomes Alternativos do Sujeito (SANs): nomes DNS, IPs, e-mails
5. Escolha o tipo e tamanho da chave
6. Defina o período de validade
7. Opcionalmente aplique um **Modelo** para pré-preencher configurações
8. Clique em **Emitir**

### Usando Modelos
Modelos pré-preenchem Key Usage, Extended Key Usage, padrões de sujeito e validade. Selecione um modelo antes de preencher o formulário para economizar tempo.

## Importando Certificados

Formatos suportados:
- **PEM** — Certificados únicos ou em pacote
- **DER** — Formato binário
- **PKCS#12 (P12/PFX)** — Certificado + chave + cadeia (senha obrigatória)
- **PKCS#7 (P7B)** — Cadeia de certificados sem chaves

## Renovando um Certificado

A renovação cria um novo certificado com:
- Mesmo Sujeito e SANs
- Novo par de chaves (gerado automaticamente)
- Novo período de validade
- Novo número de série

O certificado original permanece válido até expirar ou ser revogado.

## Revogando um Certificado

1. Selecione o certificado → **Revogar**
2. Escolha um motivo de revogação (Comprometimento de Chave, Comprometimento da CA, Mudança de Afiliação, Substituído, Cessação de Operação, Suspensão de Certificado, etc.)
3. Confirme a revogação

Certificados revogados são publicados na CRL na próxima regeneração.

> ⚠ A revogação é geralmente permanente — exceto **Suspensão de Certificado** que pode ser removida.

### Remover Suspensão

Se um certificado foi revogado com o motivo **Suspensão de Certificado**, ele pode ser restaurado para o status válido:

1. Abra os detalhes do certificado revogado
2. O botão **Remover Suspensão** aparece na barra de ações (apenas para revogações por Suspensão de Certificado)
3. Clique em **Remover Suspensão** para restaurar o certificado
4. O certificado retorna ao status válido, a CRL é regenerada e o cache OCSP é atualizado

> 💡 A Suspensão de Certificado é útil para suspensões temporárias (ex.: dispositivo perdido, investigação pendente).

### Revogar e Substituir
Combina revogação com reemissão imediata. O novo certificado herda o mesmo Sujeito e SANs.

## Exportando Certificados

Formatos de exportação:
- **PEM** — Apenas o certificado
- **PEM + Cadeia** — Certificado com cadeia completa do emissor
- **DER** — Formato binário
- **PKCS#12** — Certificado + chave + cadeia, protegido por senha

## Favoritos

Marque com estrela ⭐ certificados importantes para salvá-los nos favoritos. Favoritos aparecem primeiro em visualizações filtradas e são acessíveis pelo filtro de favoritos.

## Comparando Certificados

Selecione dois certificados e clique em **Comparar** para ver uma comparação lado a lado de Sujeito, SANs, Key Usage, validade e extensões.

## Filtragem e Pesquisa

- **Filtro de status** — Válido, Expirando, Expirado, Revogado, Órfão
- **Filtro de CA** — Mostrar certificados de uma CA específica
- **Pesquisa de texto** — Pesquisar por CN, número de série ou SAN
- **Ordenação** — Por nome, data de expiração, data de criação, status
`
  }
}
