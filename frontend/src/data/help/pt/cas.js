export default {
  helpContent: {
    title: 'Autoridades Certificadoras',
    subtitle: 'Gerencie sua hierarquia PKI',
    overview: 'Crie e gerencie Autoridades Certificadoras Raiz e Intermediárias. Construa uma cadeia de confiança completa para sua organização. CAs com chaves privadas podem assinar certificados diretamente.',
    sections: [
      {
        title: 'Visualizações',
        items: [
          { label: 'Visualização em Árvore', text: 'Exibição hierárquica mostrando relações pai-filho entre CAs' },
          { label: 'Visualização em Lista', text: 'Tabela plana com ordenação e filtragem' },
          { label: 'Visualização por Organização', text: 'Agrupado por organização para configurações multi-tenant' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Criar CA Raiz', text: 'Autoridade de nível superior autoassinada' },
          { label: 'Criar Intermediária', text: 'CA assinada por uma CA pai na cadeia' },
          { label: 'Importar CA', text: 'Importar certificado de CA existente (com ou sem chave privada)' },
          { label: 'Exportar', text: 'PEM, DER ou PKCS#12 (P12/PFX) com proteção por senha' },
          { label: 'Renovar CA', text: 'Reemitir o certificado da CA com um novo período de validade' },
          { label: 'Reparo de Cadeia', text: 'Corrigir relações pai-filho quebradas automaticamente' },
        ]
      },
    ],
    tips: [
      'CAs com ícone de chave (🔑) possuem chave privada e podem assinar certificados',
      'Use CAs intermediárias para assinatura diária, mantenha a CA raiz offline quando possível',
      'A exportação PKCS#12 inclui a cadeia completa e é ideal para backup',
    ],
    warnings: [
      'Excluir uma CA NÃO revogará os certificados que ela emitiu — revogue-os primeiro',
      'As chaves privadas são armazenadas criptografadas; perder o banco de dados significa perder as chaves',
    ],
  },
  helpGuides: {
    title: 'Autoridades Certificadoras',
    content: `
## Visão Geral

As Autoridades Certificadoras (CAs) formam a base da sua PKI. O UCM suporta hierarquias de CA em múltiplos níveis com CAs Raiz, CAs Intermediárias e Sub-CAs.

## Tipos de CA

### CA Raiz
Um certificado autoassinado que serve como âncora de confiança. CAs Raiz devem idealmente ser mantidas offline em ambientes de produção. No UCM, uma CA Raiz não possui CA pai.

### CA Intermediária
Assinada por uma CA Raiz ou outra CA Intermediária. Usada para assinatura diária de certificados. CAs Intermediárias limitam o raio de impacto em caso de comprometimento.

### Sub-CA
Qualquer CA assinada por uma CA Intermediária, criando níveis mais profundos de hierarquia.

## Visualizações

### Visualização em Árvore
Exibe a hierarquia completa de CAs como uma árvore expansível. As relações pai-filho são visualizadas com indentação e linhas de conexão.

### Visualização em Lista
Tabela plana com colunas ordenáveis: Nome, Tipo, Status, Certificados emitidos, Data de expiração.

### Visualização por Organização
Agrupa CAs pelo campo Organização (O). Útil para configurações multi-tenant onde diferentes departamentos gerenciam árvores de CA separadas.

## Criando uma CA

### Criar CA Raiz
1. Clique em **Criar** → **CA Raiz**
2. Preencha os campos do Sujeito (CN, O, OU, C, ST, L)
3. Selecione o algoritmo de chave (RSA 2048/4096, ECDSA P-256/P-384)
4. Defina o período de validade (tipicamente 10-20 anos para CAs Raiz)
5. Opcionalmente selecione um modelo de certificado
6. Clique em **Criar**

### Criar CA Intermediária
1. Clique em **Criar** → **CA Intermediária**
2. Selecione a **CA Pai** (deve ter chave privada)
3. Preencha os campos do Sujeito
4. Defina o período de validade (tipicamente 5-10 anos)
5. Clique em **Criar**

> ⚠ A validade da CA Intermediária não pode exceder a validade da sua CA pai.

## Importando uma CA

Importe certificados de CA existentes via:
- **Arquivo PEM** — Certificado em formato PEM
- **Arquivo DER** — Formato binário DER
- **PKCS#12** — Pacote de certificado + chave privada (requer senha)

Ao importar sem chave privada, a CA pode verificar certificados mas não pode assinar novos.

## Exportando uma CA

Formatos de exportação:
- **PEM** — Certificado codificado em Base64
- **DER** — Formato binário
- **PKCS#12 (P12/PFX)** — Certificado + chave privada + cadeia, protegido por senha

> 💡 A exportação PKCS#12 inclui a cadeia completa de certificados e é ideal para backup.

## Chaves Privadas

CAs com **ícone de chave** (🔑) possuem chave privada armazenada no UCM e podem assinar certificados. CAs sem chave são apenas para confiança — validam cadeias mas não podem emitir.

### Armazenamento de Chaves
As chaves privadas são criptografadas em repouso no banco de dados do UCM. Para maior segurança, considere usar um provedor HSM (veja a página HSM).

## Reparo de Cadeia

Se as relações pai-filho estiverem quebradas (ex.: após importação), use **Reparo de Cadeia** para reconstruir automaticamente a hierarquia com base na correspondência Emissor/Sujeito.

## Renovando uma CA

A renovação reemite o certificado da CA com:
- Mesmo sujeito e chave
- Novo período de validade
- Novo número de série

Os certificados existentes assinados pela CA permanecem válidos.

## Excluindo uma CA

> ⚠ Excluir uma CA a remove do UCM mas NÃO revoga os certificados que ela emitiu. Revogue os certificados primeiro se necessário.

A exclusão é bloqueada se a CA tiver CAs filhas. Exclua ou reatribua as CAs filhas primeiro.
`
  }
}
