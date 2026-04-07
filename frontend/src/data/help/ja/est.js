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
          { label: '情報', text: '統合用のESTエンドポイントURL、登録統計、使用例' },
        ]
      },
      {
        title: '認証',
        items: [
          { label: 'mTLS（相互TLS）', text: 'クライアントがTLSハンドシェイク中に証明書を提示 — 最も強力な認証方法' },
          { label: 'HTTP Basic認証', text: 'mTLSが利用できない場合のユーザー名/パスワードによるフォールバック' },
        ]
      },
      {
        title: 'エンドポイント',
        items: [
          { label: '/cacerts', text: 'CA証明書チェーンの取得（認証不要）' },
          { label: '/simpleenroll', text: 'CSRを送信して署名済み証明書を受け取る' },
          { label: '/simplereenroll', text: '既存の証明書を更新（mTLSが必要）' },
          { label: '/csrattrs', text: 'サーバーが推奨するCSR属性を取得' },
          { label: '/serverkeygen', text: 'サーバーがキーペアを生成し、証明書と鍵を返す' },
        ]
      },
    ],
    tips: [
      'ESTはSCEPの最新の代替です — 新規デプロイにはESTを推奨します',
      '最高のセキュリティにはmTLS認証を使用 — Basic認証はフォールバックです',
      '/simplereenrollエンドポイントはクライアントがmTLS経由で現在の証明書を提示する必要があります',
      '情報タブからエンドポイントURLをコピーしてESTクライアントを設定してください',
    ],
    warnings: [
      'ESTにはHTTPSが必要です — クライアントはUCMサーバー証明書またはCAを信頼する必要があります',
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

1. **ESTを有効化** — ESTプロトコルのオン/オフ切り替え
2. **署名CA** — EST登録証明書に署名するCAを選択
3. **認証** — HTTP Basic認証の資格情報（ユーザー名とパスワード）を設定
4. **証明書有効期間** — EST発行証明書のデフォルト有効期間（日数）

### 設定の保存

**保存**をクリックして変更を適用します。有効化するとESTエンドポイントは即座に利用可能になります。

## 認証

ESTは2つの認証方法をサポートしています：

### 相互TLS（mTLS） — 推奨

クライアントがTLSハンドシェイク中に証明書を提示します。UCMが証明書を検証し、クライアントを自動的に認証します。

- **最も強力な方法** — 暗号的なクライアントID
- **\`/simplereenroll\`に必須** — クライアントは現在の証明書を提示する必要があります
- **適切なTLS終端設定に依存** — リバースプロキシが\`SSL_CLIENT_CERT\`をUCMに渡す必要があります

### HTTP Basic認証 — フォールバック

HTTPS経由のユーザー名とパスワード認証。EST設定で設定します。

- **設定が簡単** — クライアント証明書不要
- **セキュリティが低い** — リクエストごとに資格情報が送信される（HTTPSで保護）
- **mTLSインフラストラクチャが利用できない場合に使用**

## ESTエンドポイント

すべてのエンドポイントは\`/.well-known/est/\`配下にあります：

### GET /cacerts
CA証明書チェーンを取得します。**認証不要。**

信頼のブートストラップに使用 — クライアントは登録前にCA証明書を取得します。

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
既存の証明書を更新します。**mTLSが必要** — クライアントは更新する証明書を提示する必要があります。

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

## 情報タブ

情報タブには以下が表示されます：
- **エンドポイントURL** — 各EST操作用のコピー＆ペースト対応URL
- **登録統計** — 登録、再登録、エラーの数
- **最終アクティビティ** — 監査ログからの最新のEST操作

## 統合例

### estクライアント（libest）の使用
\`\`\`bash
estclient -s your-server -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

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
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://your-server:8443/.well-known/est" \\
  kerberos
\`\`\`

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
