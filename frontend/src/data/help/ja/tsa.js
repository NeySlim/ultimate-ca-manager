export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'タイムスタンプ局',
    overview: 'TSA（RFC 3161）は、文書またはハッシュが特定の時点に存在したことを証明する信頼されたタイムスタンプを提供します。コード署名、法的コンプライアンス、監査証跡に使用されます。',
    sections: [
      {
        title: 'タブ',
        items: [
          { label: '設定', text: 'TSAの有効化、署名CAの選択、TSAポリシーOIDの設定' },
          { label: '情報', text: 'TSAエンドポイントURL、OpenSSLの使用例、リクエスト統計' },
        ]
      },
      {
        title: '設定',
        items: [
          { label: '署名CA', text: 'タイムスタンプトークンに署名する秘密鍵を持つCA — 有効で期限切れでないCAである必要があります' },
          { label: 'ポリシーOID', text: 'TSAポリシーのオブジェクト識別子（例：1.2.3.4.1） — すべてのタイムスタンプレスポンスに含まれます' },
          { label: '有効化/無効化', text: '設定を失うことなくTSAエンドポイントのオン/オフを切り替え' },
        ]
      },
      {
        title: '使用方法',
        items: [
          { label: 'リクエスト作成', text: 'openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq' },
          { label: 'TSAに送信', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: '検証', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'TSAタイムスタンプは、証明書の有効期限後も署名が有効であることを保証するためにコード署名で使用されます',
      'TSAエンドポイントはContent-Type: application/timestamp-queryのHTTP POSTを受け付けます',
      'タイムスタンプリクエスト作成時にはSHA-256以上のハッシュアルゴリズムを使用してください',
      '認証は不要です — TSAエンドポイントはCRL/OCSPと同様にパブリックにアクセス可能です',
    ],
    warnings: [
      'TSAを有効にする前に有効な署名CAを設定する必要があります',
      'TSAエンドポイントはパブリックプロトコルエンドポイントです — タイムスタンプリクエストに機密データを含めないでください',
    ],
  },
  helpGuides: {
    title: 'TSAプロトコル',
    content: `
## 概要

タイムスタンプ局（TSA）は**RFC 3161**を実装し、文書、ハッシュ、またはデジタル署名が特定の時点に存在したことを暗号的に証明する信頼されたタイムスタンプを提供します。TSAはコード署名、法的コンプライアンス、長期保存、監査証跡に広く使用されています。

## 動作方法

1. **クライアントがタイムスタンプリクエストを作成** — SHA-256/SHA-512でファイルをハッシュし、\`TimeStampReq\`（ASN.1 DERエンコード）を作成
2. **クライアントがTSAにリクエストを送信** — \`/tsa\`エンドポイントへのHTTP POST（\`Content-Type: application/timestamp-query\`）
3. **UCMがタイムスタンプに署名** — 設定されたCAがハッシュ + 現在時刻を\`TimeStampResp\`に署名
4. **クライアントがレスポンスを受信・保存** — \`.tsr\`ファイルは後で文書がその時点に存在したことを証明できます

## 設定

### 設定タブ

1. **TSAを有効化** — TSAサーバーのオン/オフ切り替え
2. **署名CA** — タイムスタンプトークンに署名するCAを選択
3. **ポリシーOID** — TSAポリシーのオブジェクト識別子（例：\`1.2.3.4.1\`）、すべてのタイムスタンプレスポンスに含まれます

### 署名CAの選択

署名CAの秘密鍵はすべてのタイムスタンプトークンの署名に使用されます。ベストプラクティス：

- ルートCAではなく、タイムスタンプ専用の**サブCA**を使用
- CA証明書に**id-kp-timeStamping** Extended Key Usage（OID 1.3.6.1.5.5.7.3.8）を含める
- CA証明書に**十分な有効期間**を確保 — タイムスタンプは数年間検証可能である必要があります

### ポリシーOID

ポリシーOIDは、タイムスタンプが発行されるTSAポリシーを識別します。すべての\`TimeStampResp\`に埋め込まれます。

- デフォルト：\`1.2.3.4.1\`（プレースホルダー）
- プロダクション環境では、組織のアーク下でOIDを登録するか、CP/CPSからのものを使用

## 情報タブ

情報タブには以下が表示されます：

- **TSAエンドポイントURL** — クライアント設定用のコピー＆ペースト対応URL
- **使用例** — リクエストの作成、送信、レスポンスの検証のためのOpenSSLコマンド
- **統計** — 処理されたタイムスタンプリクエストの合計（成功と失敗）

## 使用例

### タイムスタンプリクエストの作成

\`\`\`bash
# ファイルをハッシュしてタイムスタンプリクエストを作成
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### TSAにリクエストを送信

\`\`\`bash
# リクエストを送信してタイムスタンプレスポンスを受信
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### タイムスタンプの検証

\`\`\`bash
# タイムスタンプレスポンスを元のファイルに対して検証
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### タイムスタンプ付きコード署名

コード署名時にTSA URLを追加して、証明書の有効期限後も署名が有効であることを保証：

\`\`\`bash
# タイムスタンプ付き署名（osslsigncode）
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# タイムスタンプ付き署名（Windowsのsigntool.exe）
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### PDF文書のタイムスタンプ

\`\`\`bash
# PDFの分離タイムスタンプを作成
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://your-server:8443/tsa -o document.tsr
\`\`\`

## プロトコル詳細

| プロパティ | 値 |
|----------|------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| エンドポイント | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| レスポンスタイプ | \`application/timestamp-reply\` |
| ハッシュアルゴリズム | SHA-256、SHA-384、SHA-512、SHA-1（レガシー） |
| 認証 | なし（パブリックエンドポイント） |
| トランスポート | HTTPまたはHTTPS |

## セキュリティに関する考慮事項

- TSAエンドポイントは**パブリック**です — 認証は不要です（CRL/OCSPと同じ）
- 各タイムスタンプレスポンスはCAキーによって**署名**されます — クライアントは署名を検証して真正性を確認します
- リクエスト作成時には**SHA-256以上**のハッシュアルゴリズムを使用（SHA-1は受け入れられますが推奨されません）
- TSAは元の文書を**見ません** — ハッシュのみが送信されます
- TSAエンドポイントがインターネットに公開されている場合は**レート制限**を検討してください

> 💡 タイムスタンプはコード署名に不可欠です：署名証明書の有効期限後も署名済みソフトウェアが信頼され続けることを保証します。
`
  }
}
