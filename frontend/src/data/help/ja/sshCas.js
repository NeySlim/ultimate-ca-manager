export default {
  helpContent: {
    title: 'SSH認証局',
    subtitle: 'ユーザーおよびホスト認証用のSSH CAを管理',
    overview: 'OpenSSH標準に準拠したSSH認証局を作成・管理します。SSH CAを使用すると、個別の公開鍵を配布する必要がなくなります。サーバーとユーザーがCAを信頼し、CAが署名した証明書でアクセスを許可します。',
    sections: [
      {
        title: 'CAタイプ',
        items: [
          { label: 'User CA', text: 'SSHログイン用のユーザー証明書に署名します。サーバーはこのCAを信頼し、署名された証明書を受け入れます。' },
          { label: 'Host CA', text: 'サーバーのIDを証明するホスト証明書に署名します。クライアントはこのCAを信頼して、正しいサーバーに接続していることを検証します。' },
        ]
      },
      {
        title: '鍵アルゴリズム',
        items: [
          { label: 'Ed25519', text: 'モダンで高速、コンパクトな鍵（256ビット）。新規デプロイに推奨されます。' },
          { label: 'ECDSA P-256 / P-384', text: '楕円曲線鍵、幅広くサポートされています。セキュリティと互換性のバランスに優れています。' },
          { label: 'RSA 2048 / 4096', text: '従来のアルゴリズム。長期間のCAには4096ビットを使用してください。旧システムとの互換性が最も高いです。' },
        ]
      },
      {
        title: 'サーバー設定',
        items: [
          { label: 'セットアップスクリプト', text: 'このCAを信頼するようにsshdを自動設定するPOSIXシェルスクリプトをダウンロードします。主要なLinuxディストリビューションすべてに対応しています。' },
          { label: '手動セットアップ', text: 'CAの公開鍵をコピーし、sshd_configにTrustedUserCAKeys（User CA）またはHostCertificate（Host CA）を追加します。' },
        ]
      },
      {
        title: '鍵失効',
        items: [
          { label: 'KRL (Key Revocation List)', text: '個別の証明書を失効させるためのコンパクトなバイナリ形式。sshd_configのRevokedKeysで設定します。' },
          { label: 'KRLのダウンロード', text: 'CA詳細パネルから現在のKRLファイルをダウンロードします。' },
        ]
      },
    ],
    tips: [
      'ユーザー証明書とホスト証明書には別々のCAを使用してください — 混在させないでください。',
      'Ed25519は速度とセキュリティに優れているため、新規デプロイに推奨されます。',
      'セットアップスクリプトをダウンロードすれば、簡単にサーバーを設定できます — バックアップと検証が自動的に行われます。',
    ],
    warnings: [
      'CAを削除しても、署名済みの証明書は失効しません — 先に証明書を失効させるか、サーバーの信頼設定を更新してください。',
      'CAの秘密鍵が漏洩した場合、そのCAが署名したすべての証明書は信頼できないと見なす必要があります。',
    ],
  },
  helpGuides: {
    title: 'SSH認証局',
    content: `
## 概要

SSH認証局（CA）は、SSH証明書ベース認証の基盤です。個別の公開鍵をすべてのサーバーに配布する代わりに、CAを作成してサーバーがそれを信頼するように設定します。CAが署名した証明書は自動的に受け入れられます。

UCMはOpenSSH証明書形式（RFC 4253 + OpenSSH拡張）をサポートしており、OpenSSH 5.4以降であればサーバーやクライアントに追加ソフトウェアは不要です。

## CAタイプ

### User CA
User CAは**ユーザーをサーバーに対して認証する**証明書に署名します。サーバーがUser CAを信頼している場合、そのCAが署名した有効な証明書を提示するユーザーはログインが許可されます（プリンシパルのマッチングに従います）。

**サーバー設定：**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Host CAは**サーバーをクライアントに対して認証する**証明書に署名します。クライアントがHost CAを信頼していれば、接続先のサーバーが正規のものであることを検証できます。これにより「Trust On First Use」（TOFU）の警告を排除できます。

**クライアント設定：**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## CAの作成

1. **SSH CAの作成**をクリック
2. わかりやすい名前を入力（例：「Production User CA」）
3. CAタイプを選択：**User**または**Host**
4. 鍵アルゴリズムを選択：
   - **Ed25519** — 推奨。高速、コンパクトな鍵、最新のセキュリティ。
   - **ECDSA P-256/P-384** — 互換性とセキュリティのバランスが良好。
   - **RSA 2048/4096** — 最も広い互換性、鍵サイズが大きい。
5. 必要に応じて最大有効期間とデフォルト拡張を設定
6. **作成**をクリック

> 💡 ユーザー証明書とホスト証明書には別々のCAを使用してください。1つのCAを両方の目的に使用しないでください。

## サーバーセットアップ

### 自動セットアップスクリプト

UCMはサーバーを自動設定するPOSIXシェルスクリプトを生成します：

1. CA詳細パネルを開く
2. **セットアップスクリプトのダウンロード**をクリック
3. スクリプトをサーバーに転送
4. 実行：

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

スクリプトの機能：
- OSとinitシステムを検出
- 変更前にsshd_configをバックアップ
- CA公開鍵をインストール
- TrustedUserCAKeys（User CA）またはHostCertificate（Host CA）を追加
- \`sshd -t\`で設定を検証
- 検証が通った場合のみsshdを再起動
- \`--dry-run\`で変更内容をプレビュー可能

### 手動セットアップ

#### User CA
\`\`\`bash
# CA公開鍵をサーバーにコピー
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# sshd_configに追加
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# sshdを再起動
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# サーバーのホスト鍵に署名
# その後、sshd_configに追加：
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## 鍵失効リスト（KRL）

SSH CAは、侵害された証明書を無効化するためのKey Revocation Listをサポートしています：

1. SSH証明書ページから証明書を失効させる
2. CA詳細パネルから更新されたKRLをダウンロード
3. KRLファイルをサーバーに展開：

\`\`\`bash
# sshd_configに追加
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ サーバーがKRLをチェックするように設定されている必要があります。KRLが展開されるまで失効は有効になりません。

## ベストプラクティス

| 項目 | 推奨事項 |
|----------|---------------|
| CAの分離 | ユーザー証明書とホスト証明書には別々のCAを使用 |
| 鍵アルゴリズム | 新規デプロイにはEd25519、レガシー互換性にはRSA 4096 |
| CAの有効期間 | CAは長期間有効に保ち、代わりに短期間の証明書を使用 |
| バックアップ | CAの秘密鍵をエクスポートして安全に保管 |
| プリンシパルマッピング | ワイルドカードではなく、特定のユーザー名にマッピング |
`
  }
}
