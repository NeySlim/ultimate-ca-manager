export default {
  helpContent: {
    title: 'EST',
    subtitle: '安全传输注册协议',
    overview: 'EST（RFC 7030）通过 HTTPS 提供安全的证书注册，支持双向 TLS（mTLS）或 HTTP Basic 认证。适用于需要基于标准的注册协议和强传输安全的现代企业环境。',
    sections: [
      {
        title: '选项卡',
        items: [
          { label: '设置', text: '启用 EST、选择签名 CA、配置认证凭据和证书有效期' },
          { label: 'EST 端点', text: '用于集成的 EST 端点 URL 和注册统计' },
        ]
      },
      {
        title: '认证方式',
        items: [
          { label: 'mTLS（双向 TLS）', text: '客户端在 TLS 握手期间提供证书,, 最强的认证方式' },
          { label: 'HTTP Basic Auth', text: '在 mTLS 不可用时的用户名/密码回退方式。通过 PATCH /api/v2/est/config 设置 allow_empty_username 后，客户端也可以发送空用户名加密码（RFC 7030 §3.2.3，v2.252）' },
          { label: '出示的证书', text: '对于通过 mTLS 访问的 /simpleenroll 和 /serverkeygen，由 EST CA 签发的证书必须是该 CA 仍持有的证书：已吊销、已被取代或已删除的证书会被拒绝（RFC 7030 §3.3.2）；由本服务器的其他 CA 签发的证书，在其自身或其上级 CA 被吊销或已过期后会被拒绝（v2.252）；来自本服务器未持有的颁发机构的证书则交由 TLS 层处理' },
          { label: 'tls-unique 绑定', text: '带有 challengePassword 的 CSR 必须携带其到 UCM 的 TLS 1.2 连接的 tls-unique 值（RFC 7030 §3.5）；该值不同或无法验证（TLS 1.3、前置代理）时以 400 拒绝。/csrattrs 不要求该值。通过 PATCH /api/v2/est/config 设置的 ignore_challenge_password 会为在此处放入密码的客户端跳过该检查（v2.252）' },
          { label: '已泄露的密钥', text: '密钥已因泄露（keyCompromise）而吊销的 CSR 会以 400 拒绝（v2.252）' },
        ]
      },
      {
        title: '端点',
        items: [
          { label: '/cacerts', text: '获取 CA 证书链（无需认证）' },
          { label: '/simpleenroll', text: '提交 CSR 并接收签名证书' },
          { label: '/simplereenroll', text: '续期已有证书（需要 mTLS；没有客户端证书时：403）。不含 SubjectAltName 的 CSR 会续期该证书自身的名称，原本没有则不带名称，而不是由 CN 构造名称（RFC 7030 §4.2.2，v2.252）' },
          { label: '/csrattrs', text: '获取服务器推荐的 CSR 属性：keyUsage、subjectAltName 和 extKeyUsage，均为裸 OID（RFC 9908 §5.2，v2.252）。通过 PATCH /api/v2/est/config 设置的 csrattrs_legacy_encoding 会为需要的客户端提供旧格式（OID 位于 extensionRequest 内）。' },
          { label: '错误', text: '注册被拒绝（包括速率限制）时，会以纯文本消息（text/plain，RFC 8951 §5）说明原因，例如正文不是 base64 或不是 PKCS#10 CSR，或违反 CA 的名称约束（v2.252）' },
          { label: '/serverkeygen', text: '服务器生成密钥对并返回证书 + 密钥。密钥采用签发 CA 的强度：请求密钥为 RSA 或 EC 时沿用其类型（其大小或曲线被忽略），否则沿用 CA 的类型，并调整为策略允许的最接近类型。密钥在 TLS 下以未加密的 PKCS#8 返回；若 CSR 指明了 mTLS 证书的密钥 (AsymmetricDecryptKeyIdentifier)，则会加密给该证书：2048 位及以上的 RSA 使用密钥传输 (keyEncipherment)，EC 使用密钥协商 (keyAgreement)，算法取自 CSR 的 SMIMECapabilities 所列，并放入由签发 CA 为此签发的 EST key generator 证书签名的密钥包中（Ed448 CA 下为 Ed25519，v2.252）' },
        ]
      },
    ],
    tips: [
      'EST 是 SCEP 的现代替代方案:, 新部署请优先使用 EST',
      '使用 mTLS 认证获得最高安全性:, Basic Auth 是备用方案',
      '/simplereenroll 端点要求客户端通过 mTLS 提供当前证书',
      '从 EST 端点选项卡复制端点 URL 以配置您的 EST 客户端',
    ],
    warnings: [
      'EST 需要 HTTPS:, 客户端必须信任 UCM 服务器证书或 CA',
      'mTLS 认证需要正确的 TLS 终止配置（反向代理必须转发客户端证书）',
    ],
  },
  helpGuides: {
    title: 'EST 协议',
    content: `
## 概述

安全传输注册协议（EST）定义于 **RFC 7030**，通过 HTTPS 提供证书注册、重新注册和 CA 证书检索。EST 是 SCEP 的现代替代方案，通过双向 TLS（mTLS）认证提供更强的安全性。

## 配置

### 设置选项卡

1. **启用 EST**: 开启或关闭 EST 协议
2. **签名 CA**: 选择为 EST 注册的证书签名的证书颁发机构
3. **认证**: 配置 HTTP Basic Auth 凭据（用户名和密码）
4. **证书有效期**: EST 签发证书的默认有效期（天数）

### 保存配置

点击**保存**以应用更改。启用后 EST 端点将立即可用。

## 认证方式

EST 支持两种认证方式：

### 双向 TLS（mTLS）:, 推荐

客户端在 TLS 握手期间提供证书。UCM 验证证书并自动认证客户端。

- **最强方式**: 加密的客户端身份
- **必须用于** \`/simplereenroll\`: 客户端必须提供当前证书
- **出示的证书**: 对于 \`/simpleenroll\` 和 \`/serverkeygen\`，由 EST CA 签发的证书必须是该 CA 仍持有的证书：已吊销、已被取代或已删除的证书会被拒绝（RFC 7030 §3.3.2）；其他受信任颁发机构签发的证书仍会被接受
- **依赖于** 正确的 TLS 终止配置（反向代理必须将 \`SSL_CLIENT_CERT\` 传递给 UCM）

### HTTP Basic Auth:, 备用

通过 HTTPS 进行用户名和密码认证。在 EST 设置中配置。

- **设置更简单**: 不需要客户端证书
- **安全性较低**: 凭据在每次请求中传输（由 HTTPS 保护）
- **使用场景**: mTLS 基础设施不可用时

## EST 端点

所有端点位于 \`/.well-known/est/\` 下：

### GET /cacerts
获取 CA 证书链。**无需认证。**

用于引导信任:, 客户端在注册前获取 CA 证书。

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
提交 PKCS#10 CSR 并接收签名证书。

需要认证（mTLS 或 Basic Auth）。

\`\`\`bash
# 使用 curl 和 Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
续期已有证书。**需要 mTLS**: 客户端必须提供正在续期的证书。

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
获取服务器推荐的 CSR 属性（OID）。

### POST /serverkeygen
服务器生成密钥对并返回证书和私钥。适用于客户端无法在本地生成密钥的场景。

生成的密钥采用签发 CA 的强度：请求密钥为 RSA 或 EC 时沿用其类型（其大小或曲线被忽略），否则沿用 CA 的类型，并调整为策略允许的最接近类型。

私钥以未加密的 PKCS#8 (\`application/pkcs8\`) 返回，由 TLS 保护。若要加密返回，请使用 mTLS 认证，并在 CSR 中写入客户端证书的密钥标识符 (AsymmetricDecryptKeyIdentifier)：密钥将以 RFC 5958 密钥包的形式封装给该证书，断言 keyEncipherment 的 2048 位及以上 RSA 证书使用密钥传输，断言 keyAgreement 的 EC 证书使用密钥协商 (ECDH)；密钥传输或密钥协商算法以及内容算法按客户端的顺序取自 CSR 的 SMIMECapabilities。该密钥包由“EST key generator”证书签名，该证书由签发 CA 在首次使用时签发并自动续期；它链接到 \`/cacerts\` 提供的 CA，并采用该 CA 的密钥族，Ed448 CA 下为 Ed25519 (v2.252)。

## EST 端点选项卡

EST 端点选项卡显示：
- **端点 URL**: 可直接复制粘贴的各 EST 操作 URL
- **注册统计**: 注册总数、成功数和失败数

## 集成示例

### 使用 est client (libest)
使用 \`estclient\` 搭配 HTTP Basic 凭据（\`-u\` 和 \`-h\`）或客户端证书。其 TLS-SRP 选项不适用：UCM 不提供 TLS-SRP。

### 使用 OpenSSL
\`\`\`bash
# 获取 CA 证书
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# 生成 CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# 注册（Basic Auth）
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

应答是 base64 编码的 PKCS#7（仅含证书），而不是单独的证书：请用 \`openssl pkcs7\` 读取，而不是 \`openssl x509\`。

### Windows
Windows 没有内置的 EST 客户端：\`certutil -enrollmentServerURL\` 注册的是证书注册 Web 服务（WSTEP），而不是 EST 服务器。对于 Windows 计算机，请使用 Windows 自动注册（XCEP/WSTEP）。

## EST 与 SCEP 对比

| 特性 | EST | SCEP |
|---------|-----|------|
| 传输 | HTTPS (TLS) | HTTP 或 HTTPS |
| 认证 | mTLS + Basic Auth | 挑战密码 |
| 标准 | RFC 7030 (2013) | RFC 8894 (2020, 但属于遗留) |
| 密钥生成 | 可服务器端 | 仅客户端 |
| 续期 | mTLS 重新注册 | 重新注册 |
| 安全性 | 强（基于 TLS） | 较弱（共享密钥） |
| 建议 | ✅ 新部署首选 | 仅用于遗留设备 |

> 💡 新部署请使用 EST。仅在不支持 EST 的遗留网络设备上使用 SCEP。
`
  }
}
