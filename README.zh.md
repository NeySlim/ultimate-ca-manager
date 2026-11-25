# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** 是一个基于 Web 的证书颁发机构（CA）管理平台，支持 PKI 协议（ACME、SCEP、EST、OCSP、CRL/CDP），集成 Microsoft ADCS，提供多因素认证和证书全生命周期管理。

> **UCM 是一个年轻且持续积极开发的项目。** 欢迎提供反馈、错误报告和功能建议！请随时[提交 issue](https://github.com/NeySlim/ultimate-ca-manager/issues)：每一份报告都有助于让 UCM 变得更好。

> 最新变化请参阅[最新发布说明](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)和完整的 [CHANGELOG](CHANGELOG.md)。

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## 功能

### PKI 核心
- **CA 管理** -- 根 CA 与中间 CA、层级视图、导入/导出、**中间 CA 吊销**（上级的 CRL 和 OCSP，其下级显示"上游已吊销"状态）、**仅证书 CA**（由外部请求签发的 CA，私钥稍后导入）、**HSM 支持的签名密钥**（私钥不离开 HSM）、**可配置的 RFC 5280 配置文件**（签名摘要、密钥用途、EKU）、CA 可**从签发表单中隐藏**（仅用于签发中间 CA 的根），默认值与 Let's Encrypt 风格一致，并可选用 **RSA-PSS** 签名方案、与 ANSSI、BSI 及欧盟认可机制对齐的**合规配置文件**、**外部签名 CA**（UCM 生成密钥对和 CA 类型 CSR，由离线/外部根签名：私钥不离开 UCM，支持使用相同密钥的 CSR 续期）、**交叉签名 CA 证书**（在 CA 自身证书之外附加或交叉签名，根证书切换期间在默认证书链中提供，按导出或部署选择证书链，查看哪些仍链接到旧根）、创建时设置的 **RFC 5280 名称约束**（允许和排除的 DNS、IP 范围和电子邮件子树，在每条签发路径上强制执行）、有效期从 1 年或任意天数起，最长 50 年，以及可选的**唯一主体**规则（若某主体已被该 CA 下的其他实体使用，则在每条签发路径上拒绝签发该主体的证书，RFC 5280 §4.1.2.6）
- **证书生命周期** -- 签发、签名、吊销（使用 RFC 5280 原因码，可在每个吊销对话框中操作，也可批量吊销）、续期（**原位续期**：续期后 ID 保持稳定，被取代的序列号在 CRL/OCSP 中保留至其原到期日，所选有效期仍受策略上限约束）、重命名（可变的显示名称，涵盖无 CN 的证书）、导出（PEM、DER、PKCS#12（带有面向 Android 15 及更早版本、macOS 14 及更早版本、较旧 Windows 和 Java 的 3DES/SHA-1 兼容模式）以及 JKS；证书链默认省略自签名根，在打包或导入目标需要时可使用**包含根 CA** 选项）、批量操作、按状态 / 颁发者 / 来源（ACME、SCEP、EST、AD CS、导入……）筛选，包括因续期或重新注册而**归档**并保留作历史记录的条目
- **合规性检查（Linting）** -- 通过 pkilint（可用时还有 zlint）按证书检查是否符合 RFC 5280、CA/Browser Forum 基线要求和 ETSI EN 319 412，仅供参考
- **CSR 管理** -- 创建、导入、签署证书签名请求，支持**自定义额外 EKU OID**（RFC 5280 §4.2.1.12）、**带类型的 SAN 校验**（DNS / IP / Email / URI / UPN）、NIST P-256 / P-384 / P-521 和 Brainpool P256r1 / P384r1 / P512r1 曲线，以及**外部 CA 回传路径**：在其他地方为 UCM 中生成的 CSR 签发的证书，导入时会完成该 CSR 并保留其私钥；**签名时添加名称**（来自仅含 CN 的智能卡的 S/MIME 请求，其电子邮件地址在相同的名称约束、策略和审批下添加），以及从历史记录中**再次签名**，适用于无法两次生成请求的设备
- **证书模板** -- 面向服务器、客户端、代码签名、电子邮件、Windows 智能卡登录的预定义配置文件；密钥类型 RSA-2048/3072/4096、EC P-256/P-384/P-521、Brainpool 以及**后量子 ML-DSA-44/65/87**（CA 可用 Ed25519/Ed448）、**按 OID 的自定义 X.509 扩展**、**qcStatements（ETSI EN 319 412-5）和证书策略 OID**，以及预填到签发表单中的主体默认值（含电子邮件）；JSON 导出与导入保留所有设置，每个文件可包含一个或多个模板
- **证书发现** -- 网络扫描、扫描配置文件、计划扫描、证书导入
- **信任库** -- 管理受信任的根 CA 证书，支持到期告警和批量移除
- **证书链修复** -- 基于 AKI/SKI 的证书链验证，配有自动修复调度器
- **SSH 证书** -- SSH 证书颁发机构管理，签发主机/用户证书，导入 CA 和证书，对 curl 友好的设置脚本；密钥 ID 由 CA 命名（`principals@CA name`）或交由请求方决定

### 协议
- **ACME** -- RFC 8555、自动注册、自动续期、DNS-01/HTTP-01/TLS-ALPN-01 质询、通配符支持、**IP 标识符（RFC 8738）**、**带账户/方法绑定的 CAA 检查（RFC 8657/8659）**、**外部账户绑定（EAB，RFC 8555 §7.3.4）**、**续期信息（ARI，RFC 9773）**、**由 UCM 提供的 HTTP-01 质询文件**（从 80 端口转发 `/.well-known/acme-challenge/`，提交前检查，自动续期）、**DNS-01 解析器选择**（自动、仅系统、或仅限所列解析器，适用于无法访问公共解析器的网络）以支持 split-horizon、内部/私有 IP 上的 ACME（包括为同机部署的 CA 提供的可选回环上游）、**多 CA 管理**（按请求选择 CA，订单上固定 CA，使续期重用同一 CA：Let's Encrypt、Actalis、ZeroSSL、Google Trust Services、HARICA……）、**外部 CSR 与续期密钥重用**、**预发布环境预检演练**、**多 CA 代理**（已预先验证的上游域名直接通过，每个 CA 的端点位于 `/acme/proxy/<slug>/directory`，包括上游吊销）、**首选证书链**（RFC 8555 §7.4.2 备用链，按 CA 账户设置）、**证书配置文件**（draft-ietf-acme-profiles：在 directory 中公布并可按订单选择的命名签发策略，每个可选绑定到证书模板，由模板的密钥用途和 EKU 约束所签发的证书，另有**默认配置文件**以及针对未指定配置文件的订单的默认签名摘要）、**本地服务器订单管理**（订单视图，支持清理及定期清除过期订单）；代理还会发布客户端侧的 dns-01 TXT 值，使客户端的传播预检（lego、Traefik、Caddy）可直接通过，并在重试时重用账户仍处于待处理状态的订单；可选的 **DNS UPDATE（RFC 2136）监听器**允许 cert-manager 等标准 rfc2136 求解器通过代理完成 DNS-01，并按账户使用 TSIG 密钥
- **SCEP** -- RFC 8894 设备自动注册，带审批工作流、GetCert/GetCRL、已签名的 GetNextCACert，可选在纯 HTTP 端口上提供以支持 sscep 等客户端（FIPS 模式之外；FIPS 模式仅接受 RSA-OAEP 密钥传输）、由设备证书认证的续期、AES-128 加密，并为非 RSA 客户端提供基于口令（PBKDF2）的回退；手动批准的请求使用其所经配置文件的模板签发，与自动批准完全一致；命名配置文件可对照租户的 Intune API 验证 **Microsoft Intune** 质询，Windows（RSAES-OAEP 密钥传输）和 Apple 设备通过它们注册，参见 [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 安全传输注册，包括服务器端密钥生成（CMS §4.4）和 **CA 标签**（§3.2.2：通过一个端点提供多个 CA）
- **OCSP** -- RFC 6960 实时证书状态、多证书请求、nonce 支持、带响应方证书自动续期的委托响应方验证、可配置的响应有效期
- **TSA（RFC 3161）** -- 时间戳机构，可配置策略 OID；使用**专用的终端实体签名证书**签名（RFC 3161，默认要求，`openssl ts -verify` 和 jarsigner 等严格验证器也要求），可从已签发的证书中选择，或一键生成（关键、独占的 timeStamping EKU）；自动跟随续期、令牌中嵌入颁发者证书链、严格的专用签名者模式、签名者健康状况和到期信息显示在仪表板上
- **CRL/CDP** -- 证书吊销列表分发，支持 Delta CRL（RFC 5280 §5.2.4）、按 CA 的计划（有效期与发布频率解耦）和可配置的签名摘要、可选的命名 URL（CDP/AIA 路径中带 CA 名称 slug，可在现有 CA 上启用）、**为离线/无密钥 CA 上传外部签名的 CRL**（对照 CA 证书验证并检查 CRL 编号单调性，通过现有 CDP 端点提供并由 OCSP 查询）
- **AIA CA Issuers** -- 授权信息访问 CA 证书下载（RFC 5280 §4.2.2.1）

### 集成
- **Microsoft ADCS** -- 基于 AD CS 的完整生命周期：CSR 签名、模板发现、EOBO（代表他人注册）、通过连接器续期/吊销，以及可选的 WinRM 管理通道，用于 CRL 吊销同步、CA 清单导入、待处理请求的批准/拒绝，并带有 CA 健康面板
- **Windows 自动注册与 Active Directory 连接器** -- 为已加入域的计算机和用户提供 MS-XCEP/WSTEP 策略和注册，使用请求所指定的模板；在 Kerberos 绑定下，计算机模板和源自 AD 的模板从 Active Directory 获取主体（计算机的 DNS 主机名，或用户的 DN 和 UPN），支持多个域控制器及故障转移，并对每个 DC 进行计划健康检查，绝不使用匿名绑定；注册在**按 realm 划分的配置文件**（`/api/v2/windows-profiles`）中配置，每个配置文件有自己的 CA、模板、Kerberos keytab、AD 组和连接器；Kerberos 请求由其主体所属 realm 的已启用配置文件处理（UsernamePassword 绑定在默认配置文件启用时由其处理，基于证书绑定的续期由所出示证书上记录的配置文件处理），并支持**多个 Active Directory 连接器**（每个林或域一个）
- **Microsoft Intune** -- 为 Intune 托管设备验证 SCEP 质询，Entra 应用注册在 SCEP › Intune 应用注册中统一定义，并按配置文件选择，分步指南见 `docs/integrations/intune-scep.md`
- **HSM** -- 内置 SoftHSM、PKCS#11、Azure Key Vault、Google Cloud KMS、OpenBao/Vault Transit；带不可导出签名密钥的 **HSM 支持的 CA**、PKCS#11 上的 RSA-PSS 和 Brainpool，以及由欧盟合规配置文件检查的所声明设备认证（Common Criteria、EUCC、FIPS 140-3）；连接测试会显示 PKCS#11 模块报告的信息（库、制造商、固件）
- **Kubernetes / cert-manager** -- 位于 `examples/kubernetes/cert-manager/` 下的参考清单：ClusterIssuer（带 EAB 的 HTTP-01 + DNS-01）、示例 Certificate、Secret 模板
- **DNS 提供商** -- Cloudflare、Route53、Azure DNS、Plesk 等，用于 ACME DNS-01 质询
- **Webhooks** -- 针对证书生命周期事件的事件驱动通知（15+ 种事件类型）、**按端点的投递历史及手动重试**、带指数退避的持久化异步投递队列，以及历史记录的保留窗口，使其不会无限增长

### 安全与访问
- **认证** -- 密码、WebAuthn/FIDO2（也可作为第二因素，与 TOTP 并用或取代 TOTP）、TOTP 双因素认证、mTLS、API 密钥（`X-API-Key` 或 `Authorization: Bearer`）
- **SSO** -- LDAP（LDAPS 或 StartTLS）、OAuth2（Azure/Google/GitHub）、支持单点登出的 SAML 单点登录，角色映射到内置角色和**自定义角色**（从断言中读取 SAML 组，包含 Entra ID 和 AD FS 声明）以及可配置的 NameID 格式；**按用户跟踪 `auth_source`**，并可选在登录时同步角色
- **RBAC** -- 4 个内置角色（Admin、Operator、Auditor、Viewer）加上具有细粒度权限的自定义角色；**组可在用户角色之上授予额外权限**（绝不授予管理员权限）
- **策略与审批** -- 带审批工作流和强制规则（允许的密钥类型和签名哈希、DNS SAN 数量上限、有效期上限，可按 CA、模板或 DNS 模式限定范围）的证书签发策略，约束**每一条操作员路径**（签发表单、单独或批量签署已存储的请求、以及续期），并且对密钥类型和哈希而言，也约束 ACME、SCEP、EST、WSTEP 和 CA 创建；要求审批的策略会将 **ACME、EST、SCEP 和 WSTEP 请求**挂起在审批队列中，并以各协议自己的方式告知每个客户端（ACME `processing`、EST 202 加 Retry-After、SCEP PENDING、WSTEP pending）；策略还可将**吊销和续期**纳入审批；排队的请求在其目标期间被签署、续期、删除或吊销时会自动关闭
- **密钥与哈希默认值** -- 未指定密钥或哈希的请求在每条签发路径上都遵循同一个默认值（RSA-2048 配 SHA-256，除非配置文件或策略拒绝，此时取第一个被接受的类型），哈希跟随签名密钥，新的中间 CA 绝不会采用低于其上级的哈希
- **审计日志** -- 带完整性验证的操作日志、远程 syslog 转发以及可选的保留期限
- **私钥加密** -- 静态存储的 AES-128（Fernet、HMAC-SHA256），主密钥在首次启动时创建（在容器中，当 `/etc/ucm` 为卷时）或通过 `KEY_ENCRYPTION_KEY` 提供，涵盖 CA 和证书密钥、SSH CA 和部署目标密钥、ACME 账户和 EAB 密钥、SCEP 质询密码和 LDAP 绑定密码，并提供**加密剩余密钥**功能，用于处理启用加密之前存储的机密；启用加密后磁盘上不再保留明文密钥文件（启用时和启动时会移除现有的镜像文件，公共证书文件保留），禁用加密时会重新生成密钥文件
- **高可用** -- 使用 `UCM_HA=1` 在同一个 PostgreSQL 数据库上运行两个或更多节点（Docker、Docker Compose、DEB/RPM 或 Helm chart 的 `ha.enabled`）：由一个被选举的节点运行计划任务，设置、加密、备份和滚动更新会到达每个节点，会话共享，因此只有 Kerberos 注册端点需要源地址亲和性（参见 [docs/HA.md](docs/HA.md)）
- **FIPS 模式** -- `-fips` Docker 镜像在 OpenSSL FIPS Provider 3.5.9（CMVP 证书 #5586）中运行 UCM 的加密功能，该模块批准 ML-DSA、Ed25519 和 Ed448，因此使用该镜像时，FIPS 模式下可使用后量子和 EdDSA 签名；使用 `UCM_FIPS_BUILD=1` 构建的 DEB 和 RPM 包运行在 RHEL 9（#5573）或 Ubuntu 24.04 Pro（#5115）的 FIPS 模块上，它们不提供这些算法。设置 `UCM_FIPS=1` 后，UCM 仅在处于活动状态且通过自检的模块上启动，通过它生成密钥，仅当已加载的模块批准某算法时才允许该算法，并拒绝其余算法（MD5、3DES、scrypt、Argon2id、旧版 PKCS#12、NTLM），就绪检查会预先列出实例将失去的功能。UCM 本身不是经过验证的模块，Debian 13 和 arm64 也不在证书 #5586 的已测试配置之列
- **合规配置文件** -- 按 CA 设置、与 ANSSI PG-083、BSI TR-02102-1 和 ECCG 认可的加密机制对齐的策略（密钥类型、哈希、签名方案、有效期上限、由 HSM 持有的 CA 密钥、EC 时间戳签名者），文本强制要求处予以拒绝，文本建议处给出提示，并在将配置文件关联到现有 CA 之前提供只读预检；UCM 未获得上述任何机构的认证或资质
- **SBOM** -- 每个版本的每个软件包和镜像平台都有一份 CycloneDX SBOM，绑定到文件哈希或镜像摘要，列出其所含内容及版本和声明的许可证，以及软件包在安装时解析的内容（[docs/SBOM.md](docs/SBOM.md)）
- **加固** -- 由操作员配置的 HSTS（设置 → 安全，或通过环境变量覆盖）、对客户端证书标头的可信代理限制、API 密钥权限以创建者自身权限为上限；可信代理可以 CIDR 网络给出，启用代理支持后，仅接受来自它们的 `X-Forwarded-*` 标头，因此直接访问后端的客户端无法伪造其地址；Web 界面和管理 API 可以**限制为所列 IP 地址和网络**，而 PKI 协议端点保持可访问

### 运维与监控
- **概览** -- 四项关键指标、首次运行的设置步骤和九张独立卡片（带续期、重试和发布操作的工作队列、自动化健康状况、按来源的签发情况、到期视野、合规性、吊销覆盖率、层级、最新操作、机构和 HSM），可显示、隐藏并重新排序，布局预设按用户保存，数据变化时自动重新加载
- **报告** -- 定期 PDF 报告、管理层摘要、已吊销证书、自定义模板
- **证书工具箱** -- SSL 检查器、CSR/证书解码器、密钥匹配器、格式转换器
- **电子邮件通知** -- 使用 STARTTLS 或隐式 TLS（465 端口）的 SMTP，面向 Gmail、Outlook.com 和 Microsoft 365 的 **OAuth2（XOAUTH2）**，可自定义的 HTML/文本模板，带多个天数阈值的证书到期告警（每个阈值和有效期一封电子邮件，类似 30/14/7/1 的逐级升级），可选择排除由 ACME 客户端自行续期的证书
- **部署钩子** -- 通过 SSH/SFTP 将已签发和已续期的证书以及重新生成的 CRL（DER 或包含上级 CRL 的 PEM 捆绑包）推送到远程主机，每个绑定可设置目标路径和可选的重载命令：基于密钥的认证（生成的 ed25519 或导入的密钥，静态加密）、首次连接时固定主机密钥、按绑定的目标路径（证书 / 密钥 / 完整链，除非绑定要求，否则链中不含自签名根，原子写入）、带重试和按投递历史的持久化投递队列、用于与 UCM 同机运行的服务的**同主机预设**，以及**HTTP API 目标**，通过由正文模板（URL、方法、加密标头、`{{cert_pem|json}}` 风格变量，仅在明确选择并使用已验证 HTTPS 时才包含私钥）构建的一次请求，将证书推送到防火墙、负载均衡器或云 API
- **备份与恢复** -- 手动和计划的加密备份，带保留策略和可选的已存储归档所占空间上限；归档是由独立认证的分块组成的流，因此创建归档以及在恢复前检查归档时不会将其整体载入内存；归档包含 ACME 客户端订单和待处理请求，支持合并或替换模式恢复，跨安装按名称匹配行，并重放修复迁移
- **诊断日志包** -- 一键下载（设置 → 关于 → 诊断）应用日志、错误日志、systemd 日志和不含机密的系统诊断信息，打包为 ZIP，敏感令牌已脱敏
- **系统日志查看器** -- 在界面中浏览应用、访问、错误和 systemd 日志，可按级别、时间窗口和文本筛选，机密已脱敏
- **Prometheus 指标** -- 可选启用、受 bearer 保护的 `/metrics` 端点，公开证书、CA、调度器、webhook 和 ACME 计数器
- **调度器** -- 后台任务（到期检查、CRL 刷新、webhook 投递、备份、自动续期）的管理视图，显示状态并可立即运行，在 gunicorn 下于独立进程中运行
- **自服务 HTTPS** -- 将任意已签发证书应用于 Web 界面；绑定自动跟随续期（重新生成文件、重启服务）
- **安全的网络默认值** -- 双栈监听（`HOST=::` 在一个套接字上同时提供 IPv6 和 IPv4），以及管理员 Base URL 防护（应用前检查可达性，主机停止解析时规范重定向自动让开，`UCM_DISABLE_CANONICAL_REDIRECT=1` 恢复开关）
- **软件更新** -- 应用内更新检查器，支持一键安装，可在稳定版或候选版通道上进行每日定时检查，可选启用无人值守安装（DEB/RPM），强制 SHA256 校验，并提供如实的结果事件（仅在实际安装经版本验证后才记为已安装），另有更新后可选的每用户一次性发布说明窗口
- **全局搜索** -- 跨资源搜索和命令面板（Ctrl+K）

### 平台
- **主题** -- Atelier 和 Aurore，各有深色和浅色，或跟随系统；**按用户的偏好保存在服务器端**（语言、主题、模式）
- **i18n** -- 10 种语言（EN、FR、DE、ES、IT、PT、UK、RU、ZH、JA）
- **持久化界面状态** -- 主要列表页面（证书、CA、模板、策略、审计日志、信任库、用户、SSH）的筛选选择在重新加载后仍然保留
- **数据库** -- SQLite（默认）或**原生 PostgreSQL 后端**，带双向迁移界面
- **响应式界面** -- React 18 + Radix UI，对移动设备友好
- **实时** -- WebSocket 实时更新：其他操作员所做的更改会刷新显示它的列表，中断后重新连接会重新加载列表，而不是让过期的行留在屏幕上
- **多平台** -- Docker、Debian/Ubuntu（.deb）、RHEL/Rocky/Fedora（.rpm）、通过 Helm chart 部署到 Kubernetes（`oci://ghcr.io/neyslim/charts/ucm`）；软件包会为访问日志和错误日志安装日志轮转
- **支持反向代理** -- 公共端口独立于监听端口（Base URL 中显式的 `:80` 或 `:443` 按输入原样公布）、按 IP 或 CIDR 网络设置的可信代理，以及用于 UCM 前端 Ingress 的 Helm chart `proxy.*` 值

---

## 快速开始

### Docker

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

也可从 GitHub Container Registry 获取：`ghcr.io/neyslim/ultimate-ca-manager`。FIPS 变体的标签为 `<version>-fips`（使用 `UCM_FIPS=1` 运行）。固定使用 `3`（或 `3-fips`）标签即可只跟随 3.x 版本。

### Debian/Ubuntu

从[最新发布](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)下载 `.deb` 软件包：

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

从[最新发布](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)下载 `.rpm` 软件包：Fedora 使用 `ucm-VERSION-1.fc43.noarch.rpm`，RHEL、Rocky Linux 和 AlmaLinux 9 使用 `ucm-el9-VERSION-1.el9.noarch.rpm`，这些发行版的 10 版本使用 `ucm-el10-VERSION-1.el10.noarch.rpm`。

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**访问：** `https://localhost:8443` 或 `https://your-server-fqdn:8443`
**首次登录：** `admin`，密码在首次启动时生成：`sudo cat /opt/ucm/data/initial-admin-password`（Docker：`docker exec <container> cat /opt/ucm/data/initial-admin-password`）。首次登录时必须修改密码。如需自行指定密码，请参见[首次访问](docs/installation/README.md#first-access)。

包括 Docker Compose 和源码安装在内的所有方式，请参见[安装指南](docs/installation/README.md)。

---

## 文档

| 资源 | 链接 |
|------|------|
| Wiki（完整文档） | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| 安装 | [docs/installation/](docs/installation/README.md) |
| 用户指南 | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| 管理员指南 | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| ACME 代理客户端 | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| API 参考 | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| 安全 | [docs/SECURITY.md](docs/SECURITY.md) |
| 升级指南 | [UPGRADE.md](UPGRADE.md) |
| 变更日志 | [CHANGELOG.md](CHANGELOG.md) |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | React 18、Vite、Radix UI |
| 后端 | Python 3.11+、Flask、SQLAlchemy |
| 数据库 | SQLite 或 PostgreSQL |
| 服务器 | Gunicorn + gevent WebSocket |
| 加密 | pyOpenSSL、cryptography |
| 认证 | 会话 Cookie、WebAuthn/FIDO2、TOTP、mTLS |

---

## 文件位置

| 项目 | 路径 |
|------|------|
| 应用 | `/opt/ucm/` |
| 数据与数据库 | `/opt/ucm/data/` |
| 配置（DEB/RPM） | `/etc/ucm/ucm.env` |
| 日志（DEB/RPM） | `/var/log/ucm/` |
| 服务 | `systemctl status ucm` |

Docker：数据位于 `/opt/ucm/data/`（作为卷挂载），通过环境变量配置，日志输出到 stdout。

---

## 参与贡献

Pull request 以 `dev` 为目标分支，首次提交时会要求您签署一次
[CLA](CLA.md)。其余内容请参见 [CONTRIBUTING.md](CONTRIBUTING.md)：如何提交有用的错误报告、
易于审查的 pull request 应是什么样子，以及关于测试、翻译和迁移的规则。

---

## 许可证

UCM 是遵循 [GNU AGPL v3.0 only](LICENSE) 的自由软件。无论规模大小、是否商用，运行它都不收取任何费用；对于修改了它却无法公开其修改的用户，可提供[商业许可证](COMMERCIAL-LICENSE.md)。

2.243 之前的版本仍遵循其原有许可证，即带 Commons Clause 的 BSD 3-Clause。

---

## 支持

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

如果您觉得 UCM 有用，欢迎支持其开发：

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
