export default {
  helpContent: {
    title: 'SSH证书颁发机构',
    subtitle: '管理用于用户和主机认证的SSH CA',
    overview: '按照OpenSSH标准创建和管理SSH证书颁发机构。SSH CA消除了分发单独公钥的需要——服务器和用户信任CA，由CA签发证书来授予访问权限。',
    sections: [
      {
        title: 'CA类型',
        items: [
          { label: 'User CA', text: '签发用于SSH登录的用户证书。服务器信任此CA并接受其签发的任何证书。' },
          { label: 'Host CA', text: '签发用于证明服务器身份的主机证书。客户端信任此CA以验证连接的是正确的服务器。' },
        ]
      },
      {
        title: '密钥算法',
        items: [
          { label: 'Ed25519', text: '现代、快速、密钥小巧（256位）。推荐用于新部署。' },
          { label: 'ECDSA P-256 / P-384', text: '椭圆曲线密钥，广泛支持。安全性和兼容性的良好平衡。' },
          { label: 'RSA 2048 / 4096', text: '传统算法。长期CA请使用4096位。与旧系统的兼容性最广。' },
        ]
      },
      {
        title: '服务器配置',
        items: [
          { label: '配置脚本', text: '下载一个POSIX shell脚本，自动配置sshd以信任此CA。支持所有主流Linux发行版。' },
          { label: '手动配置', text: '复制CA公钥，在sshd_config中添加TrustedUserCAKeys（User CA）或HostCertificate（Host CA）。' },
        ]
      },
      {
        title: '密钥吊销',
        items: [
          { label: 'KRL (Key Revocation List)', text: '用于吊销单个证书的紧凑二进制格式。通过sshd_config中的RevokedKeys配置。' },
          { label: '下载KRL', text: '从CA详情面板下载当前的KRL文件。' },
        ]
      },
    ],
    tips: [
      '用户证书和主机证书使用单独的CA——切勿混用。',
      '由于速度和安全性，Ed25519是新部署的推荐选择。',
      '下载配置脚本可轻松配置服务器——它会自动处理备份和验证。',
    ],
    warnings: [
      '删除CA不会吊销其签发的证书——请先吊销证书或更新服务器信任设置。',
      '如果CA私钥被泄露，其签发的所有证书都必须视为不可信。',
    ],
  },
  helpGuides: {
    title: 'SSH证书颁发机构',
    content: `
## 概述

SSH证书颁发机构（CA）是SSH证书认证的基础。无需将单独的公钥分发到每台服务器，只需创建一个CA并配置服务器信任它。CA签发的任何证书都会被自动接受。

UCM支持OpenSSH证书格式（RFC 4253 + OpenSSH扩展），OpenSSH 5.4+原生支持——服务器和客户端无需安装额外软件。

## CA类型

### User CA
User CA签发用于**将用户认证到服务器**的证书。当服务器信任User CA时，持有该CA签发的有效证书的用户即可登录（取决于principal匹配）。

**服务器配置：**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Host CA签发用于**将服务器认证到客户端**的证书。当客户端信任Host CA时，可以验证所连接服务器的合法性——消除"Trust On First Use"（TOFU）警告。

**客户端配置：**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## 创建CA

1. 点击**创建SSH CA**
2. 输入描述性名称（例如："Production User CA"）
3. 选择CA类型：**User**或**Host**
4. 选择密钥算法：
   - **Ed25519** — 推荐。快速、密钥小巧、现代安全性。
   - **ECDSA P-256/P-384** — 良好的兼容性和安全性。
   - **RSA 2048/4096** — 最广泛的兼容性，密钥较大。
5. 可选设置最大有效期和默认扩展
6. 点击**创建**

> 💡 用户证书和主机证书使用单独的CA。切勿将一个CA用于两种用途。

## 服务器设置

### 自动配置脚本

UCM生成一个POSIX shell脚本，自动配置您的服务器：

1. 打开CA详情面板
2. 点击**下载配置脚本**
3. 将脚本传输到您的服务器
4. 运行：

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

该脚本：
- 检测操作系统和初始化系统
- 在修改前备份sshd_config
- 安装CA公钥
- 添加TrustedUserCAKeys（User CA）或HostCertificate（Host CA）
- 使用\`sshd -t\`验证配置
- 仅在验证通过后重启sshd
- 支持\`--dry-run\`预览更改

### 手动设置

#### User CA
\`\`\`bash
# 将CA公钥复制到服务器
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# 添加到sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# 重启sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# 签名服务器的主机密钥
# 然后添加到sshd_config：
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## 密钥吊销列表（KRL）

SSH CA支持Key Revocation List来使被泄露的证书失效：

1. 在SSH证书页面吊销证书
2. 从CA详情面板下载更新的KRL
3. 将KRL文件部署到服务器：

\`\`\`bash
# 添加到sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ 服务器必须配置为检查KRL。在KRL部署之前，吊销不会生效。

## 最佳实践

| 实践 | 建议 |
|----------|---------------|
| 分离CA | 用户证书和主机证书使用不同的CA |
| 密钥算法 | 新部署使用Ed25519，旧版兼容使用RSA 4096 |
| CA有效期 | 保持CA长期有效；改用短期证书 |
| 备份 | 导出并安全存储CA私钥 |
| Principal映射 | 将principal映射到具体用户名，而非通配符 |
`
  }
}
