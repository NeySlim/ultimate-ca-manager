export default {
  helpContent: {
    title: 'TSA',
    subtitle: '时间戳颁发机构',
    overview: 'TSA（RFC 3161）提供可信时间戳，证明文档或哈希值在特定时间点存在。用于代码签名、法律合规和审计追踪。',
    sections: [
      {
        title: '选项卡',
        items: [
          { label: '设置', text: '启用 TSA、选择签名 CA 并配置 TSA 策略 OID' },
          { label: '信息', text: 'TSA 端点 URL、OpenSSL 使用示例和请求统计' },
        ]
      },
      {
        title: '配置',
        items: [
          { label: '签名 CA', text: '用于签署时间戳令牌的 CA 私钥——必须是有效且未过期的 CA' },
          { label: '策略 OID', text: 'TSA 策略的对象标识符（例如 1.2.3.4.1）——包含在每个时间戳响应中' },
          { label: '启用/禁用', text: '在不丢失配置的情况下开关 TSA 端点' },
          { label: '要求专用证书', text: '可选启用：拒绝使用 CA 证书本身签署时间戳——需要一个带有关键 timeStamping EKU 的专用终端实体签名证书（RFC 3161）' },
                  { label: '签名证书 (v2.217)', text: '使用从已签发证书中选择的专用终端实体证书（timeStamping EKU，私钥由 UCM 持有）签署令牌。续期会被自动跟随；过期或被吊销的签名者会使请求以 503 失败，绝不回退到 CA 证书' },
                  { label: '生成签名证书 (v2.218)', text: '一键签发专用的 RFC 3161 签名证书：CA:FALSE、KeyUsage 仅含 digitalSignature，外加关键且独占的 timeStamping EKU——正是严格校验器（openssl ts -verify）所要求的形态。证书由已配置的 TSA CA 签发，并在没有可用签名者时被自动选用。该证书的来源为 "manual"：请将 "manual" 加入自动续期来源，或在到期前自行续期' },
        ]
      },
      {
        title: '使用方法',
        items: [
          { label: '创建请求', text: 'openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq' },
          { label: '发送到 TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: '验证', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'TSA 时间戳用于代码签名，确保签名在证书过期后仍然有效',
      'TSA 端点接受 HTTP POST，Content-Type 为 application/timestamp-query',
      '创建时间戳请求时使用 SHA-256 或更强的哈希算法',
      '无需认证——TSA 端点像 CRL/OCSP 一样是公开可访问的',
    ],
    warnings: [
      '启用 TSA 之前必须配置有效的签名 CA',
      'TSA 端点是公共协议端点——不要在时间戳请求中放入敏感数据',
    ],
  },
  helpGuides: {
    title: 'TSA 协议',
    content: `
## 概述

时间戳颁发机构（TSA）实现了 **RFC 3161**，提供可信时间戳，以密码学方式证明文档、哈希值或数字签名在特定时间点存在。TSA 广泛用于代码签名、法律合规、长期归档和审计追踪。

## 工作原理

1. **客户端创建时间戳请求** — 使用 SHA-256/SHA-512 对文件进行哈希并创建 \`TimeStampReq\`（ASN.1 DER 编码）
2. **客户端向 TSA 发送请求** — HTTP POST 到 \`/tsa\` 端点，Content-Type 为 \`application/timestamp-query\`
3. **UCM 签署时间戳** — 配置的 CA 将哈希值和当前时间签署为 \`TimeStampResp\`
4. **客户端接收并存储响应** — \`.tsr\` 文件可以在之后证明文档在该时间点存在

## 配置

### 设置选项卡

1. **启用 TSA** — 开关 TSA 服务器
2. **签名 CA** — 选择哪个证书颁发机构签署时间戳令牌
3. **策略 OID** — TSA 策略的对象标识符（例如 \`1.2.3.4.1\`），包含在每个时间戳响应中

### 选择签名 CA

签名 CA 的私钥用于签署每个时间戳令牌。最佳实践：

- 使用**专用子 CA** 进行时间戳签发，而不是根 CA
- CA 证书应包含 **id-kp-timeStamping** 扩展密钥用途（OID 1.3.6.1.5.5.7.3.8）
- 确保 CA 证书有**足够的有效期**——时间戳必须在数年内保持可验证
- 启用**要求专用时间戳证书**，在签名时强制执行此要求，而不是依赖约定

### 策略 OID

策略 OID 标识时间戳签发所依据的 TSA 策略。它嵌入在每个 \`TimeStampResp\` 中。

- 默认值：\`1.2.3.4.1\`（占位符）
- 生产环境中，请在您组织的 OID 弧下注册一个 OID，或使用 CP/CPS 中的 OID

## 信息选项卡

信息选项卡显示：

- **TSA 端点 URL** — 可直接复制的客户端配置 URL
- **使用示例** — 用于创建请求、发送请求和验证响应的 OpenSSL 命令
- **统计数据** — 已处理的时间戳请求总数（成功和失败）

## 使用示例

### 创建时间戳请求

\`\`\`bash
# 对文件进行哈希并创建时间戳请求
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### 向 TSA 发送请求

\`\`\`bash
# 发送请求并接收时间戳响应
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### 验证时间戳

\`\`\`bash
# 根据原始文件验证时间戳响应
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### 代码签名与时间戳

签署代码时，添加 TSA URL 以确保签名在证书过期后仍然有效：

\`\`\`bash
# 使用时间戳签名（osslsigncode）
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# 使用时间戳签名（Windows 上的 signtool.exe）
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### PDF 文档时间戳

\`\`\`bash
# 为 PDF 创建分离式时间戳
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://your-server:8443/tsa -o document.tsr
\`\`\`

## 协议详情

| 属性 | 值 |
|------|-----|
| RFC | 3161 (Internet X.509 PKI TSP) |
| 端点 | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| 响应类型 | \`application/timestamp-reply\` |
| 哈希算法 | SHA-256、SHA-384、SHA-512、SHA-1（旧版） |
| 认证 | 无（公共端点） |
| 传输 | HTTP 或 HTTPS |

## 安全注意事项

- TSA 端点是**公共的**——无需认证（与 CRL/OCSP 相同）
- 每个时间戳响应都由 CA 密钥**签名**——客户端验证签名以确保真实性
- 创建请求时使用 **SHA-256 或更强**的哈希算法（SHA-1 可接受但不推荐）
- TSA **不会**看到原始文档——只传输哈希值
- 如果 TSA 端点暴露在互联网上，考虑**速率限制**

> 💡 时间戳对代码签名至关重要：它们确保您的签名软件在签名证书过期后仍然受信任。
`
  }
}
