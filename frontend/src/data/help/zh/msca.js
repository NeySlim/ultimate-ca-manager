export default {
  helpContent: {
    title: 'Microsoft AD CS 集成',
    subtitle: '使用 Microsoft 证书颁发机构签署证书',
    overview: '将 UCM 连接到 Microsoft Active Directory 证书服务（AD CS），使用 Windows PKI 基础设施签署 CSR。支持证书（mTLS）、Kerberos 和 Basic 认证方式。',
    sections: [
      {
        title: '认证方式',
        items: [
          { label: '客户端证书 (mTLS)', text: '最安全。在 MS CA 上生成客户端证书，导出为 PFX，上传证书和密钥 PEM。' },
          { label: 'Basic Auth', text: '基于 HTTPS 的用户名/密码认证。无需加入域。需在 IIS certsrv 中启用 Basic Auth。' },
          { label: 'Kerberos', text: '需要 requests-kerberos 包以及加入域的机器或已配置的 keytab。' },
        ]
      },
      {
        title: '签署 CSR',
        items: [
          { label: '模板选择', text: '从 MS CA 上可用的证书模板中选择' },
          { label: '自动审批', text: '启用自动注册的模板将立即返回证书' },
          { label: '管理者审批', text: '某些模板需要管理者审批——UCM 跟踪待处理请求' },
          { label: '状态轮询', text: '从 CSR 详情面板检查待处理请求状态' },
        ]
      },
      {
        title: '代理注册（EOBO）',
        items: [
          { label: '概述', text: '使用注册代理证书代表其他用户提交 CSR' },
          { label: '注册人 DN', text: '目标用户的可分辨名称（从 CSR 主题自动填充）' },
          { label: '注册人 UPN', text: '目标用户的用户主体名称（从 CSR SAN 邮箱自动填充）' },
          { label: '要求', text: 'CA 模板必须允许代表其他人注册。UCM 服务账户需要注册代理证书。' },
        ]
      },
    ],
    tips: [
      '先测试连接以验证认证并发现可用模板。',
      '在签署弹窗中勾选复选框启用 EOBO——字段从 CSR 数据自动填充。',
      '生产环境推荐使用客户端证书认证——无需加入域。',
    ],
    warnings: [
      'Kerberos 要求机器已加入域或已配置 keytab——在 Docker 中不可用。',
      'EOBO 需要在 AD CS 服务器上配置注册代理证书。',
    ],
  },
  helpGuides: {
    title: 'Microsoft AD CS 集成',
    content: `
## 概述

UCM 与 Microsoft Active Directory 证书服务（AD CS）集成，使用现有的 Windows PKI 基础设施签署 CSR。这将您的内部 CA 与 UCM 的证书生命周期管理连接起来。

## 设置连接

1. 进入**设置 → Microsoft CA**
2. 点击**添加连接**
3. 输入**连接名称**和 **CA 服务器主机名**
4. 可选输入 **CA 通用名称**（留空则自动检测）
5. 选择**认证方式**
6. 输入所选方式的凭据
7. 点击**测试连接**进行验证
8. 设置**默认模板**并点击**保存**

## 认证方式

| 方式 | 要求 | 适用场景 |
|--------|-------------|----------|
| **客户端证书 (mTLS)** | 来自 CA 的客户端证书/密钥 PEM | 生产——无需加入域 |
| **Basic Auth** | 用户名 + 密码，HTTPS | 简单设置——在 IIS certsrv 中启用 Basic Auth |
| **Kerberos** | 加入域的机器 + keytab | 企业 AD 环境 |

### 客户端证书设置（推荐）

1. 在 Windows CA 上为 UCM 服务账户创建证书
2. 导出为 PFX，然后转换为 PEM：
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. 将证书和密钥 PEM 内容粘贴到 UCM 连接表单中

## 通过 Microsoft CA 签署 CSR

1. 导航到 **CSR → 待处理**
2. 选择 CSR 并点击**签署**
3. 切换到 **Microsoft CA** 选项卡
4. 选择连接和证书模板
5. 点击**签署**

### 自动审批模板
证书立即返回并导入到 UCM。

### 管理者审批模板
UCM 将请求保存为**待处理**状态并跟踪 MS CA 请求 ID。在 Windows CA 上批准后，从 CSR 详情面板检查状态以导入证书。

## 代理注册（EOBO）

EOBO 允许注册代理代表其他用户请求证书。这在企业环境中很常见，PKI 管理员为最终用户管理证书。

### 前提条件

- UCM 服务账户需要由 CA 签发的**注册代理证书**
- 证书模板必须启用**"代表其他用户注册"**权限
- 模板的安全选项卡必须授予注册代理注册权限

### 在 UCM 中使用 EOBO

1. 在签署弹窗中选择 Microsoft CA 连接和模板
2. 勾选**代理注册（EOBO）**复选框
3. 字段从 CSR 自动填充：
   - **注册人 DN** — 来自 CSR 主题（例如 CN=John Doe,OU=Users,DC=corp,DC=local）
   - **注册人 UPN** — 来自 CSR SAN 邮箱（例如 john.doe@corp.local）
4. 按需调整值
5. 点击**签署**

UCM 将这些作为 ADCS 请求属性传递：
- EnrolleeObjectName:<DN> — 在 AD 中标识目标用户
- EnrolleePrincipalName:<UPN> — 用户的登录名

### EOBO 与直接注册对比

| 特性 | 直接注册 | EOBO |
|---------|-------------------|------|
| 签署者 | 用户本人 | 注册代理代为签署 |
| 私钥 | 用户机器 | 可在 UCM 中（CSR 模式） |
| 模板权限 | 标准注册 | 需要注册代理权限 |
| 使用场景 | 自助服务 | 集中式 PKI 管理 |

## 故障排除

| 问题 | 解决方案 |
|-------|----------|
| 连接测试失败 | 验证主机名、端口 443、以及 certsrv 是否可访问 |
| 未找到模板 | 检查 UCM 账户是否在 CA 上拥有注册权限 |
| EOBO 被拒绝 | 验证注册代理证书和模板权限 |
| 请求卡在待处理状态 | 在 Windows CA 控制台上审批，然后在 UCM 中刷新状态 |

> 💡 使用**测试连接**按钮在签署前验证认证并发现可用模板。
`
  }
}
