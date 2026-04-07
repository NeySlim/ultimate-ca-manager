export default {
  helpContent: {
    title: '硬件安全模块',
    subtitle: '外部密钥存储',
    overview: '与硬件安全模块集成实现安全的私钥存储。支持 PKCS#11、AWS CloudHSM、Azure Key Vault 和 Google Cloud KMS。',
    sections: [
      {
        title: '支持的提供商',
        definitions: [
          { term: 'PKCS#11', description: '行业标准 HSM 接口（Thales、Entrust、SoftHSM）' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Services 基于云的 HSM' },
          { term: 'Azure Key Vault', description: 'Microsoft Azure 托管密钥存储' },
          { term: 'Google KMS', description: 'Google Cloud 密钥管理服务' },
        ]
      },
      {
        title: '操作',
        items: [
          { label: '添加提供商', text: '配置 HSM 连接（库路径、凭据、插槽）' },
          { label: '测试连接', text: '验证 HSM 可达且凭据有效' },
          { label: '生成密钥', text: '直接在 HSM 上创建新的密钥对' },
          { label: '状态', text: '监控提供商连接健康状况' },
        ]
      },
    ],
    tips: [
      '在部署物理 HSM 前，使用 SoftHSM 进行测试',
      '在 HSM 上生成的密钥永远不会离开硬件——无法导出',
      '在使用 HSM 提供商进行 CA 签名前先测试连接',
    ],
    warnings: [
      'HSM 提供商配置错误可能会阻止证书签名',
      '失去对 HSM 的访问权限意味着失去存储在其上的密钥',
    ],
  },
  helpGuides: {
    title: '硬件安全模块',
    content: `
## 概述

硬件安全模块（HSM）为加密密钥提供防篡改存储。存储在 HSM 上的私钥永远不会离开硬件，提供最高级别的密钥保护。

## 支持的提供商

### PKCS#11
行业标准 HSM 接口。支持的设备：
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM**（基于软件，用于测试）
- 任何兼容 PKCS#11 的设备

> 💡 **Docker**：SoftHSM 已预装在 Docker 镜像中。首次启动时，会自动初始化默认令牌并注册为 \`SoftHSM-Default\` 提供商——开箱即用。

配置：
- **库路径** — PKCS#11 共享库路径（.so/.dll）
- **插槽** — HSM 插槽号
- **PIN** — 用户 PIN 用于认证

### AWS CloudHSM
Amazon Web Services 基于云的 HSM：
- **集群 ID** — CloudHSM 集群标识符
- **区域** — AWS 区域
- **凭据** — AWS 访问密钥和密钥

### Azure Key Vault
Microsoft Azure 托管密钥存储：
- **保管库 URL** — Azure Key Vault 端点
- **租户 ID** — Azure AD 租户
- **客户端 ID/密钥** — 服务主体凭据

### Google Cloud KMS
Google Cloud 密钥管理服务：
- **项目** — GCP 项目 ID
- **位置** — KMS 密钥环位置
- **密钥环** — 密钥环名称
- **凭据** — 服务账户 JSON 密钥

## 管理提供商

### 添加提供商
1. 点击**添加提供商**
2. 选择**提供商类型**
3. 输入连接详情
4. 点击**测试连接**进行验证
5. 点击**保存**

### 测试连接
创建或修改提供商后始终测试连接。UCM 验证能否与 HSM 通信和认证。

### 提供商状态
每个提供商显示连接状态指示器：
- **已连接** — HSM 可达且已认证
- **已断开** — 无法连接 HSM
- **错误** — 认证或配置问题

## 密钥管理

### 生成密钥
1. 选择一个已连接的提供商
2. 点击**生成密钥**
3. 选择算法（RSA 2048/4096、ECDSA P-256/P-384）
4. 输入密钥标签/别名
5. 点击**生成**

密钥直接在 HSM 上创建。UCM 仅存储引用。

### 使用 HSM 密钥
创建 CA 时，选择 HSM 提供商和密钥而非生成软件密钥。CA 的签名操作将在 HSM 上执行。

> ⚠ 在 HSM 上生成的密钥无法导出。如果您失去对 HSM 的访问权限，将丢失密钥。

> 💡 在部署物理 HSM 前，使用 SoftHSM 进行开发和测试。
`
  }
}
