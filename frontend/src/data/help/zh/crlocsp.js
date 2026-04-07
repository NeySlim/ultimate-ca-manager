export default {
  helpContent: {
    title: 'CRL 与 OCSP',
    subtitle: '证书吊销服务',
    overview: '管理证书吊销列表（CRL）和在线证书状态协议（OCSP）服务。这些服务允许客户端验证证书是否已被吊销。',
    sections: [
      {
        title: 'CRL 管理',
        items: [
          { label: '自动重新生成', text: '按 CA 切换 CRL 自动重新生成' },
          { label: '手动重新生成', text: '立即强制重新生成 CRL' },
          { label: '下载 CRL', text: '以 DER 或 PEM 格式下载 CRL 文件' },
          { label: 'CDP URL', text: '嵌入证书中的 CRL 分发点 URL' },
        ]
      },
      {
        title: 'OCSP 服务',
        items: [
          { label: '状态', text: '指示每个 CA 的 OCSP 响应器是否处于活动状态' },
          { label: 'AIA URL', text: '颁发机构信息访问 URL——OCSP 响应器和 CA 签发者证书下载端点，嵌入在签发的证书中' },
          { label: '缓存', text: '响应缓存，自动每日清理过期条目' },
          { label: '总查询数', text: '已处理的 OCSP 请求数量' },
        ]
      },
    ],
    tips: [
      '启用自动重新生成以在证书吊销后保持 CRL 更新',
      '复制 CDP、OCSP 和 AIA CA 签发者 URL 以将其嵌入您的证书配置文件',
      'OCSP 提供实时吊销检查，优于 CRL',
    ],
  },
  helpGuides: {
    title: 'CRL 与 OCSP',
    content: `
## 概述

证书吊销列表（CRL）和在线证书状态协议（OCSP）允许客户端验证证书是否已被吊销。UCM 同时支持这两种机制。

## CRL 管理

### 什么是 CRL？
CRL 是由 CA 签署的已吊销证书序列号列表。客户端下载 CRL 并检查证书的序列号是否出现在其中。

### 每个 CA 的 CRL
每个 CA 都有自己的 CRL。CRL 列表显示所有 CA 及：
- **已吊销数量** — CRL 中的证书数量
- **上次重新生成** — CRL 最后一次重建的时间
- **自动重新生成** — 是否启用了自动 CRL 更新

### 重新生成 CRL
点击**重新生成**可立即重建 CA 的 CRL。这在吊销证书后非常有用。

### 自动重新生成
启用自动重新生成可在每次吊销证书时自动重建 CRL。可按 CA 切换此设置。

### CRL 分发点（CDP）
CDP URL 嵌入在证书中，以便客户端知道从何处下载 CRL。可从 CRL 详情中复制 URL。

\`\`\`
http://your-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **自动启用**：创建新 CA 时，如果已配置协议基础 URL 或 HTTP 协议服务器，CDP 将自动启用。CDP URL 会自动生成——无需手动操作。

> ⚠️ **重要**：URL 使用 HTTP 协议端口和服务器 FQDN 自动生成。如果您通过 \`localhost\` 访问 UCM，将无法生成 URL。请先在设置 → 通用中配置您的 **FQDN** 或**协议基础 URL**。

### 下载 CRL
以 DER 或 PEM 格式下载 CRL，用于分发给客户端或与其他系统集成。

## OCSP 响应器

### 什么是 OCSP？
OCSP 提供实时证书状态检查。客户端无需下载整个 CRL，而是针对特定证书发送查询并立即获得响应。

### OCSP 状态
OCSP 部分显示：
- **响应器状态** — 每个 CA 的活动或非活动状态
- **总查询数** — 已处理的 OCSP 请求数量
- **缓存** — 响应缓存，自动每日清理过期条目

### OCSP 缓存

UCM 缓存 OCSP 响应以提高性能。缓存：
- **自动清理** — 调度程序每日清除过期响应
- **吊销时失效** — 证书被吊销时，其缓存的 OCSP 响应会立即清除
- **解除挂起时失效** — 取消证书挂起时，OCSP 缓存会更新

### AIA URL
颁发机构信息访问（AIA）扩展嵌入在证书中，告诉客户端在哪里可以找到：

**OCSP 响应器** — 实时吊销检查：
\`\`\`
http://your-server:8080/ocsp
\`\`\`

**CA 签发者**（RFC 5280 §4.2.2.1）— 下载签发 CA 证书以构建链：
\`\`\`
http://your-server:8080/ca/{ca_refid}.cer   (DER 格式)
http://your-server:8080/ca/{ca_refid}.pem   (PEM 格式)
\`\`\`

在详情面板的 **AIA CA 签发者**部分中按 CA 启用。URL 使用 HTTP 协议服务器和配置的 FQDN 自动生成。

> ⚠️ **前提条件**：协议 URL（CDP、OCSP、AIA）需要有效的 **FQDN** 或在设置 → 通用中配置的**协议基础 URL**。如果您通过 \`localhost\` 访问 UCM，启用这些功能将失败——请先设置 FQDN。

### OCSP 与 CRL 对比

| 特性 | CRL | OCSP |
|---------|-----|------|
| 更新频率 | 周期性 | 实时 |
| 带宽 | 每次完整列表 | 单次查询 |
| 隐私 | 无跟踪 | 服务器可见查询 |
| 离线支持 | 是（已缓存） | 需要网络连接 |

> 💡 最佳实践：同时启用 CRL 和 OCSP 以获得最大兼容性。
`
  }
}
