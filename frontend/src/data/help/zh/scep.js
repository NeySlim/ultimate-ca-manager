export default {
  helpContent: {
    title: 'SCEP',
    subtitle: '简单证书注册协议',
    overview: 'SCEP 使网络设备（路由器、交换机、防火墙）和 MDM 解决方案能够自动请求和获取证书。设备使用质询密码进行认证。',
    sections: [
      {
        title: '选项卡',
        items: [
          { label: '请求', text: '待处理、已批准和已拒绝的 SCEP 注册请求' },
          { label: '配置', text: 'SCEP 服务器设置：CA 选择、自动批准' },
          { label: '配置文件', text: '命名注册端点，每个都有自己的 URL、CA、模板和质询' },
          { label: 'Intune 应用注册', text: '由验证 Intune 质询的配置文件共享的 Entra 应用注册（租户 ID、客户端 ID、客户端密钥）；编辑时密钥留空则保留当前密钥，测试连接仅获取令牌并发现服务，不消耗任何质询，仍被配置文件使用的应用无法删除' },
          { label: '质询', text: '查看并重新生成设备注册的质询密码' },
          { label: '信息', text: 'SCEP 端点 URL 和集成说明' },
        ]
      },
      {
        title: '配置',
        items: [
          { label: '签名 CA', text: '选择签署 SCEP 注册证书的 CA。设备会用此 CA 加密其请求，因此它必须在软件中持有 RSA 密钥：EC、HSM 支持、无密钥、离线和已吊销的 CA 不会列出 (v2.248)' },
          { label: '自动批准', text: '自动批准带有有效质询密码的请求，或由同一端点签发的证书所签署的续期请求' },
          { label: '通过纯 HTTP 提供', text: '默认关闭。同时在 HTTP 协议端口（默认 8080）上应答 SCEP，地址为 http://your-server:8080/scep/pkiclient.exe 和各配置文件 URL，供 sscep 等无法使用 HTTPS 的客户端使用。RFC 8894 §7.10：SCEP 消息本身已受保护，CMS 信封使质询密码保持私密' },
          { label: '质询密码', text: '设备用于认证注册的共享密钥。由同一端点（配置文件或全局）签发的证书所签署的续期请求（RenewalReq）由该证书认证，因此不检查其质询，更换密钥也不会阻止已注册的设备续期（RFC 8894 §2.4）。任何其他证书仍需要该端点的质询' },
          { label: '设备密钥 (v2.248)', text: '设备使用 RSA、ECDSA、Ed25519 或 ML-DSA 密钥签署其请求；ML-DSA 签名遵循 RFC 9882（SHA-512 摘要）。Ed448 会被拒绝，FIPS 模式下 ML-DSA 也会被拒绝' },
        ]
      },
      {
        title: '配置文件',
        items: [
          { label: 'URL 片段', text: '每个配置文件通过 /scep/<segment>/pkiclient.exe 提供, 将每个设备群或 MDM 配置指向其专属 URL' },
          { label: '证书模板', text: '绑定模板后，其密钥用法（KU/EKU）和有效期将决定通过该配置文件签发的每个证书' },
          { label: '签名摘要 (v2.251)', text: '通过配置文件签发的证书使用其模板的摘要签名，并提升到与 CA 密钥对应的摘要，这是策略可以覆盖的偏好。没有模板时，使用 CA 密钥的摘要' },
          { label: '按配置文件的质询', text: '每个配置文件都有自己的质询密码，加密存储，过期窗口与全局质询相同' },
          { label: '默认端点', text: '不带片段的 /scep/pkiclient.exe 端点继续使用全局配置' },
          { label: 'Microsoft Intune 验证', text: '配置文件可以针对 Intune 自己的按设备 SCEP 质询进行验证，而不使用静态密码：在配置文件中从 Intune 应用注册选项卡选择一个应用注册（SCEP challenge validation 和 Application.Read.All 权限），自动批准仍为必需；升级时，每个现有配置文件会自动获得一个以其命名的应用，按租户和客户端去重' },
          { label: '手动审批', text: '通过配置文件提交的请求会以该配置文件的模板（有效期、密钥用法）批准，与自动批准签发的结果完全一致' },
          { label: '注册者不得持有的用途', text: '绑定到配置文件的模板不能包含 OCSP 签名、时间戳、任意用途或智能卡登录，SCEP 续期也绝不会沿用这些用途；当配置文件针对 Intune 验证时允许智能卡登录，因为 Intune 为身份作担保' },
        ]
      },
    ],
    tips: [
      '为每个 CA 使用唯一的质询密码以提高安全审计能力',
      '自动批准很方便，但在高安全环境中建议手动审核请求',
      'SCEP URL：https://your-server:8443/scep/pkiclient.exe 用于已配置的 CA，https://your-server:8443/scep/<profile>/pkiclient.exe 用于配置文件',
      'Intune 配置文件需要启用自动批准:, Intune 的注册是同步的验证并签发往返过程，Intune 一侧没有批准队列',
    ],
    warnings: [
      '质询密码位于 CSR 中，CSR 在加密到 CA 的 CMS 信封内传输（RFC 8894 §2.4），因此纯 HTTP 不会暴露它；如果客户端把它作为信封外的签名属性发送，则会在 HTTP 上以及任何记录该请求的环节暴露',
    ],
  },
  helpGuides: {
    title: 'SCEP 服务器',
    content: `
## 概述

简单证书注册协议（SCEP）允许网络设备和移动设备管理（MDM）解决方案自动注册证书。它广泛支持路由器、交换机、防火墙和移动设备平台。

## 选项卡

### 请求
查看和管理 SCEP 注册请求：
- **待处理**: 等待审批的请求
- **已批准**: 已批准并已签发证书的请求
- **已拒绝**: 已拒绝的请求

### 配置
配置 SCEP 服务器设置：
- **启用/禁用**: 开启或关闭 SCEP 服务
- **签名 CA**: 选择签署 SCEP 注册证书的 CA。设备会用此 CA 加密其请求，因此它必须在软件中持有 RSA 密钥：EC、HSM 支持、无密钥、离线和已吊销的 CA 不会列出 (v2.248)
- **自动批准**: 自动批准带有有效质询密码的请求，或由同一端点签发的证书所签署的续期请求
- **通过纯 HTTP 提供**: 默认关闭。同时在 HTTP 协议端口（默认 8080）上应答 SCEP，供 sscep 等无法使用 HTTPS 的客户端使用。RFC 8894 §7.10：SCEP 消息本身已受保护，因此不要求 TLS；CMS 信封使质询密码保持私密

### 配置文件
命名注册端点，每个都通过自己的 URL 提供服务：

\`\`\`
https://your-server:8443/scep/<profile>/pkiclient.exe
\`\`\`

每个配置文件绑定：
- **自己的 CA**: 不同的设备群可针对不同的 CA 注册
- **可选的证书模板**: 绑定后，模板的密钥用法、扩展密钥用法和有效期将决定通过该配置文件签发的每个证书
- **注册者不得持有的用途**: 绑定到配置文件的模板不能包含 OCSP 签名、时间戳、任意用途或智能卡登录，SCEP 续期也绝不会沿用这些用途；当配置文件针对 Intune 验证时允许智能卡登录，因为 Intune 为身份作担保
- **按配置文件的质询密码**: 加密存储，过期窗口与全局质询相同
- **审批策略**: 每个配置文件可自动批准或手动审核

将每个设备群、MDM 配置文件或租户指向其专属配置文件 URL。不带片段的 \`/scep/pkiclient.exe\` 端点继续使用全局配置，保持不变。

### 质询密码
**质询**选项卡显示质询密码。设备必须在其注册请求中包含有效的质询密码才能通过认证。

- **查看密码**: 显示 CA 的当前质询
- **重新生成**: 创建新的质询密码（对新的注册使旧密码失效）

由同一端点（配置文件或全局）签发的证书所签署的续期请求（RenewalReq）由该证书认证：不检查其质询密码，因此重新生成的密钥不会阻止已注册的设备续期（RFC 8894 §2.4）。在其他地方签发的证书（由其他配置文件、ACME、EST 或界面签发）仍需要该端点的质询。EC 设备仍会发送密码，用于对其应答加密。

### 信息
查看 SCEP 端点 URL 和集成说明。

## SCEP 注册流程

1. 管理员在 UCM 中配置 SCEP（CA、质询密码）
2. 设备使用 SCEP URL 和质询密码配置
3. 设备生成密钥对和 CSR
4. 设备将 CSR 和质询密码发送到 UCM
5. UCM 验证质询密码并签署证书（如果启用自动批准）
6. 设备接收并安装证书

### 设备密钥
设备使用自己的密钥（RSA、ECDSA、Ed25519 或 ML-DSA）签署 PKCSReq。ML-DSA 签名按 RFC 9882 校验（SHA-512 摘要、密钥自身的算法标识符、无参数）。Ed448 签名会被拒绝，FIPS 模式下 ML-DSA 签名也会被拒绝。请求仍会加密到 RSA 签名 CA。

## SCEP URL

\`\`\`
https://your-server:8443/scep/pkiclient.exe            (已配置的 CA)
https://your-server:8443/scep/<profile>/pkiclient.exe  (按配置文件端点)
https://your-server:8443/cgi-bin/pkiclient.exe         (已配置的 CA，旧路径)
http://your-server:8080/scep/pkiclient.exe             (启用通过纯 HTTP 提供时)
\`\`\`

设备需要完整 URL 才能注册；单独的 \`/scep\` 是 Web 界面，而不是 SCEP 端点。使用配置文件 URL 可指向该配置文件的 CA、模板和质询密码。

### CA 轮换（GetNextCACert）
GetNextCACert 提供该端点 CA 的后继者，由当前 CA 签署：与其具有相同父 CA 和相同主题 DN、未被吊销、未脱机、持有软件 RSA 密钥且到期更晚的另一个 CA。仅显示名称相同的 CA 绝不会被提供；没有后继者时应答 404。

## 批准/拒绝请求

如果未启用自动批准：
1. 前往**请求**选项卡
2. 查看待处理的请求
3. 检查请求详情（主题、事务 ID、状态、CSR）
4. 点击**批准**或**拒绝**

通过配置文件提交的请求会以该配置文件的模板（有效期、密钥用法）签发，与自动批准的结果完全一致。

## 设备集成

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM-CA
  enrollment url https://your-server:8443/scep
  subject-name CN=router.example.com,O=MyOrg
  revocation-check crl
  password challenge-password-here
crypto pki enroll UCM-CA
\`\`\`

### JAMF
在 SCEP 配置文件中配置：
- 服务器 URL：\`https://your-server:8443/scep\`
- 质询：来自 UCM 的密码

### Microsoft Intune
Intune 不支持静态质询密码:, 它会为每台设备签发自己的加密质询，只有 Intune 的 API 才能验证。在 SCEP **配置文件**（而非全局端点）上启用 **Microsoft Intune SCEP 质询验证**，并提供 Entra 应用注册的租户 ID、客户端 ID 和客户端密钥：

1. 在 Microsoft Entra ID 中注册一个应用，并授予其 **Intune API → SCEP challenge validation**（\`scep_challenge_provider\`）和 **Microsoft Graph → Application.Read.All** 应用程序权限，两者均需管理员同意
2. 在 **Intune 应用注册** 中添加一次应用注册（名称、租户 ID、客户端 ID、客户端密钥），然后点击**测试连接**，确认 UCM 能够连接到 Intune；随后在配置文件的 **应用注册** 选择器中选择它。同一租户的配置文件共享该应用注册，因此密钥只需在一处轮换
3. 在 Intune 中，将设备 SCEP 配置文件的服务器 URL 指向此配置文件的 \`/scep/<segment>/pkiclient.exe\` 端点

启用了 Intune 的配置文件必须启用**自动批准**:, Intune 的注册是同步的验证并签发往返过程，Intune 一侧没有供人工审核的队列。

> 💡 SCEP 是传统协议。对于新部署，如果设备支持，建议优先使用 EST。
`
  }
}
