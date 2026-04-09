export default {
  helpContent: {
    title: 'SSH证书',
    subtitle: '签发和管理OpenSSH证书',
    overview: '签发由SSH CA签名的SSH证书。证书取代手动管理authorized_keys的方式，提供有时间限制、按principal范围划分且自动过期的访问控制。支持用户证书和主机证书。',
    sections: [
      {
        title: '签发模式',
        items: [
          { label: '签名模式', text: '粘贴现有的SSH公钥进行签名。私钥保留在用户机器上——UCM从不接触私钥。' },
          { label: '生成模式', text: 'UCM生成新的密钥对并签名证书。请立即下载私钥——之后无法再获取。' },
        ]
      },
      {
        title: '证书字段',
        items: [
          { label: 'Key ID', text: '证书的唯一标识符。出现在SSH日志中用于审计。' },
          { label: 'Principals', text: '此证书有效的用户名（用户证书）或主机名（主机证书）。以逗号分隔。' },
          { label: '有效期', text: '证书的生命周期。选择预设（1h、8h、24h、7d、30d、90d、365d）或设置自定义秒数。' },
          { label: 'Extensions', text: 'SSH扩展，如permit-pty、permit-agent-forwarding。仅适用于用户证书。' },
          { label: 'Critical Options', text: '如force-command或source-address等限制，用于约束证书的使用范围。' },
        ]
      },
      {
        title: '证书类型',
        items: [
          { label: '用户证书', text: '向服务器认证用户身份。服务器必须通过TrustedUserCAKeys信任签名CA。' },
          { label: '主机证书', text: '向客户端认证服务器身份。客户端通过known_hosts中的@cert-authority信任CA。' },
        ]
      },
      {
        title: '管理',
        items: [
          { label: '吊销', text: '将证书添加到CA的Key Revocation List（KRL）中。服务器必须配置为检查KRL。' },
          { label: '下载', text: '下载证书、公钥或私钥（仅生成模式）。' },
        ]
      },
    ],
    tips: [
      '使用短期证书（8h–24h）进行用户访问，以最大限度减少密钥泄露的影响。',
      '建议使用签名模式——用户的私钥永远不会离开其机器。',
      'Key ID应具有描述性（例如"jdoe-prod-2025"），便于日志审计。',
      '对于主机证书，principal必须与客户端连接使用的主机名匹配。',
    ],
    warnings: [
      '在生成模式下，请立即下载私钥——私钥不会被存储，也无法恢复。',
      '证书吊销仅在服务器配置为检查CA的KRL文件时才有效。',
    ],
  },
  helpGuides: {
    title: 'SSH证书',
    content: `
## 概述

SSH证书是带有元数据的签名SSH公钥：身份、有效期、允许的principals和扩展。它们用集中化、有时间限制、可审计的访问控制取代了传统的\`authorized_keys\`方式。

UCM签发OpenSSH格式的证书，兼容任何平台上的OpenSSH 5.4+。

## 签发模式

### 签名模式（推荐）
用户自行生成密钥对，仅向UCM提供**公钥**。私钥永远不会离开用户的机器。

**用户工作流程：**
\`\`\`bash
# 1. 生成密钥对（用户机器上）
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. 复制公钥内容
cat ~/.ssh/id_work.pub

# 3. 粘贴到UCM的签名表单中
# 4. 下载签名后的证书
# 5. 保存为 ~/.ssh/id_work-cert.pub

# 6. 连接
ssh -i ~/.ssh/id_work user@server
\`\`\`

### 生成模式
UCM同时生成密钥对和证书。当需要集中配置凭据时使用。

> ⚠ **请立即下载私钥** —— 私钥不会存储在UCM中，无法恢复。

**工作流程：**
1. 选择CA并填写证书详情
2. 选择"生成"模式
3. 点击**签发**
4. 下载全部三个文件：
   - 私钥（\`keyid\`）—— **请安全保管！**
   - 证书（\`keyid-cert.pub\`）
   - 公钥（\`keyid.pub\`）

## 证书字段

### Key ID
嵌入证书中的唯一标识符。当证书被使用时，它会出现在SSH服务器日志中，对于审计至关重要。

**良好的Key ID示例：** \`jdoe-prod-2025\`、\`webserver-01\`、\`deploy-ci-pipeline\`

### Principals
Principals定义证书对**谁**（用户证书）或**什么**（主机证书）有效：

- **用户证书**：持有者可以登录的用户名列表（例如：\`deploy\`、\`admin\`）
- **主机证书**：服务器已知的主机名/IP列表（例如：\`web01.example.com\`、\`10.0.1.5\`）

> 💡 如果未指定principals，证书对任何principal有效——这通常权限过大。

### 有效期

选择预设或设置自定义时长：

| 预设 | 使用场景 |
|--------|----------|
| 1小时 | CI/CD流水线、一次性任务 |
| 8小时 | 标准工作日访问 |
| 24小时 | 延长访问 |
| 7天 | 迭代周期访问 |
| 30天 | 月度轮换 |
| 365天 | 长期服务账户 |

建议人工用户使用短期证书（8h–24h）。自动化服务账户可接受更长的有效期。

### Extensions（仅用户证书）

| Extension | 说明 |
|-----------|-------------|
| permit-pty | 允许交互式终端会话 |
| permit-agent-forwarding | 允许SSH代理转发 |
| permit-X11-forwarding | 允许X11显示转发 |
| permit-port-forwarding | 允许TCP端口转发 |
| permit-user-rc | 允许登录时执行~/.ssh/rc |

### Critical Options

| 选项 | 说明 |
|--------|-------------|
| force-command | 将证书限制为单个命令 |
| source-address | 限制为特定的源IP地址/CIDR |

**示例：** 配置了\`force-command=ls\`和\`source-address=10.0.0.0/8\`的证书只能执行\`ls\`，且只能从10.x.x.x网络执行。

## 使用证书

### 用户证书
\`\`\`bash
# 将证书放在私钥旁边
# 如果密钥是 ~/.ssh/id_work，证书必须是 ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH自动使用证书
ssh user@server
\`\`\`

### 主机证书
\`\`\`bash
# 在服务器上：放置主机证书
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# 添加到sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

在客户端，将Host CA添加到known_hosts：
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## 吊销

1. 在表格中选择证书
2. 在详情面板中点击**吊销**
3. 证书被添加到CA的Key Revocation List（KRL）
4. 从SSH CA页面下载并部署更新的KRL到服务器

> ⚠ 吊销仅在服务器通过sshd_config中的\`RevokedKeys\`检查KRL时生效。

## 故障排除

| 问题 | 解决方案 |
|-------|----------|
| Permission denied (publickey) | 验证服务器上CA是否受信任（TrustedUserCAKeys） |
| 证书未被使用 | 确保证书文件命名为\`<key>-cert.pub\`并位于私钥旁边 |
| Principal不匹配 | SSH使用的用户名必须在证书的principals中列出 |
| 证书已过期 | 使用适当的有效期签发新证书 |
| 主机验证失败 | 在known_hosts中使用@cert-authority添加Host CA |
`
  }
}
