export default {
  helpContent: {
    title: '设置',
    subtitle: '系统配置',
    overview: '配置 UCM 系统的各个方面。设置按类别组织：通用、外观、电子邮件、安全、SSO、备份、审计、数据库、HTTPS、更新和 Webhook。',
    sections: [
      {
        title: "Prometheus 指标",
        content: "可选的 /metrics 端点，以 Prometheus 格式公开计数器（证书、CA、调度器、Webhook、ACME）。",
        items: [
          { label: "启用", text: "在设置 › 常规中设置指标令牌；未设置令牌时端点返回 404（禁用）" },
          { label: "认证", text: "使用 Authorization: Bearer <令牌> 抓取" },
          { label: "计数器", text: "ucm_certificates、ucm_certificate_authorities、ucm_scheduler_task_*、ucm_webhook_deliveries、ucm_acme_*" },
        ]
      },
      {
        title: "公共 ACME vhost",
        content: "设置 › 常规：反向代理后 ACME 目录 URL 的公共主机名和端口。",
        items: [
          { label: "管理", text: "admin.ucm.example.com — GUI 和 API（按策略 mTLS）" },
          { label: "ACME", text: "acme.ucm.example.com — /acme/* 和 /acme/proxy/*（无客户端 mTLS）" },
          { label: "通配符 TLS", text: "具体主机名（如 acme.ucm.example.com）。证书 SAN *.ucm.example.com 覆盖 admin/ACME 的 TLS — 不可将 *.ucm.example.com 填为 vhost" },
          { label: "保存之前", text: "先确保 ACME vhost 的 DNS 和 TLS 正常工作——重新读取 directory 的客户端会立即切换 URL，若 vhost 不可达，续期将失败" },
          { label: "TLS 证书 ID", text: "部署在 ACME vhost 上的证书元数据（如通配符）" },
        ]
      },
      {
        title: "Webhook 投递历史",
        content: "每个 Webhook 端点都保留一份投递日志，包含状态、尝试次数和手动重试。",
        items: [
          { label: "状态", text: "pending / delivered / failed，附带最后的 HTTP 代码和错误" },
          { label: "重试", text: "手动将失败或已投递的事件重新入队" },
          { label: "异步", text: "投递来自持久队列，采用指数退避（最多 5 次尝试）" },
        ]
      },
      {
        title: "调度器视图",
        content: "设置 › 系统列出后台任务及其状态和上次运行。",
        items: [
          { label: "任务", text: "到期检查、CRL 刷新、Webhook 投递、计划备份、自动续期等" },
          { label: "立即运行", text: "按需触发任何任务" },
          { label: "可见性", text: "每个任务的上次运行、上次耗时和失败次数" },
        ]
      },
      {
        title: "计划备份",
        content: "按可配置频率对数据库进行自动加密备份，并带有保留策略。",
        items: [
          { label: "频率", text: "每日 / 每周 / 每月" },
          { label: "保留", text: "保留最近 N 个备份；较旧的会被清理" },
          { label: "加密", text: "备份使用配置的备份密码加密" },
        ]
      },
      {
        title: '自动更新（v2.215）',
        content: '设置 › 更新：每日后台检查新版本，并可选启用无人值守安装。',
        items: [
          { label: "通道", text: "“稳定版”仅跟随正式发布；“候选发布版”额外仅接受 rcN 版本——绝不包含 alpha/beta" },
          { label: '通知', text: '发现新版本时触发 system.update_available Webhook/邮件事件，每个版本仅一次' },
          { label: '自动安装', text: '默认关闭。启用后，UCM 会在选定的时间下载、验证并安装更新，然后重启——仅限 DEB/RPM 安装' },
          { label: '校验和', text: '无人值守安装要求发布版提供已公布的 SHA256 用于验证；手动安装在有校验和公布时也会进行验证' },
          { label: 'Docker', text: '容器无法自行更新——检查和通知仍然有效；请拉取新镜像来完成更新' },
          { label: '更新后弹窗', text: '可选（v2.217）：更新安装后按用户显示一次版本说明。默认关闭' },
        ]
      },
      {
        title: "HSTS（Strict Transport Security）",
        content: "可由操作员配置的 HSTS 策略，以便在初始设置期间使用自签名证书的实例可以完全退出。",
        items: [
          { label: "默认", text: "HSTS 开启，includeSubDomains，max-age 1 年（向后兼容）" },
          { label: "禁用", text: "对于在初始设置期间使用自签名证书的实例，请禁用（避免浏览器锁定）" },
          { label: "环境变量", text: "/etc/ucm/ucm.env 中的 UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE 优先于数据库" },
          { label: "子域名", text: "当子域名托管具有各自证书的独立服务时，移除 includeSubDomains" },
        ]
      },
      {
        title: '类别',
        items: [
          { label: '通用', text: '实例名称、主机名和全系统默认值' },
          { label: '外观', text: '主题选择（亮色/暗色/系统）、强调色、桌面模式' },
          { label: '电子邮件 (SMTP)', text: 'SMTP 服务器、凭据、邮件模板编辑器和到期提醒通知。除传统密码认证外，还支持 Gmail、Outlook.com 和 Microsoft 365 的 OAuth2 (XOAUTH2)' },
          { label: '安全', text: '密码策略、会话超时、频率限制、IP 限制' },
          { label: 'SSO', text: 'SAML 2.0、OAuth2/OIDC 和 LDAP 单点登录集成' },
          { label: '备份', text: '手动和计划的数据库备份' },
          { label: '审计', text: '日志保留、syslog 转发、完整性验证' },
          { label: '数据库', text: '活动后端（SQLite 或 PostgreSQL）、大小、表数量、在后端之间测试/切换/迁移' },
          { label: 'HTTPS', text: 'UCM Web 界面的 TLS 证书。已应用的证书会被记住，并在其续期后自动重新应用（v2.217）；界面会显示当前绑定的证书及一个解除绑定按钮，用于停止跟随续期（v2.218）' },
          { label: '更新', text: '检查新版本、查看变更日志、每日计划检查并可选启用无人值守安装（DEB/RPM）' },
          { label: 'Webhook', text: '证书事件（签发、吊销、过期）的 HTTP Webhook — 允许内部 LAN URL；阻止云元数据 IP。可选出站认证：Bearer、Basic、API 密钥或自定义标头' },
          { label: '部署', text: '部署目标：在签发和续期时通过 SSH/SFTP 将证书推送到的远程主机，并附带一条固定的重载命令（仅管理员，v2.215）' },
          { label: 'Active Directory', text: 'UCM 自身的 AD/LDAP 连接，用于与证书相关的查询（Kerberos 主体解析、AD 派生主题）' },
          { label: 'Windows 自动注册', text: 'MS-XCEP/MS-WSTEP 原生 Windows 注册：策略发现、证书签发和 Kerberos/SPNEGO 绑定' },
        ]
      },
      {
        title: '部署钩子（v2.215）',
        content: '设置 › 部署（仅管理员）：UCM 通过 SFTP 将证书推送到的远程主机，随后通过 SSH 运行一条固定的重载命令。',
        items: [
          { label: '目标', text: '主机、端口、SSH 用户。UCM 会生成一个 ed25519 密钥（将显示的公钥安装到目标主机上），也接受导入的私钥 —— 均加密存储' },
          { label: '主机密钥', text: '在首次成功连接时固定（首次使用即信任，TOFU）；此后任何变化都会直接导致连接失败。更改主机后会重新固定' },
          { label: '重载命令', text: '推送成功后运行的一条由管理员定义的固定命令（例如 systemctl reload nginx）—— exit 0 即成功，不支持模板' },
          { label: '绑定', text: '在证书详情视图中将证书关联到目标，并为每个文件指定目标路径' },
          { label: '投递', text: '推送通过带重试和退避的持久队列异步执行；提供每次投递的状态、手动"立即部署"和重试，以及完整的审计记录' },
          { label: '最小权限', text: '在每台目标主机上使用专用 SSH 账户：仅具备证书路径的写入权限和重载服务的权限，别无其他' },
        ]
      },
      {
        title: 'SMTP OAuth2(XOAUTH2)',
        content: '用于发送邮件的现代 OAuth2 认证,替代 Microsoft 和 Google 正在弃用的旧式应用密码流程:',
        items: [
          { label: 'Gmail', text: '配置具有 https://mail.google.com/ 范围的 Google Cloud OAuth2 客户端' },
          { label: 'Microsoft 365 / Outlook.com', text: '注册具有 SMTP.Send 委派权限的 Azure AD 应用' },
          { label: '刷新令牌', text: 'UCM 存储刷新令牌并在每次发送前自动续订访问令牌' },
          { label: '回退', text: '未配置 OAuth2 时,密码认证仍受支持' },
        ]
      },
      {
        title: 'Active Directory 连接器',
        content: 'UCM 自身与 Active Directory 的 LDAP 连接，独立于在 SSO 下配置的任何 LDAP 提供程序 —— 后者用于登录 UCM，前者用于与证书相关的 AD 查询。',
        items: [
          { label: '用途', text: '将 Kerberos 计算机或用户主体解析为其 AD 对象，以便 UCM 能像真实 Windows CA 一样派生证书主题/SAN' },
          { label: '字段', text: '服务器、端口、可选 CA 验证的 LDAPS、Base DN、Bind DN/密码' },
          { label: '测试连接', text: '保存前验证连通性和凭据' },
          { label: 'GPO 注册 URL', text: '要在组策略中注册的 Kerberos 和用户名/密码证书注册策略 URL' },
        ]
      },
      {
        title: 'Windows 自动注册（XCEP/WSTEP）',
        content: '通过 MS-XCEP 策略发现和 MS-WSTEP 签发实现的原生 Windows 证书注册 —— 支持 MMC/certreq 手动注册和无人值守的 GPO 自动注册。',
        items: [
          { label: 'XCEP', text: '使 Windows 客户端能够在注册前发现可用的证书模板' },
          { label: 'WSTEP', text: '在发现策略后处理证书请求和续订' },
          { label: 'Kerberos/SPNEGO', text: '绑定用于静默 GPO 自动注册的 Kerberos 身份验证端点（需要来自域控制器的 SPN 和 keytab）' },
          { label: '设置清单', text: '该标签页会实时显示手动和无人值守注册所需的已配置项与待配置项' },
          { label: 'AD 派生主题', text: '模板可以选择通过 AD 连接器从 Active Directory 派生其主题/SAN，用于无人值守注册' },
        ]
      },
      {
        title: '自动续期',
        items: [
          { label: '来源', text: '调度器续期服务器持有其私钥的证书：默认为通过表单或签署请求签发的证书（"manual"），以及使用服务器生成密钥的 SCEP、ACME 和 EST 注册。自行持有密钥的设备通过其协议续期' },
          { label: '等待审批', text: '续期已排队等待审批的证书会交由该决定处理，前提是决定能在证书到期前作出' },
          { label: '期间已续期', text: '操作员在本批次运行期间已续期的证书不会被再次续期；批次期间被删除的证书会被跳过' },
        ]
      },

    ],
    tips: [
      '使用顶部的系统状态组件快速检查服务健康状况',
      '在依赖邮件通知前先测试 SMTP 设置',
      '使用内置的 HTML/文本编辑器自定义包含品牌标识的邮件模板',
      '为生产环境安排自动备份',
      'SQLite ↔ PostgreSQL 切换是双向的 — UI 在迁移前执行安全检查(驱动已加载、目标可达、目标为空)',
    ],
    warnings: [
      '更改 HTTPS 证书需要重启服务',
      '修改安全设置可能会锁定用户——保存前请验证访问权限',
    ],
  },
  helpGuides: {
    title: '设置',
    content: `
## 概述

按选项卡组织的全系统配置。除非另有说明，更改会立即生效。

## 通用

- **实例名称** — 显示在浏览器标题和邮件中
- **主机名** — 服务器的完全限定域名
- **默认有效期** — 默认证书有效期（天数）
- **到期警告阈值** — 触发警告的到期前天数
- **公共 ACME vhost** — ACME 目录 URL 中的具体主机名（例如 \`acme.ucm.example.com\`，而不是 \`*.ucm.example.com\`）。通配符 \`*.ucm.example.com\` **TLS 证书 SAN** 可同时覆盖 \`admin.ucm.example.com\` 和 \`acme.ucm.example.com\`。请在保存**之前**为 ACME vhost 配置好 DNS 和 TLS——重新读取目录的客户端会立即切换 URL。

## 外观

- **主题** — 亮色、暗色或系统（跟随操作系统偏好）
- **强调色** — 按钮、链接和高亮使用的主色
- **强制桌面模式** — 禁用响应式移动布局
- **侧边栏行为** — 默认折叠或展开

## 电子邮件 (SMTP)

配置 SMTP 用于邮件通知（到期提醒、用户邀请）：
- **SMTP 主机**和**端口**
- **用户名**和**密码**
- **加密** — 无、STARTTLS 或 SSL/TLS
- **发件人地址** — 发送者邮箱地址
- **内容类型** — HTML、纯文本或两者
- **提醒收件人** — 使用标签输入添加多个收件人

点击**测试**发送测试邮件以验证配置。

### 邮件模板编辑器

点击**编辑模板**打开浮动窗口中的分屏模板编辑器：
- **HTML 选项卡** — 编辑 HTML 邮件模板，右侧实时预览
- **纯文本选项卡** — 编辑不支持 HTML 的邮件客户端的纯文本版本
- 可用变量：\`{{title}}\`、\`{{content}}\`、\`{{datetime}}\`、\`{{instance_url}}\`、\`{{logo}}\`、\`{{title_color}}\`
- 点击**恢复默认**以恢复内置的 UCM 品牌模板
- 窗口可调整大小和拖动，方便编辑

### 到期提醒

配置 SMTP 后，启用自动证书到期提醒：
- 开/关切换提醒
- 选择警告阈值（90天、60天、30天、14天、7天、3天、1天）
- 运行**立即检查**触发即时扫描

## 安全

### 密码策略
- 最小长度（8-32 个字符）
- 要求大写字母、小写字母、数字、特殊字符
- 密码过期（天数）
- 密码历史记录（防止重复使用）

### 会话管理
- 会话超时（不活动分钟数）
- 每用户最大并发会话数

### 频率限制
- 每 IP 的登录尝试限制
- 超过限制后的封锁时长

### IP 限制
允许或拒绝来自特定 IP 地址或 CIDR 范围的访问。

### 2FA 强制
要求所有用户启用双因素认证。

### 私钥加密
使用 AES-256 加密数据库中存储的所有私钥，由主密钥文件保护。该部分显示加密状态以及**已加密 / 未加密**密钥计数器。两个可选启用的环境变量可使缺失密钥在启动时直接失败：\`UCM_REQUIRE_DB_ENCRYPTION_KEY\`（集成密钥加密）和 \`UCM_REQUIRE_KEY_ENCRYPTION\`（私钥加密）。

> 💡 安全敏感设置（会话、锁定、HSTS、公共 URL、密码策略）需要 **admin:settings** 权限——这些字段对操作员锁定。

> ⚠ 应用 IP 限制前请仔细测试。不正确的规则可能会锁定所有用户。

## SSO（单点登录）

### SAML 2.0
- 向您的 IDP 提供 **SP 元数据 URL**：\`/api/v2/sso/saml/metadata\`
- 或手动配置：上传/链接 IDP 元数据 XML、配置 Entity ID 和 ACS URL
- 将 IDP 属性映射到 UCM 用户字段（用户名、邮箱、角色）

### OAuth2 / OIDC
- 授权 URL 和令牌 URL
- 客户端 ID 和客户端密钥
- 用户信息 URL（用于属性检索）
- 范围（openid、profile、email）
- 首次 SSO 登录时自动创建用户

### LDAP
- 服务器主机名、端口（389/636）、SSL 切换
- 绑定 DN 和密码（服务账户）
- 基础 DN 和用户筛选器
- 属性映射（用户名、邮箱、全名）

> 💡 始终保留一个本地管理员账户作为后备，以防 SSO 出现故障。

## 备份

### 手动备份
点击**创建备份**生成数据库快照。备份包括所有证书、CA、密钥、设置和审计日志。

### 计划备份
配置自动备份：
- 频率（每日、每周、每月）
- 保留数量（保留的备份数）

### 恢复
上传备份文件将 UCM 恢复到之前的状态。

> ⚠ 恢复备份将替换所有当前数据。

## 审计

- **日志保留** — 在 N 天后自动清理旧日志
- **Syslog 转发** — 将事件发送到远程 syslog 服务器（UDP/TCP/TLS）
- **完整性验证** — 启用哈希链进行篡改检测

## 数据库

UCM 支持两种数据库后端：

- **SQLite**（默认）— 基于文件，无需配置，适合单节点
- **PostgreSQL 13+** — 推荐用于高可用、多实例，或您已运行托管 PG 集群的场景

活动后端通过 \`DATABASE_URL\` 环境变量选择。如未设置，UCM 将使用位于 \`UCM_DATA_DIR/ucm.db\` 的 SQLite。

### 状态面板
- 活动后端（sqlite / postgresql）和驱动
- 数据库大小和表数量
- 迁移版本

### 测试连接
切换前验证 \`DATABASE_URL\`（例如 \`postgresql://user:pass@host:5432/ucm\`）。测试会打开真实连接并报告任何错误。 早于版本 13 的 PostgreSQL 服务器将被拒绝 — UCM 需要 PostgreSQL 13 或更高版本。

### 切换后端
将 \`DATABASE_URL\` 持久化到 \`/etc/ucm/ucm.env\`（DEB/RPM）并重启 UCM。**不会复制任何数据** — 如果您希望保留现有数据，请先使用**迁移**。

### 迁移数据
将所有行从当前后端复制到目标后端。支持双向（SQLite ↔ PostgreSQL）：

1. 源数据库会备份到 \`/opt/ucm/data/backups/db_migration/\`
2. 通过 SQLAlchemy 在目标上创建模式
3. 批量加载期间禁用 FK 约束
4. 源/目标列取交集（遗留列会被跳过并发出警告）
5. 加载后重置 PostgreSQL 序列
6. 服务自动重启（DEB/RPM）— Docker 上请在 compose 文件中设置 \`DATABASE_URL\` 并手动重启容器


**安全检查(快速失败,源未受影响):**
- 目标必须为空。如果 \`users\`、\`cas\` 或 \`certificates\` 中已经存在行,迁移将被拒绝并返回 HTTP 409,同时提供清理提示:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - SQLite: 删除目标 \`.db\` 文件
- 如果迁移中途失败,源保持不变,错误消息会指向源备份。在重试之前重置目标。

> ⚠ 在不同后端之间迁移之前，请始终执行完整的 UCM 备份（设置 → 备份）。

## HTTPS

管理 UCM Web 界面使用的 TLS 证书：
- 查看当前证书详情
- 导入新证书（PEM 或 PKCS#12）
- 生成自签名证书

> ⚠ 更改 HTTPS 证书需要重启服务。

## 更新

- 从 GitHub 发布检查新的 UCM 版本
- 查看可用更新的变更日志
- 当前版本和构建信息
- **自动更新**：在支持的安装（DEB/RPM）上，点击**立即更新**自动下载和安装最新版本
- **包含预发布版本**：切换以同时检查候选发布版本（rc）

## Webhook

配置 HTTP Webhook 在事件发生时通知外部系统：

### 支持的事件
- 证书签发、吊销、过期、续期
- CA 创建、删除
- 用户登录、登出
- 备份已创建

### 认证

可选出站认证（适用于可选 HMAC 签名之外）：

- **无** — 无认证标头（公开 Webhook）
- **Bearer** — \`Authorization: Bearer <令牌>\`
- **Basic** — \`Authorization: Basic <base64(用户:密码)>\`
- **API 密钥** — 自定义标头（如 \`X-Api-Key: <令牌>\`）
- **自定义** — \`Authorization: <方案> <令牌>\`（如 \`auth-key 值\`）

令牌以加密方式存储，不会在 UI 中返回。

### 创建 Webhook
1. 点击**添加 Webhook**
2. 输入 **URL**（必须是 HTTPS）
3. 选择要订阅的**事件**
4. 选择**认证类型**并提供凭据（可选）
5. 可选设置**密钥**用于 HMAC 签名验证
6. 点击**创建**

### 测试
点击**测试**向 Webhook URL 发送示例事件并验证其可达性。
## Prometheus 指标

可选、令牌保护的 **\`/metrics\`** 端点。

- 通过设置指标令牌启用（设置 › 常规）；无令牌 → 404
- 使用 \`Authorization: Bearer <令牌>\` 标头抓取
- 公开 \`ucm_certificates\`、\`ucm_certificate_authorities\`、\`ucm_scheduler_task_*\`、\`ucm_webhook_deliveries\`、\`ucm_acme_*\`

## Webhook 投递历史

在某个 Webhook 上打开历史（时钟图标）查看其投递。

- **pending / delivered / failed** 状态，附最后的 HTTP 代码和错误
- 手动**重试**投递
- 持久队列，采用指数退避（最多 5 次尝试）

## 调度器视图

设置 › 系统展示后台任务。

- 任务列表，含**状态**、**上次运行**、**耗时**和**失败次数**
- 对任意任务**立即运行**
- 涵盖到期、CRL、Webhook 投递、备份、自动续期……

## 自动续期
自动续期设置驱动续期调度器。
- **来源** — 调度器续期服务器持有其私钥的证书：默认为通过表单或签署请求签发的证书（"manual"），以及使用服务器生成密钥的 SCEP、ACME 和 EST 注册。自行持有密钥的设备通过其协议续期
- **等待审批** — 续期已排队等待审批的证书会交由该决定处理，前提是决定能在证书到期前作出
- **期间已续期** — 操作员在本批次运行期间已续期的证书不会被再次续期；批次期间被删除的证书会被跳过

## 计划备份

设置 › 备份可启用自动备份。

- **每日 / 每周 / 每月**频率
- **保留**：保留最近 N 个，清理较旧的
- 使用备份密码**加密**备份


## Active Directory 连接器

UCM 自身与 Active Directory 的 LDAP 连接，独立于在 SSO 下配置的任何 LDAP 提供程序。后者用于登录 UCM；前者用于与证书相关的 AD 查询，且无论是否配置了 SSO 均可独立工作。

- **用途** — 将 Kerberos 计算机或用户主体解析为其 AD 对象，以便 UCM 能像真实 Windows CA 一样派生证书主题/SAN
- **服务器** — 域控制器的主机名/IP 和端口
- **LDAPS** — 切换以通过 SSL/TLS 使用 LDAP；**验证 SSL 证书** 验证域控制器的证书（当证书不受公共信任时，可选地针对自定义 CA 证书包进行验证）
- **Base DN** 和 **Bind DN / 密码** — 用于查询的服务账户凭据
- **测试连接** — 保存前验证连通性和凭据

### GPO 注册策略 URL

配置完成后，在组策略中（公钥策略 → 证书服务客户端 – 证书注册策略）将其中一个显示的 URL 注册为证书注册策略服务器，并同时配置证书服务客户端 – 自动注册：
- **Kerberos** — 无需凭据提示；需要已加入域的客户端，并将 GPO 的身份验证类型设置为 Kerberos
- **用户名/密码** — 需要输入凭据；仅用于交互式的“申请新证书”注册

## Windows 自动注册（XCEP/WSTEP）

通过 **MS-XCEP**（策略发现）和 **MS-WSTEP**（证书签发和续订）实现的原生 Windows 证书注册 —— 与真实 ADCS 用于 MMC“申请新证书”、\`certreq\` 和无人值守 GPO 自动注册的协议相同。

### 设置清单

该标签页会跟踪手动和无人值守注册路径所需的已配置项与待配置项 —— 证书颁发机构、策略发现 (XCEP)、证书签发 (WSTEP)，以及针对无人值守 GPO 自动注册所需的 Active Directory 连接器、Kerberos/SPNEGO，以及至少一个允许自动注册的模板。

### 策略发现 (XCEP)

- **证书颁发机构** — 公布其模板并通过此配置签发证书的 CA
- **有效期（天）** — 应用于通过 WSTEP 签发的证书的默认有效期

### Kerberos / SPNEGO

绑定用于静默 GPO 自动注册的、经 Kerberos 身份验证的 XCEP/WSTEP 端点，使计算机和用户通过其 Kerberos 票证进行身份验证，而不是弹出凭据提示：
- **服务主体名称 (SPN)** — 例如 \`HTTP/ucm.example.com@EXAMPLE.COM\`
- **Keytab** — 在域控制器上使用 \`ktpass\` 或 \`ktutil\` 为上述 SPN 生成

> ⚠ 如果未安装服务器端 SPNEGO 库，即使在此处启用，Kerberos 身份验证也无法工作 —— 该标签页会显示警告。

### 注册策略 URL

- **用户名/密码** — 需要输入凭据；用于交互式的“申请新证书”注册，不需要 Active Directory
- **Kerberos** — 无需凭据提示；需要已加入域的客户端和 GPO 配置

### 证书续订绑定

除用户名/密码和 Kerberos 外，WSTEP 还支持**客户端证书续订**，与真实 ADCS CES 端点一致：续订请求 (RST) 必须使用 **UCM 自身签发**的证书的私钥进行 XML-DSig 签名。出示的证书会与所配置 CA 存储的证书进行**逐字节**比对——仅凭序列号或主题永远不够。这使 Windows 客户端可以使用其当前证书无人值守地续订，无需凭据或 Kerberos 票证。

### SID 安全扩展 (KB5014754)

在**经 Kerberos 身份验证的签发**中，UCM 会在签发证书的 Microsoft SID 安全扩展（\`szOID_NTDS_CA_SECURITY_EXT\`）中嵌入请求者的 AD SID。域控制器将其用于**强证书映射**（KB5014754）——自 AD 对基于证书的身份验证（智能卡登录、PKINIT）强制执行强映射以来，这是必需项。

### AD 派生主题

证书模板可以选择**从 Active Directory 构建主题**（模板 → 注册）：对于无人值守的 GPO 自动注册，主题和 SAN 通过 AD 连接器从请求者的 AD 对象派生，而不要求客户端提供 —— 与真实 ADCS 模板配置自动注册的方式一致。与此独立，**允许自动注册** 会在证书注册策略中将模板公布为 \`autoEnroll=true\`，使经 GPO/Kerberos 身份验证的客户端在登录时自动请求它。
`
  }
}
