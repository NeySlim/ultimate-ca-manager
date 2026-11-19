export default {
  helpContent: {
    title: '硬件安全模块',
    subtitle: '外部密钥存储',
    overview: '与硬件安全模块集成实现安全的私钥存储。支持 PKCS#11、AWS CloudHSM、Azure Key Vault、Google Cloud KMS 和 OpenBao/Vault Transit。',
    sections: [
      {
        title: '支持的提供商',
        definitions: [
          { term: 'PKCS#11', description: '行业标准 HSM 接口（Thales、Entrust、SoftHSM）' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Services 基于云的 HSM' },
          { term: 'Azure Key Vault', description: 'Microsoft Azure 托管密钥存储' },
          { term: 'Google KMS', description: 'Google Cloud 密钥管理服务' },
          { term: 'OpenBao / Vault Transit', description: 'OpenBao 或 Vault Transit 密钥引擎，提供密钥管理即服务' },
        ]
      },
      {
        title: '操作',
        items: [
          { label: '添加提供商', text: '配置 HSM 连接（库路径、凭据、插槽）' },
          { label: '测试连接', text: '验证 HSM 可达且凭据有效；对于 PKCS#11 模块，还会记录其上报的信息（库、制造商、库版本和固件版本），显示在提供商页面上' },
          { label: '生成密钥', text: '直接在 HSM 上创建新的密钥对' },
          { label: '状态', text: '监控提供商连接健康状况' },
          { label: '认证', text: '声明 HSM 的认证：Common Criteria EAL 4+、EUCC high、FIPS 140-3 级别 3、FIPS 140-2 级别 3 或其他。留空表示未声明。对于由 HSM 支持的 CA，eu-acm 合规配置仅接受 Common Criteria EAL 4+、EUCC high 以及 FIPS 140-3 级别 3（至 2030 年 12 月 31 日）' },
          { label: '名称已存在 (v2.249)', text: '在 OpenBao 或 Azure Key Vault 已存在的名称下生成密钥会被拒绝 (409)：请通过密钥同步 (POST /api/v2/hsm/providers/<id>/sync) 引入现有密钥' },
          { label: '一次一个生成 (v2.249)', text: '每个提供商上的密钥生成依次进行，等待超过 60 秒的会得到 409。记录无法保存的密钥会从 HSM 中移除' },
          { label: '备份中的 PIN (v2.249)', text: '备份在归档内以明文保存提供商的 PIN 或令牌，并由其密码保护，因此可在另一个安装上恢复。仅另一个安装的密钥才能打开的值会在恢复时丢弃，并在日志中提示重新输入' },
          { label: 'FIPS 模式下的 SoftHSM (v2.247)', text: 'FIPS 模式拒绝新的 SoftHSM 提供商，因为 SoftHSM 不是经过验证的模块；设置 UCM_FIPS_ALLOW_SOFTHSM=1 可在测试时允许创建' },
        ]
      },
      {
        title: 'HSM 支持的 CA(v2.130+)',
        content: '配置好提供商后,您可以在创建时将 CA 的私钥固定到该 HSM:',
        items: [
          { label: 'Key Storage 开关', text: '在 CA 创建表单中,选择 Local(在 DB 中加密)或 HSM。选择提供商 + 密钥标签' },
          { label: '签名路径', text: '该 CA 的每次签发、CRL 签名和 OCSP 签名都通过 HSM, 密钥永不离开' },
          { label: '导出限制', text: 'HSM-CA 禁用 PKCS#12、JKS 和仅密钥导出(只能导出公共证书 / 链)' },
          { label: 'CRL 和 OCSP', text: '两者都与 HSM-CA 透明工作(通过 HSM 签名)' },
          { label: '迁移', text: '现有本地 CA 在创建后无法移至 HSM, 在创建时选择' },
        ]
      },
      {
        title: 'ML-DSA 密钥',
        content: 'ML-DSA-44、ML-DSA-65 和 ML-DSA-87（FIPS 204）密钥仅在能用其签名的提供商上提供。它们直接对数据签名，因此无需选择摘要。',
        items: [
          { label: 'PKCS#11', text: '实现 PKCS#11 3.2 并支持 ML-DSA 机制的令牌' },
          { label: 'OpenBao / Vault Transit', text: 'Transit 密钥类型 mldsa-44、mldsa-65 和 mldsa-87' },
          { label: 'Google Cloud KMS', text: 'PQ_SIGN_ML_DSA 密钥版本，已按 KMS API 映射，但尚未针对该服务测试。KMS 最多签署 64 KiB 数据，因此更大的 CRL 无法签名' },
          { label: '不可用', text: 'Azure Key Vault 和 AWS CloudHSM 提供商不持有 ML-DSA 密钥，FIPS 模式在所有提供商上都拒绝 ML-DSA' },
        ]
      },
    ],
    tips: [
      '在部署物理 HSM 前，使用 SoftHSM 进行测试',
      '在 HSM 上生成的密钥永远不会离开硬件:, 无法导出',
      '在使用 HSM 提供商进行 CA 签名前先测试连接',
      '对于生产中长寿命的根 CA,首选 HSM 支持的密钥存储',
    ],
    warnings: [
      '声明的认证是运营方对 HSM 的陈述：UCM 不会核实硬件。与 eIDAS 对齐的配置会读取它来检查 CA 密钥保护',
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

> 💡 **Docker**：SoftHSM 已预装在 Docker 镜像中。首次启动时，会自动初始化默认令牌并注册为 \`SoftHSM-Default\` 提供商:, 开箱即用。在 FIPS 模式下，SoftHSM 不是经过验证的模块：不会创建默认提供商，并且会拒绝 SoftHSM 提供商，除非设置 \`UCM_FIPS_ALLOW_SOFTHSM=1\` 允许用于测试。

配置：
- **库路径**: PKCS#11 共享库路径（.so/.dll）
- **令牌标签**: 要使用的令牌标签（必填）
- **插槽**: HSM 插槽号（可选）
- **PIN**: 用户 PIN 用于认证

### AWS CloudHSM
Amazon Web Services 基于云的 HSM：
- **集群 ID**: CloudHSM 集群标识符
- **令牌标签**: CloudHSM PKCS#11 令牌的标签
- **加密用户 / 加密密码**: UCM 登录所用的加密用户 (CU)，无需 AWS 访问密钥

### Azure Key Vault
Microsoft Azure 托管密钥存储：
- **保管库 URL**: Azure Key Vault 端点
- **租户 ID**: Azure AD 租户
- **客户端 ID/密钥**: 服务主体凭据

### Google Cloud KMS
Google Cloud 密钥管理服务：
- **项目**: GCP 项目 ID
- **位置**: KMS 密钥环位置
- **密钥环**: 密钥环名称
- **凭据**: 服务账户 JSON 密钥

### OpenBao / Vault Transit
OpenBao 或 HashiCorp Vault Transit Secrets Engine。密钥通过 Transit API 远程管理: 无需 PKCS#11 库。

配置：
- **URL**: 服务器地址（例如 \`https://openbao.example.com:8200\`）
- **令牌**: 认证令牌
- **挂载路径**: Transit 引擎挂载点（默认：\`transit\`）
- **命名空间**: 可选的多租户命名空间
- **跳过 TLS 验证**: 跳过 TLS 证书验证（用于自签名证书）

支持的密钥类型：
- RSA 2048、3072、4096
- ECDSA P-256、P-384、P-521
- ML-DSA-44、ML-DSA-65、ML-DSA-87（Transit \`mldsa-*\` 密钥，需 OpenBao 版本支持）
- AES-256-GCM（对称）

> 💡 OpenBao 是 HashiCorp Vault 的社区分支。UCM 两者都支持。

## 管理提供商

### 添加提供商
1. 点击**新提供商**
2. 选择**提供商类型**
3. 输入连接详情
4. 点击**创建**
5. 在新建的提供商上点击**测试**以验证连接

### 测试连接
创建或修改提供商后始终测试连接。UCM 验证能否与 HSM 通信和认证。对于 PKCS#11 模块，测试还会记录模块上报的信息（库、制造商、库版本和固件版本），显示在提供商页面上。

### 提供商状态
每个提供商显示连接状态指示器：
- **已连接**: HSM 可达且已认证
- **已断开**: 无法连接 HSM
- **错误**: 认证或配置问题

## 密钥管理

### 生成密钥
1. 选择一个已连接的提供商
2. 点击**生成密钥**
3. 选择算法（RSA 2048/4096、ECDSA P-256/P-384）
4. 输入密钥标签/别名
5. 点击**生成**

密钥直接在 HSM 上创建。UCM 仅存储引用。

### ML-DSA 密钥
ML-DSA-44、ML-DSA-65 和 ML-DSA-87（FIPS 204）仅在能用其签名的提供商上提供：
- **PKCS#11**: 实现 PKCS#11 3.2 并支持 ML-DSA 机制的令牌
- **OpenBao / Vault Transit**: 密钥类型 \`mldsa-44\`、\`mldsa-65\` 和 \`mldsa-87\`
- **Google Cloud KMS**: \`PQ_SIGN_ML_DSA_*\` 密钥版本，已按 KMS API 映射，但尚未针对该服务测试。KMS 最多签署 64 KiB 数据，因此更大的 CRL 无法签名

Azure Key Vault 和 AWS CloudHSM 提供商不持有 ML-DSA 密钥，FIPS 模式在所有提供商上都拒绝 ML-DSA。ML-DSA 密钥直接对数据签名，因此无需选择摘要。

### 使用 HSM 密钥
创建 CA 时，选择 HSM 提供商和密钥而非生成软件密钥。CA 的签名操作将在 HSM 上执行。

> ⚠ 在 HSM 上生成的密钥无法导出。如果您失去对 HSM 的访问权限，将丢失密钥。

> 💡 在部署物理 HSM 前，使用 SoftHSM 进行开发和测试。
`
  }
}
