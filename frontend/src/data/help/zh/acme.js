export default {
  helpContent: {
    title: 'ACME',
    subtitle: '自动化证书管理',
    overview: 'UCM 支持两种 ACME 模式：ACME 客户端用于从任何符合 RFC 8555 的 CA（Let\'s Encrypt、ZeroSSL、Buypass、HARICA 等）获取公共证书；本地 ACME 服务器用于内部 PKI 自动化，支持多 CA 域名映射。',
    sections: [
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
        title: '多 CA 解析',
        content: '当 ACME 客户端请求证书时，UCM 按以下顺序解析签名 CA：',
        items: [
          '1. 本地域名映射——精确域名匹配，然后父域名',
          '2. DNS 域名映射——检查为 DNS 提供商配置的签发 CA',
          '3. 全局默认——ACME 服务器配置中设置的 CA',
          '4. 第一个拥有私钥的可用 CA',
        ]
      },
    ],
    tips: [
      'ACME 目录 URL：https://your-server:port/acme/directory',
      '使用自定义目录 URL 连接到 ZeroSSL、Buypass、HARICA 或任何 RFC 8555 CA',
      'EAB 凭据（密钥 ID + HMAC 密钥）由您的 CA 在注册时提供',
      'ECDSA P-256 密钥提供与 RSA-2048 等效的安全性，但体积更小',
      '使用本地域名为不同的内部域名分配不同的 CA',
      '任何拥有私钥的 CA 都可以被选为签发 CA',
      '通配符域名 (*.example.com) 需要 DNS-01 验证',
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
`
  }
}
