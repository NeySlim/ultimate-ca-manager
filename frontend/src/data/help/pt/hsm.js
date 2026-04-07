export default {
  helpContent: {
    title: 'Módulos de Segurança de Hardware',
    subtitle: 'Armazenamento externo de chaves',
    overview: 'Integre com Módulos de Segurança de Hardware para armazenamento seguro de chaves privadas. Suporte para PKCS#11, AWS CloudHSM, Azure Key Vault e Google Cloud KMS.',
    sections: [
      {
        title: 'Provedores Suportados',
        definitions: [
          { term: 'PKCS#11', description: 'Interface HSM padrão da indústria (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM baseado em nuvem da Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Armazenamento gerenciado de chaves do Microsoft Azure' },
          { term: 'Google KMS', description: 'Google Cloud Key Management Service' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Adicionar Provedor', text: 'Configurar conexão a um HSM (caminho da biblioteca, credenciais, slot)' },
          { label: 'Testar Conexão', text: 'Verificar se o HSM está acessível e as credenciais são válidas' },
          { label: 'Gerar Chave', text: 'Criar um novo par de chaves diretamente no HSM' },
          { label: 'Status', text: 'Monitorar a saúde da conexão do provedor' },
        ]
      },
    ],
    tips: [
      'Use SoftHSM para testes antes de implantar com um HSM físico',
      'Chaves geradas em um HSM nunca saem do hardware — elas não podem ser exportadas',
      'Teste a conexão antes de usar um provedor HSM para assinatura de CA',
    ],
    warnings: [
      'Configuração incorreta do provedor HSM pode impedir a assinatura de certificados',
      'Perder acesso ao HSM significa perder acesso às chaves armazenadas nele',
    ],
  },
  helpGuides: {
    title: 'Módulos de Segurança de Hardware',
    content: `
## Visão Geral

Módulos de Segurança de Hardware (HSMs) fornecem armazenamento resistente a adulteração para chaves criptográficas. Chaves privadas armazenadas em um HSM nunca saem do hardware, fornecendo o mais alto nível de proteção de chaves.

## Provedores Suportados

### PKCS#11
A interface HSM padrão da indústria. Dispositivos suportados:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (baseado em software, para testes)
- Qualquer dispositivo compatível com PKCS#11

> 💡 **Docker**: SoftHSM vem pré-instalado na imagem Docker. Na primeira inicialização, um token padrão é auto-inicializado e registrado como provedor \`SoftHSM-Default\` — pronto para usar imediatamente.

Configuração:
- **Caminho da Biblioteca** — Caminho para a biblioteca compartilhada PKCS#11 (.so/.dll)
- **Slot** — Número do slot HSM
- **PIN** — PIN do usuário para autenticação

### AWS CloudHSM
HSM baseado em nuvem da Amazon Web Services:
- **ID do Cluster** — Identificador do cluster CloudHSM
- **Região** — Região AWS
- **Credenciais** — Chave de acesso e segredo AWS

### Azure Key Vault
Armazenamento gerenciado de chaves do Microsoft Azure:
- **URL do Vault** — Endpoint do Azure Key Vault
- **ID do Tenant** — Tenant do Azure AD
- **ID/Segredo do Cliente** — Credenciais do service principal

### Google Cloud KMS
Google Cloud Key Management Service:
- **Projeto** — ID do projeto GCP
- **Localização** — Localização do key ring KMS
- **Key Ring** — Nome do key ring
- **Credenciais** — Chave JSON da conta de serviço

## Gerenciando Provedores

### Adicionando um Provedor
1. Clique em **Adicionar Provedor**
2. Selecione o **tipo de provedor**
3. Insira os detalhes de conexão
4. Clique em **Testar Conexão** para verificar
5. Clique em **Salvar**

### Testando Conexão
Sempre teste a conexão após criar ou modificar um provedor. O UCM verifica se pode se comunicar com o HSM e autenticar.

### Status do Provedor
Cada provedor mostra um indicador de status de conexão:
- **Conectado** — HSM está acessível e autenticado
- **Desconectado** — Não é possível alcançar o HSM
- **Erro** — Problema de autenticação ou configuração

## Gerenciamento de Chaves

### Gerando Chaves
1. Selecione um provedor conectado
2. Clique em **Gerar Chave**
3. Escolha o algoritmo (RSA 2048/4096, ECDSA P-256/P-384)
4. Insira um rótulo/alias para a chave
5. Clique em **Gerar**

A chave é criada diretamente no HSM. O UCM armazena apenas uma referência.

### Usando Chaves HSM
Ao criar uma CA, selecione um provedor HSM e uma chave em vez de gerar uma chave de software. As operações de assinatura da CA são realizadas no HSM.

> ⚠ Chaves geradas em um HSM não podem ser exportadas. Se você perder acesso ao HSM, você perde as chaves.

> 💡 Use SoftHSM para desenvolvimento e testes antes de implantar com HSMs físicos.
`
  }
}
