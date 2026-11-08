export default {
  helpContent: {
    title: 'Microsoft AD CS 集成',
    subtitle: '使用 Microsoft 证书颁发机构签署证书',
    overview: '将 UCM 连接到 Microsoft Active Directory 证书服务（AD CS），使用 Windows PKI 基础设施签署 CSR 并管理证书的完整生命周期。支持证书（mTLS）、Kerberos 和 Basic 认证方式，以及一个可选的 WinRM 管理通道，用于吊销、CRL、清单和待处理请求管理。',
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
          { label: '管理者审批', text: '某些模板需要管理者审批,, UCM 跟踪待处理请求' },
          { label: '待处理请求', text: 'CA 为其管理员保留的请求在 UCM 中保持“待处理”，页面不提供状态检查：在 CA 上签发后，请导入证书，或让通过 WinRM 管理通道进行的清单同步导入 UCM 尚不知道的证书' },
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
      {
        title: '生命周期：续期与吊销',
        items: [
          { label: '续期', text: '续期 AD CS 签发的证书会将其原始 CSR 重新提交到同一连接和同一模板,, 由签发 CA 签署，而非 UCM。' },
          { label: '吊销', text: '吊销 AD CS 签发的证书仅在 UCM 本地生效，除非已配置 WinRM 管理通道,, 此时吊销会传播到 Windows CA。' },
          { label: '待处理续期', text: '如果 CA 将续期保留待管理者审批，UCM 会像其他待处理请求一样跟踪它。' },
        ]
      },
      {
        title: 'WinRM 管理通道（可选）',
        items: [
          { label: '用途', text: '通过 PowerShell 远程 + certutil 在 Windows CA 上执行管理操作（吊销、撤销吊销、发布 CRL、清单、审批/拒绝）,, 这些是 AD CS Web 注册无法完成的。' },
          { label: '传输', text: '基于 HTTP/HTTPS 的 NTLM 或 Kerberos。推荐 Kerberos + HTTPS；Kerberos 复用连接的 keytab。' },
          { label: '凭据', text: '默认复用连接自身的凭据。mTLS 注册的连接必须设置专用的 WinRM 账户（最小权限的"颁发和管理证书"专员）。' },
          { label: '要求', text: 'CA 上已启用 WinRM 并已安装可选的 pywinrm 包。管理操作需要 admin:system 权限；将吊销或解除挂起传播到 CA 则遵循证书的 write:certificates。' },
        ]
      },
      {
        title: 'CRL 吊销同步',
        items: [
          { label: '单向同步', text: '定期获取 CA 的 CRL，并将 CA 上已吊销的证书在 UCM 中标记为已吊销。绝不撤销吊销。' },
          { label: 'CRL 来源', text: '显式的 CRL URL，或从已签发证书的 CRL 分发点自动检测。' },
          { label: '已验证', text: '应用任何内容之前，CRL 签名都会根据 CA 证书进行校验。' },
        ]
      },
      {
        title: 'CA 清单与控制面板',
        items: [
          { label: '清单同步', text: '导入直接在 CA 上签发但 UCM 尚不知晓的证书（按请求 ID 增量处理）；对账可通过 API 使用。' },
          { label: '待处理请求', text: '列出、审批（重新提交 + 自动导入）或拒绝等待 CA 管理者审批的请求。' },
          { label: 'CA 健康状况', text: '一目了然地查看 CA 服务状态、CA 证书到期时间、CRL 下次更新时间和待处理请求数量。' },
        ]
      },
    ],
    tips: [
      '先测试连接以验证认证并发现可用模板。',
      '在签署弹窗中勾选复选框启用 EOBO:, 字段从 CSR 数据自动填充。',
      '生产环境推荐使用客户端证书认证:, 无需加入域。',
      '启用 WinRM 管理通道，可将吊销传播到 CA 并在 UCM 中管理待处理请求。',
    ],
    warnings: [
      'Kerberos 要求机器已加入域或已配置 keytab:, 在 Docker 中不可用。',
      'EOBO 需要在 AD CS 服务器上配置注册代理证书。',
      '没有 WinRM 管理通道时，吊销 AD CS 证书仅在 UCM 中标记为已吊销:, Windows CA 不会收到通知。',
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
4. 可选输入 **CA 通用名称**（留空则使用服务器主机名）
5. 选择**认证方式**
6. 输入所选方式的凭据
7. 点击**测试连接**进行验证
8. 设置**默认模板**并点击**保存**

## 认证方式

| 方式 | 要求 | 适用场景 |
|--------|-------------|----------|
| **客户端证书 (mTLS)** | 来自 CA 的客户端证书/密钥 PEM | 生产:, 无需加入域 |
| **Basic Auth** | 用户名 + 密码，HTTPS | 简单设置:, 在 IIS certsrv 中启用 Basic Auth |
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
UCM 将请求保存为**待处理**状态并跟踪 MS CA 请求 ID。页面不提供状态检查：在 Windows CA 上签发后，请导入证书，或让通过 WinRM 管理通道进行的**清单同步**导入 UCM 尚不知道的证书。

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
   - **注册人 DN**: 来自 CSR 主题（例如 CN=John Doe,OU=Users,DC=corp,DC=local）
   - **注册人 UPN**: 来自 CSR SAN 邮箱（例如 john.doe@corp.local）
4. 按需调整值
5. 点击**签署**

UCM 将这些作为 ADCS 请求属性传递：
- EnrolleeObjectName:<DN>: 在 AD 中标识目标用户
- EnrolleePrincipalName:<UPN>: 用户的登录名

### EOBO 与直接注册对比

| 特性 | 直接注册 | EOBO |
|---------|-------------------|------|
| 签署者 | 用户本人 | 注册代理代为签署 |
| 私钥 | 用户机器 | 可在 UCM 中（CSR 模式） |
| 模板权限 | 标准注册 | 需要注册代理权限 |
| 使用场景 | 自助服务 | 集中式 PKI 管理 |

## 证书生命周期

### 续期 AD CS 证书
续期**不会**在本地重新签署（签发密钥位于 Windows CA 上）。UCM 会将证书的原始 CSR:, 相同的密钥、主题和 SAN,, 重新提交到签发它的连接和模板，并就地更新证书。如果 CA 将续期保留待管理者审批，它将作为待处理请求被跟踪。

### 吊销 AD CS 证书
AD CS Web 注册没有吊销端点。吊销 AD CS 签发的证书：
- **没有 WinRM 管理通道**: 仅在 UCM 中标记为已吊销；Windows CA 不会收到通知。请同时在 CA 上吊销它。
- **有 WinRM 管理通道**: UCM 将吊销传播到 Windows CA（certutil -revoke + 发布 CRL）。解除 certificateHold 也会传播撤销吊销。

## WinRM 管理通道（可选）

管理通道让 UCM 能够在 Windows CA 上执行 Web 注册无法完成的管理操作：吊销/撤销吊销、发布 CRL、清单、以及审批/拒绝待处理请求。它使用 PowerShell 远程 + certutil。

### 要求
- CA 上**已启用 WinRM**（Enable-PSRemoting；推荐在 5986 上使用 HTTPS 侦听器）
- UCM 中已安装可选的 **pywinrm** 包（pip install pywinrm）
- 一个被允许在 CA 上**管理证书**的账户（"Issue and Manage Certificates"）

### 配置
1. 编辑连接并启用 **WinRM 管理通道**
2. 设置主机（默认为连接的服务器）、端口和传输方式
3. **传输**：Kerberos（推荐，复用连接的 keytab）或 NTLM，基于 HTTP 或 HTTPS
4. **凭据**：留空以复用连接自身的凭据（Basic/Kerberos）。mTLS 连接没有可复用的 WinRM 凭据:, 请设置专用账户
5. 点击**测试管理通道**

| 注册认证模式 | 是否为 WinRM 复用凭据？ |
|--------------|--------------------------|
| Kerberos（keytab） | 是:, 相同的主体/keytab |
| Basic（用户名/密码） | 是:, 密码用于 NTLM/Kerberos |
| 证书（mTLS） | 否:, 请设置专用的 WinRM 账户 |

## CRL 吊销同步

在连接上启用**从 CA 的 CRL 同步吊销**，UCM 会定期获取 CA 的 CRL，并将 CA 上已吊销的证书在 UCM 中标记为已吊销。这是严格单向的（CA 到 UCM），绝不会撤销在 UCM 中已吊销证书的吊销状态。CRL URL 取自连接，或从已签发证书的 CRL 分发点自动检测，其签名在应用任何内容之前会根据 CA 证书进行验证。每小时运行一次，另有**立即同步 CRL** 操作。

## CA 清单同步

启用**导入直接在 CA 上签发的证书**，将 UCM 之外签发的证书（原生工具、自动注册、或 UCM 部署之前签发的）纳入 UCM 存储，使 UCM 跟踪整个生命周期。它使用 certutil -view 读取 CA 数据库，导入 UCM 尚未拥有的证书（按序列号去重），并按请求 ID 增量处理（支持完整重新扫描选项）。**对账**视图列出存在于 CA 上但不在 UCM 中的证书，反之亦然。每 6 小时运行一次，另有**立即从 CA 导入**操作。需要 WinRM 管理通道。

## CA 控制面板

控制面板（从连接打开，需要管理通道）管理等待 CA 管理者审批的请求并显示 CA 健康状况：
- **待处理请求**: 列出、**审批**（certutil -resubmit；签发的证书会自动导入）或**拒绝**（certutil -deny）
- **健康状况**: CA 服务状态、CA 证书到期时间、CRL 下次更新时间和待处理请求数量

## 故障排除

| 问题 | 解决方案 |
|-------|----------|
| 连接测试失败 | 验证主机名、端口 443、以及 certsrv 是否可访问 |
| 未找到模板 | 检查 UCM 账户是否在 CA 上拥有注册权限 |
| EOBO 被拒绝 | 验证注册代理证书和模板权限 |
| 请求卡在待处理状态 | 从 CA 控制面板审批，或在 Windows CA 控制台上审批后在 UCM 中刷新状态 |
| 管理通道测试失败 | 验证 CA 上已启用 WinRM、端口/传输方式正确、且已安装 pywinrm |
| 吊销未同步到 CA | 启用 WinRM 管理通道:, 没有它，吊销仅在 UCM 本地生效 |
| 未检测到待处理状态（非英语 CA） | 已在 v2.192 中修复:, UCM 现在能识别本地化的 AD CS 待处理页面 |

> 💡 使用**测试连接**按钮在签署前验证认证并发现可用模板。启用 **WinRM 管理通道**可直接从 UCM 管理吊销、CRL、清单和待处理请求。
`
  }
}
