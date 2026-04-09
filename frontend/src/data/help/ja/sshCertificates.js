export default {
  helpContent: {
    title: 'SSH証明書',
    subtitle: 'OpenSSH証明書の発行と管理',
    overview: 'SSH CAで署名されたSSH証明書を発行します。証明書は手動のauthorized_keys管理を置き換え、時間制限付きでプリンシパルにスコープされた、自動期限切れのアクセス制御を提供します。ユーザー証明書とホスト証明書の両方をサポートしています。',
    sections: [
      {
        title: '発行モード',
        items: [
          { label: '署名モード', text: '既存のSSH公開鍵を貼り付けて署名します。秘密鍵はユーザーのマシンに残ります — UCMは秘密鍵にアクセスしません。' },
          { label: '生成モード', text: 'UCMが新しい鍵ペアを生成して証明書に署名します。秘密鍵はすぐにダウンロードしてください — 後から取得することはできません。' },
        ]
      },
      {
        title: '証明書フィールド',
        items: [
          { label: 'Key ID', text: '証明書の一意識別子。監査のためSSHログに表示されます。' },
          { label: 'Principals', text: 'この証明書が有効なユーザー名（ユーザー証明書）またはホスト名（ホスト証明書）。カンマ区切りで指定します。' },
          { label: '有効期間', text: '証明書の有効期間。プリセット（1h、8h、24h、7d、30d、90d、365d）から選択するか、カスタム秒数を設定します。' },
          { label: 'Extensions', text: 'permit-pty、permit-agent-forwardingなどのSSH拡張。ユーザー証明書にのみ適用されます。' },
          { label: 'Critical Options', text: 'force-commandやsource-addressなどの制限で、証明書の使用範囲を限定します。' },
        ]
      },
      {
        title: '証明書タイプ',
        items: [
          { label: 'ユーザー証明書', text: 'ユーザーをサーバーに対して認証します。サーバーはTrustedUserCAKeysで署名CAを信頼する必要があります。' },
          { label: 'ホスト証明書', text: 'サーバーをクライアントに対して認証します。クライアントはknown_hostsの@cert-authorityでCAを信頼します。' },
        ]
      },
      {
        title: '管理',
        items: [
          { label: '失効', text: '証明書をCAのKey Revocation List（KRL）に追加します。サーバーがKRLをチェックするように設定されている必要があります。' },
          { label: 'ダウンロード', text: '証明書、公開鍵、または秘密鍵（生成モードのみ）をダウンロードします。' },
        ]
      },
    ],
    tips: [
      '鍵の漏洩の影響を最小限にするため、ユーザーアクセスには短期間の証明書（8h〜24h）を使用してください。',
      '署名モードが推奨されます — ユーザーの秘密鍵がマシンから離れることはありません。',
      'Key IDはわかりやすい名前にしてください（例：「jdoe-prod-2025」）。ログ監査が容易になります。',
      'ホスト証明書の場合、プリンシパルはクライアントが接続に使用するホスト名と一致する必要があります。',
    ],
    warnings: [
      '生成モードでは、秘密鍵をすぐにダウンロードしてください — 保存されないため、後から復元できません。',
      '証明書の失効は、サーバーがCAのKRLファイルをチェックするように設定されている場合のみ機能します。',
    ],
  },
  helpGuides: {
    title: 'SSH証明書',
    content: `
## 概要

SSH証明書は、メタデータ付きの署名済みSSH公開鍵です。メタデータにはID、有効期間、許可されたプリンシパル、拡張が含まれます。従来の\`authorized_keys\`方式を、集中管理された時間制限付きの監査可能なアクセス制御に置き換えます。

UCMは、あらゆるプラットフォームのOpenSSH 5.4以降と互換性のあるOpenSSH形式の証明書を発行します。

## 発行モード

### 署名モード（推奨）
ユーザーが自身の鍵ペアを生成し、**公開鍵**のみをUCMに提供します。秘密鍵はユーザーのマシンから離れません。

**ユーザーのワークフロー：**
\`\`\`bash
# 1. 鍵ペアの生成（ユーザーのマシンで）
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. 公開鍵の内容をコピー
cat ~/.ssh/id_work.pub

# 3. UCMの署名フォームに貼り付け
# 4. 署名済み証明書をダウンロード
# 5. ~/.ssh/id_work-cert.pubとして保存

# 6. 接続
ssh -i ~/.ssh/id_work user@server
\`\`\`

### 生成モード
UCMが鍵ペアと証明書の両方を生成します。認証情報を一括でプロビジョニングする必要がある場合に使用します。

> ⚠ **秘密鍵はすぐにダウンロードしてください** — UCMには保存されず、復元できません。

**ワークフロー：**
1. CAを選択し、証明書の詳細を入力
2. 「生成」モードを選択
3. **発行**をクリック
4. 3つのファイルすべてをダウンロード：
   - 秘密鍵（\`keyid\`）— **安全に保管してください！**
   - 証明書（\`keyid-cert.pub\`）
   - 公開鍵（\`keyid.pub\`）

## 証明書フィールド

### Key ID
証明書に埋め込まれた一意識別子です。証明書が使用されるとSSHサーバーログに表示され、監査に不可欠です。

**良いKey IDの例：** \`jdoe-prod-2025\`、\`webserver-01\`、\`deploy-ci-pipeline\`

### Principals
Principalsは証明書が有効な**対象者**（ユーザー証明書）または**対象ホスト**（ホスト証明書）を定義します：

- **ユーザー証明書**：所有者がログインできるユーザー名のリスト（例：\`deploy\`、\`admin\`）
- **ホスト証明書**：サーバーが認識されるホスト名/IPのリスト（例：\`web01.example.com\`、\`10.0.1.5\`）

> 💡 Principalsを指定しない場合、証明書はすべてのプリンシパルに対して有効になります — 通常、権限が広すぎます。

### 有効期間

プリセットから選択するか、カスタム期間を設定します：

| プリセット | 用途 |
|--------|----------|
| 1時間 | CI/CDパイプライン、一時的なタスク |
| 8時間 | 標準的な勤務時間のアクセス |
| 24時間 | 延長アクセス |
| 7日間 | スプリント単位のアクセス |
| 30日間 | 月次ローテーション |
| 365日間 | 長期間のサービスアカウント |

人間のユーザーには短期間の証明書（8h〜24h）が推奨されます。自動化されたサービスアカウントにはより長い有効期間も許容されます。

### Extensions（ユーザー証明書のみ）

| Extension | 説明 |
|-----------|-------------|
| permit-pty | 対話型ターミナルセッションを許可 |
| permit-agent-forwarding | SSHエージェント転送を許可 |
| permit-X11-forwarding | X11ディスプレイ転送を許可 |
| permit-port-forwarding | TCPポート転送を許可 |
| permit-user-rc | ログイン時の~/.ssh/rcの実行を許可 |

### Critical Options

| オプション | 説明 |
|--------|-------------|
| force-command | 証明書を単一のコマンドに制限 |
| source-address | 特定のソースIPアドレス/CIDRに制限 |

**例：** \`force-command=ls\`と\`source-address=10.0.0.0/8\`が設定された証明書は、10.x.x.xネットワークからの\`ls\`コマンドのみ実行できます。

## 証明書の使用

### ユーザー証明書
\`\`\`bash
# 証明書を秘密鍵の横に配置
# 鍵が~/.ssh/id_workの場合、証明書は~/.ssh/id_work-cert.pubにする
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSHが自動的に証明書を使用
ssh user@server
\`\`\`

### ホスト証明書
\`\`\`bash
# サーバー上：ホスト証明書を配置
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# sshd_configに追加
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

クライアント側で、Host CAをknown_hostsに追加：
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## 失効

1. テーブルで証明書を選択
2. 詳細パネルで**失効**をクリック
3. 証明書がCAのKey Revocation List（KRL）に追加される
4. SSH CAページから更新されたKRLをダウンロードしてサーバーに展開

> ⚠ 失効は、サーバーがsshd_configの\`RevokedKeys\`でKRLをチェックしている場合のみ有効です。

## トラブルシューティング

| 問題 | 解決策 |
|-------|----------|
| Permission denied (publickey) | サーバーでCAが信頼されていることを確認（TrustedUserCAKeys） |
| 証明書が使用されない | 証明書ファイルが秘密鍵の横に\`<key>-cert.pub\`という名前で配置されていることを確認 |
| プリンシパルの不一致 | SSHで使用するユーザー名が証明書のPrincipalsに含まれている必要があります |
| 証明書の期限切れ | 適切な有効期間で新しい証明書を発行 |
| ホスト検証の失敗 | Host CAを@cert-authorityでknown_hostsに追加 |
`
  }
}
