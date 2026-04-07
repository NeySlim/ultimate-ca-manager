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
          { label: '信息', text: '用于集成的 EST 端点 URL、注册统计和使用示例' },
        ]
      },
      {
        title: '认证方式',
        items: [
          { label: 'mTLS（双向 TLS）', text: '客户端在 TLS 握手期间提供证书——最强的认证方式' },
          { label: 'HTTP Basic Auth', text: '在 mTLS 不可用时的用户名/密码回退方式' },
        ]
      },
      {
        title: '端点',
        items: [
          { label: '/cacerts', text: '获取 CA 证书链（无需认证）' },
          { label: '/simpleenroll', text: '提交 CSR 并接收签名证书' },
          { label: '/simplereenroll', text: '续期已有证书（需要 mTLS）' },
          { label: '/csrattrs', text: '获取服务器推荐的 CSR 属性' },
          { label: '/serverkeygen', text: '服务器生成密钥对并返回证书 + 密钥' },
        ]
      },
    ],
    tips: [
      'EST 是 SCEP 的现代替代方案——新部署请优先使用 EST',
      '使用 mTLS 认证获得最高安全性——Basic Auth 是备用方案',
      '/simplereenroll 端点要求客户端通过 mTLS 提供当前证书',
      '从信息选项卡复制端点 URL 以配置您的 EST 客户端',
    ],
    warnings: [
      'EST 需要 HTTPS——客户端必须信任 UCM 服务器证书或 CA',
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

1. **启用 EST** — 开启或关闭 EST 协议
2. **签名 CA** — 选择为 EST 注册的证书签名的证书颁发机构
3. **认证** — 配置 HTTP Basic Auth 凭据（用户名和密码）
4. **证书有效期** — EST 签发证书的默认有效期（天数）

### 保存配置

点击**保存**以应用更改。启用后 EST 端点将立即可用。

## 认证方式

EST 支持两种认证方式：

### 双向 TLS（mTLS）——推荐

客户端在 TLS 握手期间提供证书。UCM 验证证书并自动认证客户端。

- **最强方式** — 加密的客户端身份
- **必须用于** \`/simplereenroll\` — 客户端必须提供当前证书
- **依赖于** 正确的 TLS 终止配置（反向代理必须将 \`SSL_CLIENT_CERT\` 传递给 UCM）

### HTTP Basic Auth——备用

通过 HTTPS 进行用户名和密码认证。在 EST 设置中配置。

- **设置更简单** — 不需要客户端证书
- **安全性较低** — 凭据在每次请求中传输（由 HTTPS 保护）
- **使用场景** — mTLS 基础设施不可用时

## EST 端点

所有端点位于 \`/.well-known/est/\` 下：

### GET /cacerts
获取 CA 证书链。**无需认证。**

用于引导信任——客户端在注册前获取 CA 证书。

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
续期已有证书。**需要 mTLS** — 客户端必须提供正在续期的证书。

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

## 信息选项卡

信息选项卡显示：
- **端点 URL** — 可直接复制粘贴的各 EST 操作 URL
- **注册统计** — 注册、重新注册和错误的数量
- **最近活动** — 审计日志中最近的 EST 操作

## 集成示例

### 使用 est client (libest)
\`\`\`bash
estclient -s your-server -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

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
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://your-server:8443/.well-known/est" \\
  kerberos
\`\`\`

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
