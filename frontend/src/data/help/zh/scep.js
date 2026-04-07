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
          { label: '配置', text: 'SCEP 服务器设置：CA 选择、CA 标识符、自动批准' },
          { label: '质询密码', text: '管理每个 CA 的设备注册质询密码' },
          { label: '信息', text: 'SCEP 端点 URL 和集成说明' },
        ]
      },
      {
        title: '配置',
        items: [
          { label: '签名 CA', text: '选择哪个 CA 签署 SCEP 注册的证书' },
          { label: '自动批准', text: '自动批准带有有效质询密码的请求' },
          { label: '质询密码', text: '设备用于认证注册的共享密钥' },
        ]
      },
    ],
    tips: [
      '为每个 CA 使用唯一的质询密码以提高安全审计能力',
      '自动批准很方便，但在高安全环境中建议手动审核请求',
      'SCEP URL 格式：https://your-server:port/scep',
    ],
    warnings: [
      '质询密码在 SCEP 请求中传输——请使用 HTTPS 保证传输安全',
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
- **待处理** — 等待审批的请求
- **已批准** — 已批准并已签发证书的请求
- **已拒绝** — 已拒绝的请求

### 配置
配置 SCEP 服务器设置：
- **签名 CA** — 选择哪个 CA 签署证书
- **CA 标识符** — SCEP CA 标识符字符串
- **自动批准** — 启用/禁用带有有效质询密码的请求的自动批准

### 质询密码
管理用于设备注册认证的质询密码：
- 每个 CA 可以有自己的质询密码
- 密码在设备注册配置文件中配置

### 信息
查看 SCEP 端点 URL 和集成说明。

## SCEP 注册流程

1. 管理员在 UCM 中配置 SCEP（CA、质询密码）
2. 设备使用 SCEP URL 和质询密码配置
3. 设备生成密钥对和 CSR
4. 设备将 CSR 和质询密码发送到 UCM
5. UCM 验证质询密码并签署证书（如果启用自动批准）
6. 设备接收并安装证书

## SCEP URL

\`\`\`
https://your-server:8443/scep
\`\`\`

设备使用此 URL 作为 SCEP 服务器地址。

## 批准/拒绝请求

如果未启用自动批准：
1. 前往**请求**选项卡
2. 查看待处理的请求
3. 检查主题、密钥类型和质询
4. 点击**批准**或**拒绝**

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

### Microsoft Intune / JAMF
在 MDM 配置文件中配置 SCEP URL、质询密码和证书主题。MDM 平台会自动处理注册。

> 💡 SCEP 是传统协议。对于新部署，如果设备支持，建议优先使用 EST。
`
  }
}
