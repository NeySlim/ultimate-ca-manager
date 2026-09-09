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
          { label: 'Revogar', text: 'Revogar uma CA intermediária a partir da sua CA pai: publicada na CRL e no OCSP da CA pai, e a CA não pode mais assinar (permanente)' },
          { label: 'Reparo de Cadeia', text: 'Corrigir relações pai-filho quebradas automaticamente' },
        ]
      },
      {
        title: 'CAs assinadas externamente (modo CSR, v2.214)',
        content: 'O tipo de criação "Assinada por CA externa (CSR)" cobre o padrão de raiz offline: o par de chaves vive no UCM, o certificado é assinado em outro lugar. A chave privada nunca sai do UCM.',
        items: [
          { label: 'Criar', text: 'O UCM gera o par de chaves (local ou HSM) e um CSR do tipo CA — o CSR é baixado automaticamente' },
          { label: 'Aguardando certificado', text: 'A CA pendente não pode assinar, ser exportada, ser pai nem ficar offline até que seu certificado seja instalado' },
          { label: 'Enviar certificado', text: 'Cole ou envie o certificado assinado externamente (PEM/DER). Sua chave pública deve corresponder à chave privada armazenada; as restrições de CA são aplicadas' },
          { label: 'Cadeia', text: 'Vinculada automaticamente quando o emissor é conhecido pelo UCM — importe a raiz externa (apenas o certificado) para uma cadeia completa' },
          { label: 'Renovar via CSR', text: 'Reemite um CSR a partir da mesma chave (SKI estável); faça-o ser assinado externamente e envie o novo certificado' },
          { label: 'Após a renovação', text: 'O certificado substituído permanece válido até seu notAfter — o UCM mostra seu número de série após o envio; revogue-o na raiz externa se ele não deve mais ser confiável' },
        ]
      },
      {
        title: 'CAs apoiadas por HSM',
        items: [
          { label: 'Armazenamento de chave', text: 'Na criação da CA, escolha Local (criptografado no BD) ou HSM' },
          { label: 'Gerar nova chave', text: 'Cria uma nova chave de assinatura no provedor HSM selecionado' },
          { label: 'Usar chave existente', text: 'Vincula a CA a uma chave de assinatura não utilizada já presente no HSM' },
          { label: 'Sem exportação de chave privada', text: 'As chaves apoiadas por HSM nunca saem do HSM — exportações PKCS#12, JKS e apenas chave estão desativadas' },
          { label: 'Pré-requisito', text: 'Configure e conecte um provedor HSM em Gerenciamento HSM primeiro' },
        ]
      },
      {
        title: 'Modo offline',
        items: [
          { label: 'Propósito', text: 'Proteger a chave privada de uma CA (tipicamente uma raiz) do uso em tempo de execução mantendo disponíveis o certificado, a cadeia, a CRL e o OCSP' },
          { label: 'Protegida por senha', text: 'A chave é envolvida com uma senha fornecida pelo usuário (PKCS#8) e permanece no banco de dados. Restauração digitando a senha.' },
          { label: 'Exportada para arquivo', text: 'A chave é exportada como PEM criptografado baixado uma vez e removida do banco de dados. Restauração reenviando o arquivo com a senha.' },
          { label: 'Política de senha', text: 'A senha segue as regras de complexidade do UCM (comprimento e classes de caracteres). Se perdida, a chave é irrecuperável.' },
          { label: 'Efeito na assinatura', text: 'A assinatura de CSR, emissão de certificados e renovação da CA são bloqueadas offline. CRL e OCSP continuam funcionando a partir das assinaturas em cache.' },
          { label: 'Sub-CAs', text: 'Tanto CAs raízes quanto intermediárias podem ser colocadas offline independentemente' },
        ]
      },
      {
        title: 'CRLs externas para CAs sem chave (v2.215)',
        content: 'Uma CA cuja chave o UCM não pode usar (CA offline, importação apenas de certificado) não pode assinar sua própria CRL — envie em vez disso uma CRL gerada junto à chave offline.',
        items: [
          { label: 'Onde', text: 'Painel de detalhes da CA › Lista de revogação (CRL): mostra o número da CRL servida, a contagem de entradas, thisUpdate/nextUpdate e um aviso quando o nextUpdate tiver passado' },
          { label: 'Envio', text: 'PEM ou DER, apenas CRLs completas (não delta). A assinatura deve ser verificável com o certificado da CA e o emissor deve corresponder ao seu sujeito' },
          { label: 'Monotonicidade', text: 'Um envio mais antigo que a CRL atualmente servida (número de CRL ou thisUpdate) é recusado — emita-a com um número de CRL maior' },
          { label: 'Publicação', text: 'A CRL enviada é servida no caminho CDP existente da CA, e o OCSP responde revogado para os seriais que ela lista' },
          { label: 'Fluxo de trabalho', text: 'Revogue na raiz offline, gere a CRL da raiz no ambiente air-gap e envie-a aqui — a chave da raiz nunca fica online' },
        ]
      },
    ],
    tips: [
      'CAs com ícone de chave (🔑) possuem chave privada e podem assinar certificados',
      'Coloque a CA raiz offline assim que suas intermediárias estiverem operacionais',
      'Use «Exportada para arquivo» para o maior isolamento air-gap; «Protegida por senha» para restauração rápida no local',
      'A exportação PKCS#12 inclui a cadeia completa e é ideal para backup',
    ],
    warnings: [
      'Excluir uma CA NÃO revogará os certificados que ela emitiu — revogue-os primeiro',
      'As chaves privadas são armazenadas criptografadas; perder o banco de dados significa perder as chaves',
      'Senhas do modo offline NÃO são recuperáveis — armazene-as em seu gerenciador de senhas / vault antes de confirmar',
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

### Criar uma CA assinada externamente (modo CSR, v2.214)
Para o padrão de raiz offline — a chave da CA emissora vive no UCM, seu certificado é assinado em outro lugar:
1. Clique em **Criar** → tipo **Assinada por CA externa (CSR)**
2. Preencha o Sujeito e as configurações de chave (local ou HSM) — a validade é decidida pelo assinante externo
3. Envie: o UCM gera o par de chaves e um CSR do tipo CA (baixado automaticamente)
4. Faça o CSR ser assinado pela sua CA raiz externa/offline
5. De volta à CA (selo **Aguardando certificado**), clique em **Enviar certificado** e forneça o certificado assinado (PEM ou DER)

O UCM só ativa a CA se a chave pública do certificado corresponder à chave privada armazenada e se as restrições de CA forem respeitadas. A cadeia é vinculada automaticamente quando o emissor é conhecido pelo UCM — importe a raiz externa (apenas o certificado) para uma cadeia completa. Até a ativação, a CA pendente não pode assinar, ser exportada, ser CA pai nem ficar offline.

Para renovar, use **Renovar via CSR**: um novo CSR é emitido **a partir da mesma chave** (o SKI permanece estável), assinado externamente e enviado pelo mesmo fluxo.

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

## Revogando uma CA Intermediária

Uma CA intermediária cuja chave foi comprometida ou que foi desativada é revogada a partir da sua CA pai, como um certificado:

1. Selecione a CA intermediária e clique em **Revogar CA**
2. Escolha o motivo RFC 5280 (chave comprometida, CA comprometida, cessação de atividade, ...)
3. Confirme: a revogação é permanente

O que acontece em seguida:
- O número de série da CA é publicado na **CRL da CA pai** (regenerada imediatamente) e o **respondedor OCSP** da CA pai responde \`revoked\` com o motivo
- A CA revogada **não pode mais assinar** nada: certificados, CSRs, renovações, sub-CAs, e as CAs abaixo dela também não
- Os certificados que ela emitiu deixam de ser confiáveis para os clientes que validam a cadeia; sua própria CRL e seu OCSP continuam sendo servidos até que a CA seja excluída
- Excluir a CA revogada mantém sua entrada na CRL da CA pai até a expiração original do certificado

> ⚠ Uma CA raiz não pode ser revogada a partir do UCM (autoassinada: as partes confiantes a removem de seus armazenamentos de confiança), e uma intermediária assinada por uma raiz externa é revogada nessa raiz. Sua CRL pode então ser servida a partir do UCM (veja Modo offline).

## Excluindo uma CA

> ⚠ Excluir uma CA a remove do UCM mas NÃO revoga os certificados que ela emitiu. Revogue os certificados primeiro se necessário.

A exclusão é bloqueada se a CA tiver CAs filhas. Exclua ou reatribua as CAs filhas primeiro.

## CAs apoiadas por HSM

O UCM pode armazenar a chave de assinatura de uma CA em um módulo de segurança de hardware (HSM) externo em vez do banco de dados criptografado local. Esta é a opção recomendada para CAs raiz e intermediárias em produção.

### Quando usar
- Requisitos de conformidade (FIPS 140-2/3, eIDAS, Common Criteria)
- Defesa em profundidade: as chaves não podem ser exfiltradas mesmo se o host UCM for comprometido
- Custódia centralizada de chaves entre várias ferramentas PKI

### Pré-requisitos
1. Abra **Gerenciamento HSM** e configure um provedor (PKCS#11 / OpenBao / etc.)
2. Verifique se o provedor está **Ativo** e **Conectado**

### Passo a passo
1. Abra **Criar CA**
2. Preencha Subject e validade como de costume
3. Em **Armazenamento de chave**, mude de *Local* para **HSM**
4. Escolha o provedor HSM
5. Escolha um modo de chave:
   - **Gerar nova chave** — forneça um rótulo (letras/dígitos/_/-) e escolha o algoritmo (RSA-2048/3072/4096 ou EC-P256/P384/P521)
   - **Usar chave existente** — escolha uma chave de assinatura não utilizada já presente no HSM
6. Envie. O UCM cria o certificado CA e o vincula à chave HSM.

### Limitações
- As chaves privadas apoiadas por HSM **não podem ser exportadas**. As opções PKCS#12, JKS e somente-chave ficam ocultas para CAs HSM. Apenas o certificado (PEM/DER/P7B) pode ser exportado.
- **Não há migração no lugar** entre Local e HSM. Para "mover" uma CA local existente para um HSM, crie uma nova CA no HSM e reemita os certificados.
- As chaves existentes oferecidas em *Usar chave existente* são filtradas para chaves assimétricas com capacidade de assinatura ainda não vinculadas a outra CA.

## Modo offline

Tire a chave de assinatura de uma CA do uso em tempo de execução sem excluir a CA. O certificado, a cadeia, a CRL e o OCSP continuam funcionando — apenas as operações de assinatura (assinar CSR, emitir certificado, renovar CA) são bloqueadas.

Esta é a maneira padrão de proteger uma CA raiz entre cerimônias raras, mantendo online sua âncora de confiança e infraestrutura de revogação.

### Dois modos

**Protegida por senha** — a chave privada permanece no banco de dados UCM, envolvida (PKCS#8) sob uma senha que você escolhe. Para colocar a CA novamente online, clique em **Restaurar** e digite a senha novamente. Rápido e conveniente; a segurança depende da força da senha e de o UCM não estar comprometido.

**Exportada para arquivo** — a chave privada é exportada como um arquivo PEM criptografado por senha baixado uma vez. A chave é então **removida do banco de dados**. Para colocar a CA novamente online, clique em **Restaurar**, faça upload do arquivo e digite a senha. Esta é a opção mais forte (verdadeiro air-gap) mas você é totalmente responsável pelo arquivo: se perdê-lo, a chave é irrecuperável.

### Regras de senha
A senha segue a política de complexidade padrão do UCM: comprimento mínimo, mistura de classes de caracteres, sem sequências triviais. As mesmas regras das senhas de usuário.

### Passo a passo — Colocar offline
1. Abra o painel de detalhes da CA
2. Clique em **Colocar offline**
3. Leia a explicação, clique em **Continuar**
4. Escolha um modo (*Protegida por senha* ou *Exportada para arquivo*)
5. Digite a senha duas vezes
6. Confirme. Para *Exportada para arquivo*, a chave criptografada é baixada imediatamente — armazene-a com segurança.

### Passo a passo — Restaurar
1. Abra o painel de detalhes da CA offline
2. Clique em **Restaurar**
3. Digite a senha
4. Para *Exportada para arquivo*: também selecione o arquivo de chave baixado anteriormente
5. Confirme. As operações de assinatura são retomadas imediatamente.

### Efeito nas operações
| Operação | Online | Offline |
|---|---|---|
| Emitir certificado | Permitido | **Bloqueado** |
| Assinar CSR | Permitido | **Bloqueado** |
| Renovar CA | Permitido | **Bloqueado** |
| Renovar certificado emitido | Permitido | **Bloqueado** |
| Servir CRL / OCSP | Permitido | Permitido (assinatura em cache) |
| Exportar certificado / cadeia | Permitido | Permitido |
| Excluir CA | Permitido | Permitido |

> ⚠ Senhas do modo offline **não são recuperáveis**. Armazene-as em seu gerenciador de senhas / vault antes de confirmar. Senha perdida = CA inutilizável = reemissão completa da hierarquia subordinada.
`
  }
}