export default {
  helpContent: {
    title: '单点登录',
    subtitle: 'SAML、OAuth2 和 LDAP 集成',
    overview: '配置单点登录以允许用户通过其组织身份提供商进行认证。支持 SAML 2.0、OAuth2/OIDC 和 LDAP 协议。',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: '身份提供商', text: '配置 IDP 元数据 URL 或上传 XML' },
          { label: 'SP 元数据 URL', text: '向您的 IDP 提供此 URL 以自动配置 UCM 作为服务提供商' },
          { label: 'SP 证书', text: '元数据中包含的 UCM HTTPS 证书——必须被 IDP 信任，否则元数据将被拒绝' },
          { label: 'Entity ID', text: 'UCM 服务提供商实体标识符' },
          { label: 'ACS URL', text: '断言消费者服务回调 URL' },
          { label: '属性映射', text: '将 IDP 属性映射到 UCM 用户字段' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: '授权 URL', text: 'OAuth2 授权端点' },
          { label: '令牌 URL', text: 'OAuth2 令牌端点' },
          { label: '客户端 ID/密钥', text: '来自 IDP 的 OAuth2 客户端凭据' },
          { label: '范围', text: '请求的 OAuth2 范围（openid、profile、email）' },
          { label: '自动创建用户', text: '首次 SSO 登录时自动创建 UCM 账户' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: '服务器', text: 'LDAP 服务器主机名和端口（389 或 636 用于 SSL）' },
          { label: '绑定 DN', text: '用于 LDAP 绑定认证的可分辨名称' },
          { label: '基础 DN', text: '用户查找的搜索基础' },
          { label: '用户筛选器', text: '匹配用户的 LDAP 筛选器（例如 (uid={username})）' },
          { label: '属性映射', text: '将 LDAP 属性映射到用户名、邮箱、全名' },
        ]
      },
    ],
    tips: [
      '先用非管理员账户测试 SSO 以避免锁定',
      '保留本地管理员登录作为后备',
      '映射 IDP 邮箱属性以确保唯一的用户识别',
      '使用 SP 元数据 URL 自动配置您的 IDP（SAML）',
      'UCM HTTPS 证书必须被 IDP 信任，SAML 元数据才能被接受',
    ],
    warnings: [
      '错误配置的 SSO 可能会锁定所有用户——请始终保留本地管理员',
    ],
  },
  helpGuides: {
    title: '单点登录',
    content: `
## 概述

SSO 允许用户使用其组织的身份提供商（IDP）进行认证，无需单独的 UCM 凭据。UCM 支持 **SAML 2.0**、**OAuth2/OIDC** 和 **LDAP**。

## SAML 2.0

### SP 元数据 URL

UCM 提供**服务提供商（SP）元数据 URL**，您可以将其提供给 IDP 以进行自动配置：

\`\`\`
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

此 URL 返回符合 SAML 2.0 的 XML 文档，包含：
- **Entity ID** — UCM 的服务提供商标识符
- **ACS URL** — 断言消费者服务端点（HTTP-POST）
- **SLO URL** — 单点登出服务端点
- **签名证书** — UCM 的 HTTPS 证书用于签名验证
- **NameID 格式** — 请求的名称标识符格式

将此 URL 复制到 IDP 的"添加服务提供商"或"SAML 应用"配置中。

> ⚠️ **重要：** UCM 的 HTTPS 证书必须被 **IDP 信任**。如果 IDP 无法验证证书（例如自签名或由私有 CA 签发），它将拒绝元数据。请将 UCM 的 CA 证书导入 IDP 的信任存储，或使用由公共信任 CA 签发的证书。

### 配置
1. 从身份提供商获取 IDP 元数据 URL 或 XML 文件
2. 在 UCM 中进入**设置 → SSO**
3. 点击**添加提供商** → SAML
4. 输入 **IDP 元数据 URL** — UCM 自动填充 Entity ID、SSO/SLO URL 和证书
5. 或直接粘贴 IDP 元数据 XML
6. 配置**属性映射**（用户名、邮箱、组）
7. 点击**保存**并**启用**

### 属性映射
将 IDP SAML 属性映射到 UCM 用户字段：
- \`username\` → UCM 用户名（必需）
- \`email\` → UCM 邮箱（必需）
- \`groups\` → UCM 组成员关系（可选）

## OAuth2 / OIDC

### 配置
1. 在 OAuth2/OIDC 提供商中注册 UCM 作为客户端
2. 将**重定向 URI** 设置为：\`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. 复制**客户端 ID** 和**客户端密钥**
4. 在 UCM 中进入**设置 → SSO**
5. 点击**添加提供商** → OAuth2
6. 输入**授权 URL** 和**令牌 URL**
7. 输入**用户信息 URL**（用于登录后获取用户属性）
8. 输入客户端 ID 和密钥
9. 配置范围（openid、profile、email）
10. 点击**保存**并**启用**

### 自动创建用户
启用后，首次 SSO 登录时会自动创建新的 UCM 用户账户，使用 IDP 提供的属性。分配默认角色。

## LDAP

### 配置
1. 在 UCM 中进入**设置 → SSO**
2. 点击**添加提供商** → LDAP
3. 输入 **LDAP 服务器**主机名和**端口**（LDAP 用 389，LDAPS 用 636）
4. 为加密连接启用**使用 SSL**
5. 输入**绑定 DN** 和**绑定密码**（服务账户凭据）
6. 输入**基础 DN**（用户查找的搜索基础）
7. 配置**用户筛选器**（例如 \`(uid={username})\` 或 AD 用 \`(sAMAccountName={username})\`）
8. 映射 LDAP 属性：**用户名**、**邮箱**、**全名**
9. 点击**测试连接**验证，然后**保存**并**启用**

### Active Directory
对于 Microsoft Active Directory，使用：
- 端口：**389**（或使用 SSL 的 636）
- 用户筛选器：\`(sAMAccountName={username})\`
- 用户名属性：\`sAMAccountName\`
- 邮箱属性：\`mail\`
- 全名属性：\`displayName\`

## 登录流程
1. 用户在 UCM 登录页面点击**使用 SSO 登录**（或输入 LDAP 凭据）
2. 对于 SAML/OAuth2：用户被重定向到 IDP 进行认证，然后重定向回来
3. 对于 LDAP：凭据直接在 LDAP 服务器上验证
4. UCM 创建或更新用户账户
5. 用户登录成功

> ⚠ 始终保留至少一个本地管理员账户作为后备，以防 SSO 配置错误导致所有人被锁定。

> 💡 在将 SSO 设为主要认证方式前，先用非管理员账户测试。

> 💡 使用**测试连接**按钮在启用提供商前验证配置。
`
  }
}
