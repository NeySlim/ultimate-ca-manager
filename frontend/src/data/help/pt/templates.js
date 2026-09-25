export default {
  helpContent: {
    title: 'Modelos de Certificado',
    subtitle: 'Perfis de certificado reutilizáveis',
    overview: 'Defina perfis de certificado reutilizáveis com campos de sujeito, key usage, extended key usage, períodos de validade e outras extensões pré-configurados. Aplique modelos ao emitir ou assinar certificados.',
    sections: [
      {
        title: 'Origem',
        definitions: [
          { term: 'Sistema', description: 'Incluído na instalação. Duplique-o para obter uma cópia editável: ele próprio não pode ser editado nem excluído' },
          { term: 'Personalizado', description: 'Criado ou importado aqui, e o único tipo que pode ser editado ou excluído' },
        ]
      },
      {
        title: 'Recursos',
        items: [
          { label: 'Tipo', text: 'Web Server, Email, VPN Server ou Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon ou Custom. Define os padrões de Key Usage, EKU e SAN' },
          { label: 'Padrões de Sujeito', text: 'Pré-preencher Organização, OU, País, Estado, Cidade e Email. Em certificados E-mail e Servidor + Cliente (Combinado), o Email também se torna um SAN' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, etc.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Validade', text: 'Período de validade padrão em dias' },
          { label: 'Duplicar', text: 'Clonar um modelo existente e modificá-lo' },
          { label: 'Mostrar sistema', text: 'Oculte os modelos incluídos para trabalhar apenas com os seus. Lembrado por navegador' },
          { label: 'Importar/Exportar', text: 'Compartilhar modelos como arquivos JSON entre instâncias UCM, um modelo ou vários em um só arquivo' },
        ]
      },
      {
        title: 'Autoinscrição do Windows',
        items: [
          { label: 'Permitir autoinscrição', text: 'Anuncia o modelo como autoEnroll=true na Diretiva de Inscrição de Certificados para que clientes GPO/Kerberos o solicitem automaticamente no logon. Desativado por padrão, a inscrição manual continua possível sem ele' },
          { label: 'Criar sujeito a partir do Active Directory', text: 'Deriva o sujeito e o SAN do objeto AD do solicitante (via Conector AD) em vez de exigir que o cliente forneça um, para autoinscrição GPO não assistida' },
          { label: 'Restringir inscrição a grupo AD', text: 'Apenas membros do grupo AD configurado (incluindo associação aninhada) podem se inscrever pelo endpoint autenticado por Kerberos. Em branco = qualquer principal autenticado. Não aplicado no endpoint Usuário/Senha' },
          { label: 'Campos de sujeito fixados', text: 'Força os valores C/ST/L/O/OU em cada certificado emitido via WSTEP, sobrescrevendo o CSR ou a derivação do AD para esses campos. CN e SAN nunca são afetados, deixe um campo em branco para mantê-lo dinâmico' },
        ]
      },
    ],
    tips: [
      'Crie modelos separados para servidores TLS, clientes e assinatura de código',
      'Use a ação Duplicar para criar variações rapidamente de um modelo, inclusive de um modelo do sistema',
      'Modelos com flags de autoinscrição mostram os selos AD / Auto / ACL / Fixado na lista',
    ],
  },
  helpGuides: {
    title: 'Modelos de Certificado',
    content: `
## Visão Geral

Modelos definem perfis de certificado reutilizáveis. Em vez de configurar manualmente Key Usage, Extended Key Usage, validade e campos de sujeito toda vez, aplique um modelo para pré-preencher tudo.

## Sistema e Personalizado

Todo modelo é de um tipo ou do outro, indicado na coluna **Origem**.

### Sistema
Os modelos incluídos na instalação: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication e Smartcard Logon. Editar e Excluir são recusados para eles, na interface e pela API. **Duplicar** fornece uma cópia editável para servir de base.

### Personalizado
Tudo o que é criado ou importado aqui. Esses podem ser editados e excluídos livremente.

Desative **Mostrar sistema** na barra de ferramentas para ocultar os modelos incluídos e trabalhar apenas com os seus. A escolha é lembrada, a menos que você ainda não tenha modelos personalizados, caso em que os modelos incluídos permanecem visíveis.

Autoridades certificadoras não são criadas a partir de modelos: crie-as na página **CAs**.

## Criando um Modelo

1. Clique em **Criar Modelo**
2. Insira um **nome** e descrição opcional
3. Selecione o **tipo** do modelo: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon ou Custom. Ele define os padrões de Key Usage, Extended Key Usage e SAN, que você pode alterar em seguida
4. Configure **padrões de Sujeito** (O, OU, C, ST, L, CN, Email). Em certificados E-mail e Servidor + Cliente (Combinado), o Email também se torna um SAN de email
5. Selecione flags de **Key Usage**
6. Selecione valores de **Extended Key Usage**
7. Defina o **período de validade** padrão em dias
8. Clique em **Criar**

## Usando Modelos

Ao emitir um certificado ou assinar um CSR, selecione um modelo no dropdown. O modelo pré-preenche:
- Campos de sujeito (você pode sobrescrevê-los)
- Key Usage e Extended Key Usage
- Período de validade

## Flags de Autoinscrição do Windows

Os modelos carregam três flags opcionais usadas pelos protocolos de autoinscrição do Windows (XCEP/WSTEP, configurados em **Configurações → Autoinscrição do Windows**):

- **Permitir autoinscrição**: Anuncia o modelo como \`autoEnroll=true\` na Diretiva de Inscrição de Certificados, para que clientes autenticados por GPO/Kerberos o solicitem automaticamente no logon sem nenhuma ação do usuário. Desativado por padrão: como no ADCS real, um modelo ainda pode ser inscrito manualmente (MMC "Solicitar Novo Certificado", \`certreq\`) sem essa flag, já que Enroll e Autoenroll são permissões separadas.
- **Criar sujeito a partir do Active Directory**: Para autoinscrição GPO não assistida: deriva o sujeito e o SAN do certificado a partir do objeto AD do solicitante (via Conector AD) em vez de exigir que o cliente forneça um.
- **Restringir inscrição a grupo AD**: Apenas principals pertencentes ao grupo do Active Directory configurado (incluindo associação aninhada) podem se inscrever com este modelo pelo endpoint autenticado por Kerberos. Insira um nome de grupo ou DN completo; deixe em branco para permitir qualquer principal autenticado, correspondendo ao padrão do ADCS real. Não aplicado no endpoint Usuário/Senha, que não tem identidade por solicitação para verificar.

Modelos com essas flags mostram os selos **AD**, **Auto** e **ACL** na lista de modelos.

## Campos de Sujeito Fixados

Um modelo pode **fixar** os campos organizacionais do sujeito: **C, ST, L, O, OU**: para certificados emitidos via WSTEP. Um valor fixado é forçado em cada certificado emitido, sobrescrevendo o que o CSR do cliente ou a derivação do Active Directory fornecer para esse campo.

- **Common Name e Subject Alternative Name nunca são afetados**: permanecem dinâmicos por solicitante
- Deixe um campo em branco para mantê-lo dinâmico
- Modelos com campos fixados mostram um selo **Fixado**, e os valores fixados aparecem no painel de detalhes do modelo

Use isso para garantir uma identidade organizacional uniforme (ex. \`O\` e \`C\` fixos) em uma frota autoinscrita, independentemente do que cada cliente Windows enviar.

## Duplicando Modelos

Clique em **Duplicar** para criar uma cópia de um modelo existente. Modifique a cópia sem afetar o original.

## Importação e Exportação

### Exportar
Exporte modelos como JSON para compartilhar entre instâncias UCM.

### Importar
Importe de:
- **Arquivo JSON**: Envie um arquivo JSON de modelo, um modelo ou vários em um só arquivo
- **Colar JSON**: Cole JSON diretamente na área de texto

Um modelo cujo nome já existe é ignorado, e a importação informa quais foram.

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
