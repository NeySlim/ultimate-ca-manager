export default {
  helpContent: {
    title: 'ACME',
    subtitle: '自动化证书管理',
    overview: 'UCM 支持两种 ACME 模式：ACME 客户端用于从任何符合 RFC 8555 的 CA（Let\'s Encrypt、ZeroSSL、Buypass、HARICA 等）获取公共证书；本地 ACME 服务器用于内部 PKI 自动化，支持多 CA 域名映射。',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "本地 ACME 服务器公布 renewalInfo 资源，使客户端了解每个证书的理想续期时机。",
        items: [
          { label: "建议窗口", text: "返回一个以到期前为中心的开始/结束窗口，使续期错峰分布" },
          { label: "吊销", text: "已吊销证书返回过去的窗口 → 合规客户端立即续期" },
          { label: "无需认证", text: "renewalInfo 是普通 GET——无需账户或 JWS（RFC 9773）" },
        ]
      },
      {
        title: 'ACME 客户端',
        items: [
          { label: '客户端', text: '从任何 ACME CA 请求证书——Let\'s Encrypt、ZeroSSL、Buypass、HARICA 或自定义' },
          { label: '自定义服务器', text: '设置自定义 ACME 目录 URL 以使用任何符合 RFC 8555 的 CA' },
          { label: 'EAB', text: '支持外部账户绑定，用于需要预注册的 CA（ZeroSSL、HARICA 等）' },
          { label: '密钥类型', text: '证书密钥支持 RSA-2048、RSA-4096、ECDSA P-256、ECDSA P-384' },
          { label: '账户密钥', text: 'ACME 账户密钥支持 ES256 (P-256)、ES384 (P-384) 或 RS256 算法' },
          { label: 'DNS 提供商', text: '配置 DNS-01 挑战提供商（Cloudflare、Route53 等）' },
          { label: '域名', text: '将域名映射到 DNS 提供商以进行自动验证' },
        ]
      },
      {
        title: '本地 ACME 服务器',
        items: [
          { label: '配置', text: '启用/禁用内置 ACME 服务器，选择默认 CA' },
          { label: '本地域名', text: '将内部域名映射到特定 CA 以实现多 CA 签发' },
          { label: '账户', text: '查看和管理已注册的 ACME 客户端账户' },
          { label: '历史', text: '跟踪所有 ACME 证书签发订单' },
        ]
      },
      {
        title: 'ACME 代理',
        items: [
          { label: '上游CA', text: '选择预设（Let\'s Encrypt 生产/测试）或输入任何 RFC 8555 CA 的自定义URL' },
          { label: '账户状态', text: '显示UCM是否已在上游CA注册。账户在首次代理请求时自动注册' },
          { label: '测试连接', text: '验证与上游CA的连接性并检查是否需要EAB凭据' },
          { label: '重置账户', text: '清除保存的上游账户凭据以强制重新注册（更改CA后使用）' },
          { label: 'EAB凭据', text: '需要EAB的CA的External Account Binding凭据（如ZeroSSL、Google Trust）' },
          { label: 'DNS挑战', text: 'UCM使用配置的DNS提供商代表客户端处理DNS-01挑战' },
        ]
      },
      {
        title: 'EAB 凭据(服务器端)',
        content: '当 UCM 作为 ACME 服务器时,External Account Binding(RFC 8555 §7.3.4)允许在客户端注册账户之前要求预先发行的凭据:',
        items: [
          { label: '签发', text: '从 ACME → EAB Credentials 生成新的 kid + HMAC 密钥对' },
          { label: '分发', text: '将 kid + HMAC 交给客户端(cert-manager、certbot、acme.sh)' },
          { label: '绑定', text: '客户端在 newAccount 上对 MAC 密钥签名 JWS 以绑定其 ACME 账户' },
          { label: '轮换 / 撤销', text: '随时撤销 kid — 现有账户继续工作,新绑定被拒绝' },
          { label: '审计', text: '签发、轮换和撤销在执行操作员名下进行审计' },
        ]
      },
      {
        title: '自定义 DNS 解析器(DNS-01)',
        items: [
          { label: '账户级覆盖', text: '在验证 _acme-challenge TXT 记录时覆盖系统解析器' },
          { label: '分裂视图', text: '当权威服务器在内部但公网视图被其他地方缓存时有用' },
          { label: '过时记录', text: '在快速自动续期期间避免公共解析器缓存' },
        ]
      },
      {
        title: '在内部 / 私有 IP 上的 ACME',
        content: 'HTTP-01 和 TLS-ALPN-01 验证对 RFC1918、loopback、.lan / .local / .corp 目标开箱即用 — UCM 的主要部署模式。',
        items: [
          { label: '开关', text: 'Settings → SystemConfig → acme.allow_private_ips(默认:true)' },
          { label: '始终阻止', text: '云元数据 IP(169.254.169.254、fd00:ec2::254 等)无条件阻止' },
        ]
      },
      {
        title: '多 CA 解析',
        content: '当 ACME 客户端请求证书时，UCM 按以下顺序解析签名 CA：',
        items: [
          '1. 本地域名映射——精确域名匹配，然后父域名',
          '2. DNS 域名映射——检查为 DNS 提供商配置的签发 CA',
          '3. 全局默认——ACME 服务器配置中设置的 CA',
          '4. 第一个拥有私钥的可用 CA',
        ]
      },
      {
        title: 'IP 地址证书 (RFC 8738)',
        content: '本地 ACME 服务器不仅可以为 DNS 名称签发证书，还可以为 IPv4 和 IPv6 地址签发证书。在订单中使用标识符类型“ip”。',
        items: [
          { label: '标识符', text: '使用 { "type": "ip", "value": "192.0.2.10" }（IPv4）或像 2001:db8::1 这样的 IPv6 字面量下单' },
          { label: '质询', text: '仅提供 HTTP-01 和 TLS-ALPN-01 — 根据 RFC 8738，IP 标识符禁止使用 DNS-01' },
          { label: 'TLS-ALPN-01 SNI', text: '验证使用反向 DNS 形式（in-addr.arpa / ip6.arpa）作为 SNI 主机名' },
          { label: '签发的 SAN', text: '证书包含 iPAddress SAN；支持 DNS + IP 混合订单' },
          { label: '内部 IP', text: 'RFC1918 和环回地址开箱即可验证 — UCM 的主要部署模式' },
        ]
      }
    ],
    tips: [
      'ACME 目录 URL：https://your-server:port/acme/directory',
      '使用自定义目录 URL 连接到 ZeroSSL、Buypass、HARICA 或任何 RFC 8555 CA',
      'EAB 凭据（密钥 ID + HMAC 密钥）由您的 CA 在注册时提供',
      'ECDSA P-256 密钥提供与 RSA-2048 等效的安全性，但体积更小',
      '使用本地域名为不同的内部域名分配不同的 CA',
      '任何拥有私钥的 CA 都可以被选为签发 CA',
      '通配符域名 (*.example.com) 需要 DNS-01 验证',
      '当 UCM 是 ACME 服务器时,在 ACME → EAB Credentials 中签发您自己的 EAB 凭据',
      '对于 Kubernetes/cert-manager:参见 examples/kubernetes/cert-manager/ 中的参考清单',
    ],
    warnings: [
      '域名验证是必需的——您的服务器必须可达或已配置 DNS',
      '更改账户密钥类型需要重新注册 ACME 账户',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## 概述

UCM 支持两种 ACME（自动化证书管理环境）模式：

- **ACME 客户端** — 从任何符合 RFC 8555 的 CA 获取证书（Let's Encrypt、ZeroSSL、Buypass、HARICA 或自定义）
- **本地 ACME 服务器** — 内置 ACME 服务器，用于内部 PKI 自动化，支持多 CA

## ACME 客户端

### 客户端设置
管理您的 ACME 客户端配置：
- **环境** — 测试（staging）或生产（正式证书）
- **联系邮箱** — 账户注册时必填
- **自动续期** — 在证书到期前自动续期
- **证书密钥类型** — RSA-2048、RSA-4096、ECDSA P-256 或 ECDSA P-384
- **账户密钥算法** — ES256、ES384 或 RS256 用于 ACME 账户签名

### 自定义 ACME 服务器
使用任何符合 RFC 8555 的 CA，不仅限于 Let's Encrypt：

| CA 提供商 | 目录 URL |
|---|---|
| **Let's Encrypt** | *（默认，留空）* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

在**设置** → **自定义 ACME 服务器**中设置 CA 的目录 URL。

### 外部账户绑定（EAB）
某些 CA 需要 EAB 凭据将您的 ACME 账户与 CA 上的现有账户关联：

1. 在 CA 的门户网站注册以获取 **EAB 密钥 ID** 和 **HMAC 密钥**
2. 在**设置** → **自定义 ACME 服务器**中输入这两个值
3. HMAC 密钥是 base64url 编码的（由 CA 提供）

> 💡 ZeroSSL、HARICA、Google Trust Services 和大多数企业 CA 都需要 EAB。

### ECDSA 与 RSA 密钥对比

| 密钥类型 | 大小 | 安全性 | 性能 |
|---|---|---|---|
| **RSA-2048** | 2048 位 | 标准 | 基准 |
| **RSA-4096** | 4096 位 | 更高 | 更慢 |
| **ECDSA P-256** | 256 位 | ≈ RSA-3072 | 快得多 |
| **ECDSA P-384** | 384 位 | ≈ RSA-7680 | 更快 |

ECDSA 密钥推荐用于现代部署——更小、更快且同样安全。

### DNS 提供商
配置 DNS-01 挑战提供商以进行域名验证。支持的提供商包括：
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- 等等

每个提供商需要特定于该 DNS 服务的 API 凭据。

### 域名
将域名映射到 DNS 提供商。当为域名请求证书时，UCM 使用映射的提供商创建 DNS-01 挑战记录。

1. 点击**添加域名**
2. 输入域名（例如 \`example.com\` 或 \`*.example.com\`）
3. 选择 DNS 提供商
4. 点击**保存**

> 💡 通配符证书（\`*.example.com\`）需要 DNS-01 验证。


## ACME代理模式

ACME代理允许内部客户端通过UCM从公共CA（Let's Encrypt、ZeroSSL等）请求证书，无需直接访问互联网。UCM作为中间人，管理DNS-01挑战并将请求转发到上游CA。

### 何时使用代理模式
- 无法直接访问互联网的内部服务器
- 通过UCM配置的DNS提供商集中处理DNS-01挑战
- 审计和跟踪所有公共证书的签发

### 配置
1. 转到 **ACME** → **Let's Encrypt** 选项卡
2. 滚动到 **ACME代理** 部分
3. 启用 **ACME代理** 开关
4. 在 **外部 CA 账户** 中选择 **上游 CA 账户**（Let's Encrypt、Actalis、ZeroSSL、自定义 URL、EAB）
5. 点击 **测试连接** 验证与上游 CA 的连接
6. 如需要，注册上游账户（邮箱 + **注册账户**）
7. 若尚未注册，UCM 在首次代理请求时自动注册

### 专用代理路径（多 CA）
每个外部 CA 账户可暴露自己的 ACME 代理端点：

1. 打开 **外部 CA 账户**（同一 Let's Encrypt 选项卡）
2. 编辑或创建 CA 账户
3. 启用 **通过 ACME 代理暴露**
4. 设置唯一的 **代理路径 (slug)** — 如 \`actalis-production\`
5. 保存 — URL 显示在代理部分和账户卡片上

客户端使用：
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

遗留默认路径（代理设置中所选账户）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

保留 slug（不可用）：\`directory\`、\`new-order\`、\`challenge\`、\`acct\` 等

### 账户管理
- **账户状态标记** 显示UCM是否已在上游CA注册
- 更换上游CA会自动清除过时凭据并强制重新注册
- 如需手动清除凭据，使用 **重置账户** 按钮
- **测试连接** 检查上游目录是否可达以及是否需要EAB

### 使用代理
将内部 ACME 客户端指向目标 CA 的代理目录。

**按 slug 的 URL**（多 CA 时推荐）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

**默认 URL**（代理设置中所选账户）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

certbot 示例（替换 \`<slug>\`）：
\`\`\`
certbot certonly \\
  --server https://your-ucm-server:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 代理 EAB 凭据与客户端 EAB 不同——用于 UCM 向上游 CA 认证。

> ⚠ 前提：域名须在 ACME Domains 中配置 DNS 提供商。代理仅支持 dns-01。

> ⚠ 避免对同一 FQDN 并发请求（Certbot + UCM 界面）。

> ℹ️ 自签名 HTTPS（实验环境）请为 Certbot 添加 \`--no-verify-ssl\`。

## 本地 ACME 服务器

### 配置
- **启用/禁用** — 切换内置 ACME 服务器
- **默认 CA** — 选择默认签署证书的 CA
- **服务条款** — 客户端可选的服务条款 URL

### ACME 目录 URL
\`\`\`
https://your-server:8443/acme/directory
\`\`\`

certbot、acme.sh 或 Caddy 等客户端使用此 URL 来发现 ACME 端点。

### 本地域名（多 CA）
将内部域名映射到特定 CA。这允许不同域名由不同 CA 签署。

1. 点击**添加域名**
2. 输入域名（例如 \`internal.corp\` 或 \`*.dev.local\`）
3. 选择**签发 CA**
4. 启用/禁用**自动批准**
5. 点击**保存**

### CA 解析顺序
当 ACME 客户端请求证书时，UCM 按以下顺序确定签名 CA：
1. **本地域名映射** — 精确匹配，然后父域名匹配
2. **DNS 域名映射** — 为 DNS 提供商配置的 CA
3. **全局默认** — ACME 服务器配置中设置的 CA
4. **第一个可用** — 任何拥有私钥的 CA

### 账户
查看已注册的 ACME 客户端账户：
- 账户 ID 和联系邮箱
- 注册日期
- 订单数量

### 历史
浏览所有证书签发订单：
- 订单状态（pending、valid、invalid、ready）
- 请求的域名
- 使用的签名 CA
- 签发时间戳

## 使用 certbot

\`\`\`
# 注册账户（Let's Encrypt——默认）
certbot register --agree-tos --email admin@example.com

# 使用自定义 ACME CA + EAB 注册
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --agree-tos --email admin@example.com

# 使用 ECDSA 密钥请求证书
certbot certonly --server https://your-server:8443/acme/directory \\
  --standalone -d myserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# 续期
certbot renew --server https://your-server:8443/acme/directory
\`\`\`

## 使用 acme.sh

\`\`\`
# 默认（Let's Encrypt）
acme.sh --issue -d example.com --standalone

# 使用自定义 ACME CA + EAB 和 ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ 对于内部 ACME，客户端必须信任 UCM CA。在客户端的信任存储中安装根 CA 证书。
## IP 地址证书 (RFC 8738)

本地 ACME 服务器不仅可以为 DNS 名称签发证书，还可以为 **IP 地址**（IPv4 和 IPv6）签发证书。适用于内部服务、设备以及直接通过 IP 寻址的主机。

### 订购 IP 证书
在 ACME 订单中使用标识符类型 \`ip\`：
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
也支持 DNS + IP 混合订单。

### 验证
- 对于 IP 标识符，仅提供 **HTTP-01** 和 **TLS-ALPN-01** 质询。根据 RFC 8738，IP **禁止使用 DNS-01**。
- **HTTP-01** 直接连接到 IP（IPv6 字面量需加方括号，例如 \`http://[2001:db8::1]/...\`）。
- **TLS-ALPN-01** 使用 IP 的反向 DNS 形式（\`in-addr.arpa\` / \`ip6.arpa\`）作为 SNI 主机名。

### 签发的证书
签名后的证书为每个已验证的 IP 包含一个 **iPAddress** SubjectAltName 条目。

> 💡 内部地址（RFC1918、环回）开箱即可验证 — UCM 的主要部署模式。云元数据 IP 仍被阻止。

## Renewal Information (ARI, RFC 9773)

本地 ACME 服务器在其 directory 中公布 \`renewalInfo\`，并为每个证书提供**建议续期窗口**。

- 窗口以到期前为中心 → 续期随时间错峰
- 已吊销证书 → 过去的窗口（立即续期）
- 对 \`/acme/renewalInfo/<certID>\` 的无认证 GET

`
  }
}
