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
          { label: 'SP 证书', text: '元数据中包含的 UCM HTTPS 证书,, 必须被 IDP 信任，否则元数据将被拒绝' },
          { label: 'Entity ID', text: 'UCM 服务提供商实体标识符' },
          { label: 'ACS URL', text: '断言消费者服务回调 URL' },
          { label: '属性映射', text: '左列：IdP 发送的属性名称。右列：对应填充的 UCM 字段（username、email、fullname 或 groups）。示例：user.userprincipalname → username。' },
          { label: '用于角色映射的组', text: '从映射到 groups 的属性中读取；否则从 groups 以及 Microsoft Entra ID / AD FS 的组和角色声明中读取。当 Entra ID 发送 groups.link 而不是组（用户属于超过 150 个组）时，会记录一条警告并应用默认角色：请只发出分配给该应用程序的组，或应用角色。' },
          { label: '由 IdP 发起的登录', text: '接受从 IdP 门户发起的登录，与其他响应一样进行校验。2.243 之前创建的提供商默认开启，新提供商默认关闭：仅当用户从 IdP 门户开始登录时才开启。' },
          { label: 'NameID 格式', text: '未指定（IdP 默认）、持久 (persistent)、电子邮件地址或临时 (transient)：随每个登录请求发送，并发布在 SP 元数据中。持久格式提供稳定的标识符；临时 NameID 绝不用于识别账户。' },
          { label: '单点注销', text: '由 IdP 签名并发送到 SP 元数据中 SLO URL（HTTP-Redirect）的 LogoutRequest，会关闭此浏览器中该 NameID 的 UCM 会话，除非其 SessionIndex 指定了另一个会话。LogoutResponse 会返回到 IdP 的 SLO URL，使用 SP 密钥签名（SP 证书不是 RSA 时不签名，严格的 IdP 会拒绝）；没有 IdP SLO URL 时，浏览器返回登录页面。未签名、伪造、过期或重放的请求，或不带 Destination 的请求，都会被拒绝。' },
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
        title: '角色配置 (#81)',
        items: [
          { label: '身份匹配', text: '登录会打开与 IdP 标识符绑定的账户（OIDC sub、SAML 持久 NameID、LDAP entryUUID 或 objectGUID）。用户名或邮箱只会匹配同一提供商中尚未绑定的账户；本地账户，或已绑定到其他身份的账户，会在登录时被拒绝。要合并本地账户，请先在用户中使用“关联到 SSO”：其下一次通过该提供商登录时会绑定该标识符。' },
          { label: '默认角色', text: '在提供商没有角色映射规则时，授予首次 SSO 登录时创建的账户；也作为新账户的基础角色（其匹配规则只给出自定义角色时；无时为 viewer）。无：没有规则就没有人能登录。之后在 UCM 中所做的角色更改会被保留。' },
          { label: '角色映射', text: '将外部组（Azure AD、Okta、LDAP）映射到 UCM 角色（admin / operator / auditor / viewer）或自定义角色。只要至少有一条规则，没有规则匹配的用户在每次 SSO 登录（OIDC、SAML、LDAP）时都会被拒绝，无论是新账户还是现有账户；通行密钥或证书登录不检查。在用户创建时使用；启用角色同步后，每次登录时也会使用。多个组匹配时，权限最高的角色胜出（admin > operator > auditor > viewer），条目顺序无关紧要 (#221)。每个组还可以指定一个自定义角色（从现有自定义角色中选择）：它会添加到基础角色之上，或单独使用。如果多个匹配的组都指定了自定义角色，则以列表中第一个为准。启用角色同步后，若没有任何组指定自定义角色，则由 SSO 设置的自定义角色会被移除；在 UCM 中手动分配的自定义角色不会被改动。系统角色不能用作自定义角色。' },
          { label: '每次登录时同步角色', text: '关闭（默认）：SSO 绝不覆盖由 UCM 管理的角色。开启：每次登录时从 role_mapping 重新同步角色；匹配规则没有给出基础角色时保留其已存储的角色（default_role 绝不会被重新应用）。' },
          { label: '强制 2FA', text: '此提供商的用户必须注册第二因素。LDAP 登录与本地登录一样，会要求已注册的 TOTP 代码或安全密钥，无论是否启用此选项；OIDC 和 SAML 登录仅要求完成注册，MFA 依赖身份提供商。' },
          { label: '自动更新用户', text: '每次登录时更新邮箱和全名。不会改动角色。' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: '服务器', text: 'LDAP 服务器主机名和端口（389 或 636 用于 SSL）' },
          { label: 'StartTLS', text: '在普通 LDAP 端口上，先将连接升级为 TLS 再进行任何绑定，证书验证与 LDAPS 相同。对未启用 SSL/TLS 的新提供商默认开启。没有 SSL/TLS 或 StartTLS 时，绑定和用户密码会以明文在网络上传输。' },
          { label: '绑定 DN', text: '用于 LDAP 绑定认证的可分辨名称' },
          { label: '基础 DN', text: '用户查找的搜索基础' },
          { label: '用户筛选器', text: '匹配用户的 LDAP 筛选器（例如 (uid={username})）' },
          { label: '属性映射', text: '将 LDAP 属性映射到 UCM 字段：用户名、邮箱、全名。' },
          { label: '唯一 ID 属性', text: '用于识别账户的不可变 ID（entryUUID、objectGUID）。按 DN 绑定的账户会在下一次登录时迁移到此 ID；从一个 ID 属性改为另一个会拒绝所有已绑定的用户，直到执行解除 SSO 关联再关联到 SSO。' },
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
      '错误配置的 SSO 可能会锁定所有用户:, 请始终保留本地管理员',
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
- **Entity ID**: UCM 的服务提供商标识符
- **ACS URL**: 断言消费者服务端点（HTTP-POST）
- **SLO URL**: 单点登出服务端点
- **签名证书**: UCM 的 HTTPS 证书用于签名验证
- **NameID 格式**: 提供商的 **NameID 格式**设置（未指定、持久、电子邮件地址或临时），同时随每个登录请求发送。持久格式提供稳定的标识符；临时 NameID 绝不用于识别账户

将此 URL 复制到 IDP 的"添加服务提供商"或"SAML 应用"配置中。

> ⚠️ **重要：** UCM 的 HTTPS 证书必须被 **IDP 信任**。如果 IDP 无法验证证书（例如自签名或由私有 CA 签发），它将拒绝元数据。请将 UCM 的 CA 证书导入 IDP 的信任存储，或使用由公共信任 CA 签发的证书。

### 配置
1. 从身份提供商获取 IDP 元数据 URL 或 XML 文件
2. 在 UCM 中进入**设置 → SSO**
3. 点击**添加提供商** → SAML
4. 输入 **IDP 元数据 URL**: UCM 自动填充 Entity ID、SSO/SLO URL 和证书
5. 或直接粘贴 IDP 元数据 XML
6. 配置**属性映射**（用户名、邮箱、组）
7. 点击**保存**并**启用**

### 属性映射
将 IDP SAML 属性映射到 UCM 用户字段：
- \`username\` → UCM 用户名（必需）
- \`email\` → UCM 邮箱（必需）
- \`groups\` → 由角色映射规则读取（可选）；不会使用户成为 UCM 组的成员

### 单点注销
IdP 结束会话时，会通过浏览器向 SLO URL 发送已签名的 **LogoutRequest**。UCM 检查 IdP 签名、签发者、Destination（必需）、IssueInstant（在时钟窗口内）以及该请求未被使用过，关闭此浏览器中该 NameID 的 UCM 会话（请求携带 SessionIndex 时，仅关闭其指定的会话），然后向 IdP 的 SLO URL 发送使用 SP 密钥签名的 **LogoutResponse**；SP 证书不是 RSA 时不签名，AD FS 等严格的 IdP 会拒绝。没有 IdP SLO URL 时，浏览器返回 UCM 登录页面。未签名或伪造的 LogoutRequest 会被拒绝，会话保持打开。

### 由 IdP 发起的登录
从 IdP 门户发起的登录到达 UCM 时，并没有 UCM 发出的请求。**允许由 IdP 发起的登录** 会接受它，并同样校验签名、受众、Destination、有效期和防重放。2.243 之前创建的提供商保持开启；新提供商默认关闭。仅当用户从 IdP 门户开始登录时才开启。

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

## 谁可以登录

### 身份匹配
登录会打开与 IdP 标识符绑定的账户：OIDC \`sub\`、SAML 持久 NameID、LDAP \`entryUUID\` 或 \`objectGUID\`。用户名或邮箱只会匹配同一提供商中尚未绑定的账户（在稳定标识符出现之前创建，或由管理员关联）；OIDC IdP 标记为未验证（\`email_verified\` 为 false）的邮箱不匹配任何账户。本地账户，或已绑定到其他身份的账户，绝不会被 SSO 登录打开：登录会被拒绝并记入审计日志。要将本地账户合并到 SSO 身份，请先对该用户使用**关联到 SSO**；其下一次通过该提供商登录时会绑定 IdP 标识符。

删除提供商时，其用户会被保留：为同一 IdP（相同的签发者、Entity ID，或 LDAP 服务器和基础 DN）重新创建的提供商会在他们下次登录时接回他们。否则，以及对恢复后没有提供商的用户，请对每个账户先**解除 SSO 关联**再**关联到 SSO**。

### 角色映射规则
- **至少一条规则**: 没有规则匹配的用户在每次 SSO 登录（OIDC、SAML、LDAP）时都会被拒绝，无论账户是新建的还是已存在的；通行密钥或证书登录不检查
- **没有规则**: 提供商认证的每个用户都可以登录；新账户获得**默认角色**
- 只给出自定义角色的规则: 新账户以**默认角色**作为基础角色（无时为 viewer）
- **默认角色：无**且没有规则: 没有人能通过该提供商登录

提供商没有规则时，**用户配置**部分会自动展开并显示警告。

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
