export default {
  helpContent: {
    title: 'EST',
    subtitle: 'セキュアトランスポートによる登録',
    overview: 'EST（RFC 7030）はHTTPSを介して、相互TLS（mTLS）またはHTTP Basic認証による安全な証明書登録を提供します。強力なトランスポートセキュリティを備えた標準ベースの登録を必要とする最新のエンタープライズ環境に最適です。',
    sections: [
      {
        title: 'タブ',
        items: [
          { label: '設定', text: 'ESTの有効化、署名CAの選択、認証資格情報と証明書有効期間の設定' },
          { label: 'ESTエンドポイント', text: '統合用のESTエンドポイントURLと登録統計' },
        ]
      },
      {
        title: '認証',
        items: [
          { label: 'mTLS（相互TLS）', text: 'クライアントがTLSハンドシェイク中に証明書を提示, 最も強力な認証方法' },
          { label: 'HTTP Basic認証', text: 'mTLSが利用できない場合のユーザー名/パスワードによるフォールバック。PATCH /api/v2/est/config で allow_empty_username を設定すると、クライアントは空のユーザー名とパスワードを送ることもできます（RFC 7030 §3.2.3、v2.252）' },
          { label: '提示される証明書', text: 'mTLS 経由の /simpleenroll と /serverkeygen では、EST の CA が署名した証明書はその CA が現在も保持しているものでなければなりません。失効済み、置き換え済み、削除済みの証明書は拒否されます（RFC 7030 §3.3.2）。このサーバーの別の CA が発行した証明書は、その証明書または上位の CA が失効した場合、または期限切れの場合に拒否されます (v2.252)。このサーバーが保持しない認証局のものは TLS 層に任されます' },
          { label: 'tls-unique リンク', text: 'challengePassword を含む CSR は、UCM への TLS 1.2 接続の tls-unique 値を持つ必要があります（RFC 7030 §3.5）。値が異なる場合、または検証できない場合（TLS 1.3、前段のプロキシ）は 400 で拒否されます。/csrattrs はこれを要求しません。PATCH /api/v2/est/config で設定する ignore_challenge_password は、そこにパスワードを入れるクライアントに対してこのチェックを省略します (v2.252)' },
          { label: '侵害された鍵', text: '鍵が侵害（keyCompromise）として失効された CSR は 400 で拒否されます (v2.252)' },
        ]
      },
      {
        title: 'エンドポイント',
        items: [
          { label: '/cacerts', text: 'CA証明書チェーンの取得（認証不要）' },
          { label: '/simpleenroll', text: 'CSRを送信して署名済み証明書を受け取る' },
          { label: '/simplereenroll', text: '既存の証明書を更新（mTLSが必要。クライアント証明書がない場合は 403）。SubjectAltName のない CSR は、CN から作った名前ではなく、証明書自身の名前（なかった場合は名前なし）を更新します（RFC 7030 §4.2.2、v2.252）' },
          { label: '/csrattrs', text: 'サーバーが推奨するCSR属性を取得：keyUsage、subjectAltName、extKeyUsage を OID のみで返します（RFC 9908 §5.2、v2.252）。PATCH /api/v2/est/config の csrattrs_legacy_encoding は、必要とするクライアント向けに従来の形（extensionRequest 内の OID）を返します' },
          { label: 'エラー', text: '登録の拒否（レート制限を含む）は、理由を示すプレーンテキストのメッセージ（text/plain、RFC 8951 §5）で返されます。たとえば本文が base64 でない、PKCS#10 CSR でない、または CA の名前制約によるものです (v2.252)' },
          { label: '/serverkeygen', text: 'サーバーがキーペアを生成し、証明書と鍵を返します。鍵は発行 CA の強度に合わせ、RSA または EC のリクエスト鍵がある場合はそのファミリー（サイズや曲線は無視されます）、そうでなければ CA のファミリーとなり、ポリシーが許可する最も近いタイプに変更されます。鍵は TLS 下で暗号化されない PKCS#8 として返されます。mTLS 証明書の鍵（AsymmetricDecryptKeyIdentifier）を指定した CSR には、その証明書宛てに暗号化されて返されます。2048 ビット以上の RSA は鍵トランスポート（keyEncipherment）、EC は鍵合意（keyAgreement）で、アルゴリズムは CSR の SMIMECapabilities に列挙されたものを使い、発行 CA がこの目的で発行する EST key generator 証明書で署名された鍵パッケージに格納されます（Ed448 の CA の下では Ed25519、v2.252）' },
        ]
      },
    ],
    tips: [
      'ESTはSCEPの最新の代替です: 新規デプロイにはESTを推奨します',
      '最高のセキュリティにはmTLS認証を使用: Basic認証はフォールバックです',
      '/simplereenrollエンドポイントはクライアントがmTLS経由で現在の証明書を提示する必要があります',
      'ESTエンドポイントタブからエンドポイントURLをコピーしてESTクライアントを設定してください',
    ],
    warnings: [
      'ESTにはHTTPSが必要です: クライアントはUCMサーバー証明書またはCAを信頼する必要があります',
      'mTLS認証には適切なTLS終端設定が必要です（リバースプロキシがクライアント証明書を転送する必要があります）',
    ],
  },
  helpGuides: {
    title: 'ESTプロトコル',
    content: `
## 概要

Enrollment over Secure Transport（EST）は**RFC 7030**で定義されており、HTTPSを介した証明書の登録、再登録、CA証明書の取得を提供します。ESTはSCEPの最新の代替であり、相互TLS（mTLS）認証によるより強力なセキュリティを提供します。

## 設定

### 設定タブ

1. **ESTを有効化**: ESTプロトコルのオン/オフ切り替え
2. **署名CA**: EST登録証明書に署名するCAを選択
3. **認証**: HTTP Basic認証の資格情報（ユーザー名とパスワード）を設定
4. **証明書有効期間**: EST発行証明書のデフォルト有効期間（日数）

### 設定の保存

**保存**をクリックして変更を適用します。有効化するとESTエンドポイントは即座に利用可能になります。

## 認証

ESTは2つの認証方法をサポートしています：

### 相互TLS（mTLS）: 推奨

クライアントがTLSハンドシェイク中に証明書を提示します。UCMが証明書を検証し、クライアントを自動的に認証します。

- **最も強力な方法**: 暗号的なクライアントID
- **\`/simplereenroll\`に必須**: クライアントは現在の証明書を提示する必要があります
- **提示される証明書**: \`/simpleenroll\`と\`/serverkeygen\`では、EST の CA が署名した証明書はその CA が現在も保持しているものでなければなりません。失効済み、置き換え済み、削除済みの証明書は拒否されます（RFC 7030 §3.3.2）。信頼された別の認証局の証明書は引き続き受け入れられます
- **適切なTLS終端設定に依存**: リバースプロキシが\`SSL_CLIENT_CERT\`をUCMに渡す必要があります

### HTTP Basic認証: フォールバック

HTTPS経由のユーザー名とパスワード認証。EST設定で設定します。

- **設定が簡単**: クライアント証明書不要
- **セキュリティが低い**: リクエストごとに資格情報が送信される（HTTPSで保護）
- **mTLSインフラストラクチャが利用できない場合に使用**

## ESTエンドポイント

すべてのエンドポイントは\`/.well-known/est/\`配下にあります：

### GET /cacerts
CA証明書チェーンを取得します。**認証不要。**

信頼のブートストラップに使用: クライアントは登録前にCA証明書を取得します。

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
PKCS#10 CSRを送信して署名済み証明書を受け取ります。

認証が必要です（mTLSまたはBasic認証）。

\`\`\`bash
# curlでBasic認証を使用
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
既存の証明書を更新します。**mTLSが必要**: クライアントは更新する証明書を提示する必要があります。

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
サーバーが推奨するCSR属性（OID）を取得します。

### POST /serverkeygen
サーバーがキーペアを生成し、証明書と秘密鍵を返します。クライアントがローカルで鍵を生成できない場合に便利です。

生成される鍵は発行 CA の強度に合わせます。RSA または EC のリクエスト鍵がある場合はそのファミリー（サイズや曲線は無視されます）、そうでなければ CA のファミリーとなり、ポリシーが許可する最も近いタイプに変更されます。

秘密鍵は、TLS で保護された暗号化されない PKCS#8（\`application/pkcs8\`）として返されます。暗号化して受け取るには、mTLS で認証し、クライアント証明書の鍵識別子を CSR に入れます（AsymmetricDecryptKeyIdentifier）。すると鍵は、その証明書宛てにエンベロープされた RFC 5958 の鍵パッケージで届きます。keyEncipherment を持つ 2048 ビット以上の RSA 証明書には鍵トランスポート、keyAgreement を持つ EC 証明書には鍵合意（ECDH）が使われ、鍵トランスポートまたは鍵合意とコンテンツのアルゴリズムは、クライアントの順序で CSR の SMIMECapabilities から選ばれます。パッケージは、発行 CA が初回使用時に発行し自動で更新する「EST key generator」証明書で署名されます。この証明書は \`/cacerts\` が返す CA にチェーンし、CA と同じ鍵ファミリーを持ち、Ed448 の CA の下では Ed25519 です (v2.252)。

## ESTエンドポイントタブ

ESTエンドポイントタブには以下が表示されます：
- **エンドポイントURL**: 各EST操作用のコピー＆ペースト対応URL
- **登録統計**: 登録の合計、成功、失敗の数

## 統合例

### estクライアント（libest）の使用
\`estclient\` を HTTP Basic 資格情報（\`-u\` と \`-h\`）またはクライアント証明書で使用します。TLS-SRP オプションは適用されません：UCM は TLS-SRP を提供しません。

### OpenSSLの使用
\`\`\`bash
# CA証明書を取得
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# CSRを生成
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# 登録（Basic認証）
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

応答は裸の証明書ではなく、base64 の PKCS#7（certs-only）です。\`openssl x509\` ではなく \`openssl pkcs7\` で読み取ってください。

### Windows
Windows には組み込みの EST クライアントがありません。\`certutil -enrollmentServerURL\` が登録するのは証明書登録 Web サービス（WSTEP）であり、EST サーバーではありません。Windows マシンには Windows 自動登録（XCEP/WSTEP）を使用してください。

## EST vs SCEP

| 機能 | EST | SCEP |
|------|-----|------|
| トランスポート | HTTPS (TLS) | HTTPまたはHTTPS |
| 認証 | mTLS + Basic認証 | チャレンジパスワード |
| 標準 | RFC 7030 (2013) | RFC 8894 (2020、ただしレガシー) |
| 鍵生成 | サーバー側オプション | クライアントのみ |
| 更新 | mTLS再登録 | 再登録 |
| セキュリティ | 強力（TLSベース） | 弱い（共有シークレット） |
| 推奨 | ✅ 新規に推奨 | レガシーデバイスのみ |

> 💡 新規デプロイにはESTを使用してください。SCEPはESTをサポートしないレガシーネットワークデバイスにのみ使用してください。
`
  }
}
