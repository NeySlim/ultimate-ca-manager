export default {
  helpContent: {
    title: 'ACME',
    subtitle: '自動証明書管理',
    overview: 'UCMは2つのACMEモードをサポートしています：RFC 8555準拠のCA（Let\'s Encrypt、ZeroSSL、Buypass、HARICAなど）からパブリック証明書を取得するACMEクライアントと、マルチCA対応のドメインマッピングによる内部PKI自動化のためのローカルACMEサーバーです。',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "ローカル ACME サーバーは renewalInfo リソースを公開し、クライアントが各証明書の理想的な更新時期を知ることができます。",
        items: [
          { label: "推奨ウィンドウ", text: "有効期限前を中心とした開始/終了ウィンドウを返し、更新を時間的に分散します" },
          { label: "失効", text: "失効した証明書は過去のウィンドウを返し、準拠クライアントは直ちに更新します" },
          { label: "認証不要", text: "renewalInfo は単純な GET — アカウントや JWS は不要（RFC 9773）" },
        ]
      },
      {
        title: 'ACMEクライアント',
        items: [
          { label: 'クライアント', text: '任意のACME CAから証明書を要求 — Let\'s Encrypt、ZeroSSL、Buypass、HARICA、またはカスタム' },
          { label: 'カスタムサーバー', text: 'カスタムACMEディレクトリURLを設定して、任意のRFC 8555準拠CAを使用します' },
          { label: 'EAB', text: '事前登録が必要なCA（ZeroSSL、HARICAなど）のための外部アカウントバインディングサポート' },
          { label: 'キータイプ', text: '証明書キー用のRSA-2048、RSA-4096、ECDSA P-256、ECDSA P-384' },
          { label: 'アカウントキー', text: 'ACMEアカウントキー用のES256 (P-256)、ES384 (P-384)、またはRS256アルゴリズム' },
          { label: 'DNSプロバイダー', text: 'DNS-01チャレンジプロバイダーの設定（Cloudflare、Route53など）' },
          { label: 'ドメイン', text: '自動検証のためにドメインをDNSプロバイダーにマッピングします' },
        ]
      },
      {
        title: 'ローカルACMEサーバー',
        items: [
          { label: '設定', text: '組み込みACMEサーバーの有効化/無効化、デフォルトCAの選択' },
          { label: 'ローカルドメイン', text: 'マルチCA発行のために内部ドメインを特定のCAにマッピング' },
          { label: 'アカウント', text: '登録済みACMEクライアントアカウントの表示と管理' },
          { label: '履歴', text: 'すべてのACME証明書発行オーダーの追跡' },
        ]
      },
      {
        title: 'ACMEプロキシ',
        items: [
          { label: 'アップストリームCA', text: 'プリセット（Let\'s Encrypt本番/ステージング）を選択するか、任意のRFC 8555 CA用のカスタムURLを入力します' },
          { label: 'アカウント状態', text: 'UCMがアップストリームCAに登録されているかを表示します。アカウントは最初のプロキシリクエスト時に自動登録されます' },
          { label: '接続テスト', text: 'アップストリームCAへの接続性を確認し、EAB認証情報が必要かチェックします' },
          { label: 'アカウントリセット', text: '保存されたアップストリームアカウント認証情報をクリアして再登録を強制します（CA変更後に使用）' },
          { label: 'EAB認証情報', text: 'EABが必要なCAのためのExternal Account Binding認証情報（例：ZeroSSL、Google Trust）' },
          { label: 'DNSチャレンジ', text: 'UCMは設定されたDNSプロバイダーを使用して、クライアントに代わってDNS-01チャレンジを処理します' },
        ]
      },
      {
        title: 'EAB クレデンシャル(サーバー側)',
        content: 'UCM が ACME サーバーとして動作する場合、External Account Binding(RFC 8555 §7.3.4)により、クライアントがアカウントを登録する前に事前発行クレデンシャルを要求できます:',
        items: [
          { label: '発行', text: 'ACME → EAB Credentials から新しい kid + HMAC キーペアを生成' },
          { label: '配布', text: 'kid + HMAC をクライアント(cert-manager、certbot、acme.sh)に渡す' },
          { label: 'バインド', text: 'クライアントは newAccount で MAC キー上に JWS を署名して ACME アカウントをバインドする' },
          { label: 'ローテーション / 取消', text: 'kid をいつでも取消可能 — 既存アカウントは継続動作、新規バインドは拒否' },
          { label: '監査', text: '発行・ローテーション・取消は実行したオペレーターの下で監査される' },
        ]
      },
      {
        title: 'カスタム DNS リゾルバ(DNS-01)',
        items: [
          { label: 'アカウント単位オーバーライド', text: '_acme-challenge TXT レコードを検証する際にシステムリゾルバを上書き' },
          { label: 'スプリットホライズン', text: '権威サーバーが内部にあり、パブリックビューが他所にキャッシュされている場合に有用' },
          { label: '古いレコード', text: '高速な自動更新中にパブリックリゾルバのキャッシュを回避' },
        ]
      },
      {
        title: '内部 / プライベート IP 上の ACME',
        content: 'HTTP-01 および TLS-ALPN-01 検証は、RFC1918、loopback、.lan / .local / .corp ターゲットでデフォルトで動作します — UCM の主要なデプロイメントモデル。',
        items: [
          { label: 'トグル', text: 'Settings → SystemConfig → acme.allow_private_ips(デフォルト: true)' },
          { label: '常時ブロック', text: 'クラウドメタデータ IP(169.254.169.254、fd00:ec2::254 など)は無条件にブロック' },
        ]
      },
      {
        title: 'マルチCA解決',
        content: 'ACMEクライアントが証明書を要求すると、UCMは以下の順序で署名CAを解決します：',
        items: [
          '1. ローカルドメインマッピング — 完全一致のドメイン、次に親ドメイン',
          '2. DNSドメインマッピング — DNSプロバイダーに設定された発行CAを確認',
          '3. グローバルデフォルト — ACMEサーバー設定で指定されたCA',
          '4. 秘密鍵を持つ最初の利用可能なCA',
        ]
      },
      {
        title: 'IPアドレス証明書 (RFC 8738)',
        content: 'ローカルACMEサーバーはDNS名だけでなく、IPv4およびIPv6アドレスの証明書を発行できます。注文で識別子タイプ「ip」を使用します。',
        items: [
          { label: '識別子', text: '{ "type": "ip", "value": "192.0.2.10" }（IPv4）または 2001:db8::1 のようなIPv6リテラルで注文' },
          { label: 'チャレンジ', text: 'HTTP-01とTLS-ALPN-01のみが提供されます — RFC 8738によりIP識別子ではDNS-01は禁止されています' },
          { label: 'TLS-ALPN-01 SNI', text: '検証では逆引きDNS形式（in-addr.arpa / ip6.arpa）をSNIホスト名として使用します' },
          { label: '発行されるSAN', text: '証明書にはiPAddress SANが含まれます。DNS + IPの混在注文に対応しています' },
          { label: '内部IP', text: 'RFC1918およびループバックアドレスはそのまま検証されます — UCMの主要な導入モデルです' },
        ]
      }
    ],
    tips: [
      'ACMEディレクトリURL: https://your-server:port/acme/directory',
      'カスタムディレクトリURLを使用して、ZeroSSL、Buypass、HARICA、またはその他のRFC 8555 CAに接続できます',
      'EAB資格情報（キーID + HMACキー）は、登録時にCAから提供されます',
      'ECDSA P-256キーはRSA-2048と同等のセキュリティを、はるかに小さいサイズで提供します',
      'ローカルドメインを使用して、異なる内部ドメインに異なるCAを割り当てることができます',
      '秘密鍵を持つ任意のCAを発行CAとして選択できます',
      'ワイルドカードドメイン（*.example.com）にはDNS-01検証が必要です',
      'UCM が ACME サーバーの場合、ACME → EAB Credentials で独自の EAB クレデンシャルを発行してください',
      'Kubernetes/cert-manager 用: examples/kubernetes/cert-manager/ にある参照マニフェストを参照',
    ],
    warnings: [
      'ドメイン検証が必要です — サーバーが到達可能であるか、DNSが設定されている必要があります',
      'アカウントキータイプを変更するには、ACMEアカウントの再登録が必要です',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## 概要

UCMはACME（自動証明書管理環境）を2つのモードでサポートしています：

- **ACMEクライアント** — 任意のRFC 8555準拠CA（Let's Encrypt、ZeroSSL、Buypass、HARICA、またはカスタム）から証明書を取得
- **ローカルACMEサーバー** — マルチCA対応の内部PKI自動化のための組み込みACMEサーバー

## ACMEクライアント

### クライアント設定
ACMEクライアント設定を管理します：
- **環境** — ステージング（テスト）またはプロダクション（本番証明書）
- **連絡先メール** — アカウント登録に必要です
- **自動更新** — 有効期限前に証明書を自動的に更新します
- **証明書キータイプ** — RSA-2048、RSA-4096、ECDSA P-256、またはECDSA P-384
- **アカウントキーアルゴリズム** — ACMEアカウント署名用のES256、ES384、またはRS256

### カスタムACMEサーバー
Let's Encryptだけでなく、任意のRFC 8555準拠CAを使用できます：

| CAプロバイダー | ディレクトリURL |
|---|---|
| **Let's Encrypt** | *（デフォルト、空のまま）* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

**設定** → **カスタムACMEサーバー**でCAのディレクトリURLを設定してください。

### 外部アカウントバインディング (EAB)
一部のCAは、ACMEアカウントをCAの既存アカウントにリンクするためにEAB資格情報を要求します：

1. CAのポータルで登録して**EABキーID**と**HMACキー**を取得
2. **設定** → **カスタムACMEサーバー**に両方の値を入力
3. HMACキーはbase64urlエンコードされています（CAから提供）

> 💡 EABはZeroSSL、HARICA、Google Trust Services、およびほとんどのエンタープライズCAで必要です。

### ECDSA vs RSAキー

| キータイプ | サイズ | セキュリティ | パフォーマンス |
|---|---|---|---|
| **RSA-2048** | 2048 bit | 標準 | 基準 |
| **RSA-4096** | 4096 bit | より高い | より遅い |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | はるかに速い |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | 速い |

ECDSAキーは最新のデプロイに推奨されます — より小さく、より速く、同等のセキュリティです。

### キーソース
証明書リクエスト時に、秘密鍵の由来を選択します：

- **新しい鍵を生成** *(デフォルト)* — UCM がオーダーごとに新しい鍵ペアを作成
- **更新時に鍵を再利用** — 更新をまたいで同じ秘密鍵を維持（DANE/TLSA レコードやキーピンニングに必要）；初回発行で鍵を生成し、更新時に再読み込み
- **外部 CSR を提供** — 外部で生成した PEM CSR を貼り付け；UCM は finalize 時に送信し、秘密鍵は UCM に一切入りません。CSR のドメインはオーダーの識別子と完全に一致する必要があります

### プリフライト（ドライラン）
リクエストフォームの**プリフライト実行**は、本番のレート制限を消費せずに Let's Encrypt の **staging** ディレクトリに対してリクエスト全体を検証します：

- ドメイン構文、連絡先メール、ACME アカウント / EAB、CA 接続性を確認
- **フル**モードは staging オーダーを作成し、公開すべき \`_acme-challenge\` TXT レコードを正確にプレビュー
- **検証のみ**モードはオーダーを作成せず設定と接続性のみ確認
- レコード追加後に DNS TXT の伝播を任意で検証可能

> 💡 カスタム CA には staging エンドポイントがないため、プリフライトは設定と接続性のみを検証します。

### DNSプロバイダー
ドメイン検証用のDNS-01チャレンジプロバイダーを設定します。対応プロバイダー：
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- その他

各プロバイダーにはDNSサービス固有のAPI資格情報が必要です。

### ドメイン
ドメインをDNSプロバイダーにマッピングします。ドメインの証明書を要求する際、UCMはマッピングされたプロバイダーを使用してDNS-01チャレンジレコードを作成します。

1. **ドメインを追加**をクリック
2. ドメイン名を入力（例：\`example.com\` または \`*.example.com\`）
3. DNSプロバイダーを選択
4. **保存**をクリック

> 💡 ワイルドカード証明書（\`*.example.com\`）にはDNS-01検証が必要です。


## ACMEプロキシモード

ACMEプロキシにより、内部クライアントはインターネットに直接アクセスすることなく、UCMを介して公開CA（Let's Encrypt、ZeroSSLなど）から証明書を要求できます。UCMは仲介者として機能し、DNS-01チャレンジを管理し、リクエストをアップストリームCAに転送します。

### プロキシモードの使用場面
- インターネットに直接アクセスできない内部サーバー
- UCMに設定されたDNSプロバイダーによるDNS-01チャレンジの一元管理
- すべての公開証明書発行の監査と追跡

### 設定
1. **ACME** → **Let's Encrypt**タブに移動
2. **ACMEプロキシ**セクションまでスクロール
3. **ACMEプロキシ**トグルを有効化
4. **外部CAアカウント**で**アップストリームCAアカウント**を選択（Let's Encrypt、Actalis、ZeroSSL、カスタムURL、EAB）
5. **接続テスト**でアップストリームCAとの接続性を確認
6. 必要ならアップストリームアカウントを登録（メール + **アカウント登録**）
7. 未登録の場合、UCMは最初のプロキシリクエスト時に自動登録

### 専用プロキシパス（マルチCA）
各外部CAアカウントは独自のACMEプロキシエンドポイントを公開できます：

1. **外部CAアカウント**を開く（同じLet's Encryptタブ）
2. CAアカウントを編集または作成
3. **ACMEプロキシ経由で公開**を有効化
4. 一意の**プロキシパス (slug)** を設定 — 例: \`actalis-production\`
5. 保存 — URLはプロキシセクションとアカウントカードに表示

クライアントは次を使用：
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

レガシー既定パス（プロキシ設定で選択したアカウント）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

予約済みslug（使用不可）: \`directory\`, \`new-order\`, \`challenge\`, \`acct\` など

### アカウント管理
- **アカウント状態バッジ**はUCMがアップストリームCAに登録されているかを表示
- アップストリームCAの変更は古い認証情報を自動的にクリアし、再登録を強制
- 必要に応じて**アカウントリセット**ボタンで手動で認証情報をクリア
- **接続テスト**はアップストリームディレクトリが到達可能か、EABが必要かを確認

### プロキシの使用
内部ACMEクライアントを対象CAのプロキシディレクトリに向けます。

**slug URL**（複数CA時に推奨）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

**既定URL**（プロキシ設定で選択したアカウント）：
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

certbotの例（\`<slug>\`を置換）：
\`\`\`
certbot certonly \\
  --server https://your-ucm-server:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 プロキシEAB認証情報はクライアントEABとは別です — UCMをアップストリームCAに対して認証します。

> ⚠ 前提: ドメインをACME DomainsでDNSプロバイダ付きで設定。プロキシはdns-01のみ。

> ⚠ 同一FQDNへの同時リクエスト（Certbot + UCM UI）を避けてください。

> ℹ️ 自己署名HTTPS（ラボ）ではCertbotに \`--no-verify-ssl\` を追加。

## ローカルACMEサーバー

### 設定
- **有効化/無効化** — 組み込みACMEサーバーの切り替え
- **デフォルトCA** — デフォルトで証明書に署名するCAを選択
- **利用規約** — クライアント向けのオプションのToS URL

### ACMEディレクトリURL
\`\`\`
https://your-server:8443/acme/directory
\`\`\`

certbot、acme.sh、CaddyなどのクライアントはこのURLを使用してACMEエンドポイントを検出します。

### ローカルドメイン（マルチCA）
内部ドメインを特定のCAにマッピングします。これにより、異なるドメインを異なるCAで署名できます。

1. **ドメインを追加**をクリック
2. ドメインを入力（例：\`internal.corp\` または \`*.dev.local\`）
3. **発行CA**を選択
4. **自動承認**を有効化/無効化
5. **保存**をクリック

### CA解決順序
ACMEクライアントが証明書を要求すると、UCMは以下の順序で署名CAを決定します：
1. **ローカルドメインマッピング** — 完全一致、次に親ドメイン一致
2. **DNSドメインマッピング** — DNSプロバイダーに設定されたCA
3. **グローバルデフォルト** — ACMEサーバー設定で指定されたCA
4. **最初の利用可能なCA** — 秘密鍵を持つ任意のCA

### アカウント
登録済みACMEクライアントアカウントの表示：
- アカウントIDと連絡先メール
- 登録日
- オーダー数

### 履歴
すべての証明書発行オーダーの参照：
- オーダーステータス（保留中、有効、無効、準備完了）
- 要求されたドメイン名
- 使用された署名CA
- 発行タイムスタンプ

## certbotの使用

\`\`\`
# アカウント登録（Let's Encrypt — デフォルト）
certbot register --agree-tos --email admin@example.com

# カスタムACME CA + EABでの登録
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --agree-tos --email admin@example.com

# ECDSAキーで証明書を要求
certbot certonly --server https://your-server:8443/acme/directory \\
  --standalone -d myserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# 更新
certbot renew --server https://your-server:8443/acme/directory
\`\`\`

## acme.shの使用

\`\`\`
# デフォルト（Let's Encrypt）
acme.sh --issue -d example.com --standalone

# カスタムACME CAとEABおよびECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ 内部ACMEの場合、クライアントはUCM CAを信頼する必要があります。ルートCA証明書をクライアントのトラストストアにインストールしてください。
## IPアドレス証明書 (RFC 8738)

ローカルACMEサーバーはDNS名だけでなく、**IPアドレス**（IPv4およびIPv6）の証明書を発行できます。内部サービス、アプライアンス、IPで直接アドレス指定されるホストに便利です。

### IP証明書の注文
ACME注文で識別子タイプ \`ip\` を使用します：
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
DNS + IP の混在注文も対応しています。

### 検証
- IP識別子に対して提供される検証は **HTTP-01** と **TLS-ALPN-01** のみです。RFC 8738 により IP では **DNS-01 は禁止** されています。
- **HTTP-01** は IP に直接接続します（IPv6リテラルは角括弧で囲まれます。例：\`http://[2001:db8::1]/...\`）。
- **TLS-ALPN-01** は IP の逆引きDNS形式（\`in-addr.arpa\` / \`ip6.arpa\`）を SNI ホスト名として使用します。

### 発行される証明書
署名された証明書には、検証された各IPに対する **iPAddress** SubjectAltName エントリが含まれます。

> 💡 内部アドレス（RFC1918、ループバック）はそのまま検証されます — UCMの主要な導入モデルです。クラウドメタデータIPは引き続きブロックされます。

## Renewal Information (ARI, RFC 9773)

ローカル ACME サーバーは directory で \`renewalInfo\` を通知し、証明書ごとの**推奨更新ウィンドウ**を提供します。

- 有効期限前を中心としたウィンドウ → 更新が時間的に分散
- 失効した証明書 → 過去のウィンドウ（直ちに更新）
- \`/acme/renewalInfo/<certID>\` への認証不要の GET

`
  }
}
