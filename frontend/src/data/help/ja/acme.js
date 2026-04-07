export default {
  helpContent: {
    title: 'ACME',
    subtitle: '自動証明書管理',
    overview: 'UCMは2つのACMEモードをサポートしています：RFC 8555準拠のCA（Let\'s Encrypt、ZeroSSL、Buypass、HARICAなど）からパブリック証明書を取得するACMEクライアントと、マルチCA対応のドメインマッピングによる内部PKI自動化のためのローカルACMEサーバーです。',
    sections: [
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
        title: 'マルチCA解決',
        content: 'ACMEクライアントが証明書を要求すると、UCMは以下の順序で署名CAを解決します：',
        items: [
          '1. ローカルドメインマッピング — 完全一致のドメイン、次に親ドメイン',
          '2. DNSドメインマッピング — DNSプロバイダーに設定された発行CAを確認',
          '3. グローバルデフォルト — ACMEサーバー設定で指定されたCA',
          '4. 秘密鍵を持つ最初の利用可能なCA',
        ]
      },
    ],
    tips: [
      'ACMEディレクトリURL: https://your-server:port/acme/directory',
      'カスタムディレクトリURLを使用して、ZeroSSL、Buypass、HARICA、またはその他のRFC 8555 CAに接続できます',
      'EAB資格情報（キーID + HMACキー）は、登録時にCAから提供されます',
      'ECDSA P-256キーはRSA-2048と同等のセキュリティを、はるかに小さいサイズで提供します',
      'ローカルドメインを使用して、異なる内部ドメインに異なるCAを割り当てることができます',
      '秘密鍵を持つ任意のCAを発行CAとして選択できます',
      'ワイルドカードドメイン（*.example.com）にはDNS-01検証が必要です',
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
`
  }
}
