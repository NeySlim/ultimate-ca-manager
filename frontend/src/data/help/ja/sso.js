export default {
  helpContent: {
    title: 'シングルサインオン',
    subtitle: 'SAML、OAuth2、LDAP統合',
    overview: 'ユーザーが組織のIDプロバイダーを通じて認証できるようにシングルサインオンを設定します。SAML 2.0、OAuth2/OIDC、LDAPプロトコルをサポートしています。',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'IDプロバイダー', text: 'IDPメタデータURLの設定またはXMLのアップロード' },
          { label: 'SPメタデータURL', text: 'UCMをサービスプロバイダーとして自動設定するためにIDPに提供するURL' },
          { label: 'SP証明書', text: 'メタデータに含まれるUCM HTTPS証明書 — IDPに信頼される必要があり、信頼されない場合メタデータが拒否されます' },
          { label: 'Entity ID', text: 'UCMサービスプロバイダーのエンティティ識別子' },
          { label: 'ACS URL', text: 'Assertion Consumer ServiceコールバックURL' },
          { label: '属性マッピング', text: 'IDP属性をUCMユーザーフィールドにマッピング' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: '認可URL', text: 'OAuth2認可エンドポイント' },
          { label: 'トークンURL', text: 'OAuth2トークンエンドポイント' },
          { label: 'クライアントID/シークレット', text: 'IDPからのOAuth2クライアント資格情報' },
          { label: 'スコープ', text: '要求するOAuth2スコープ（openid、profile、email）' },
          { label: 'ユーザー自動作成', text: '初回SSOログイン時にUCMアカウントを自動的に作成' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'サーバー', text: 'LDAPサーバーのホスト名とポート（389またはSSLの場合636）' },
          { label: 'バインドDN', text: 'LDAPバインド認証のための識別名' },
          { label: 'ベースDN', text: 'ユーザー検索の検索ベース' },
          { label: 'ユーザーフィルター', text: 'ユーザーに一致するLDAPフィルター（例：(uid={username})）' },
          { label: '属性マッピング', text: 'LDAP属性をユーザー名、メール、フルネームにマッピング' },
        ]
      },
    ],
    tips: [
      'ロックアウトを避けるため、まず管理者以外のアカウントでSSOをテストしてください',
      'フォールバックとしてローカル管理者ログインを利用可能に保ってください',
      'ユーザーの一意な識別を確保するためにIDPのメール属性をマッピングしてください',
      'SPメタデータURLを使用してIDPを自動設定してください（SAML）',
      'SAMLメタデータが受け入れられるには、UCM HTTPS証明書がIDPに信頼される必要があります',
    ],
    warnings: [
      'SSOの設定ミスはすべてのユーザーをロックアウトする可能性があります — 常にローカル管理者を保持してください',
    ],
  },
  helpGuides: {
    title: 'シングルサインオン',
    content: `
## 概要

SSOにより、ユーザーは組織のIDプロバイダー（IDP）を使用して認証できるため、UCM専用の資格情報が不要になります。UCMは**SAML 2.0**、**OAuth2/OIDC**、**LDAP**をサポートしています。

## SAML 2.0

### SPメタデータURL

UCMは自動設定のためにIDPに提供できる**サービスプロバイダー（SP）メタデータURL**を提供します：

\`\`\`
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

このURLはSAML 2.0準拠のXMLドキュメントを返します：
- **Entity ID** — UCMのサービスプロバイダー識別子
- **ACS URL** — Assertion Consumer Serviceエンドポイント（HTTP-POST）
- **SLO URL** — Single Logout Serviceエンドポイント
- **署名証明書** — 署名検証用のUCMのHTTPS証明書
- **NameID形式** — 要求される名前識別子の形式

このURLをIDPの「サービスプロバイダーの追加」または「SAMLアプリケーション」設定にコピーしてください。

> ⚠️ **重要:** UCMのHTTPS証明書は**IDPに信頼される**必要があります。IDPが証明書を検証できない場合（例：自己署名またはプライベートCAが発行）、メタデータが無効として拒否されます。UCMのCA証明書をIDPのトラストストアにインポートするか、パブリックに信頼されたCAが署名した証明書を使用してください。

### 設定
1. IDプロバイダーからIDPメタデータURLまたはXMLファイルを取得
2. UCMで**設定 → SSO**に移動
3. **プロバイダーを追加** → SAMLをクリック
4. **IDPメタデータURL**を入力 — UCMがEntity ID、SSO/SLO URL、証明書を自動入力
5. またはIDPメタデータXMLを直接貼り付け
6. **属性マッピング**を設定（ユーザー名、メール、グループ）
7. **保存**して**有効化**をクリック

### 属性マッピング
IDP SAML属性をUCMユーザーフィールドにマッピング：
- \`username\` → UCMユーザー名（必須）
- \`email\` → UCMメール（必須）
- \`groups\` → UCMグループメンバーシップ（オプション）

## OAuth2 / OIDC

### 設定
1. OAuth2/OIDCプロバイダーにUCMをクライアントとして登録
2. **リダイレクトURI**を設定：\`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. **クライアントID**と**クライアントシークレット**をコピー
4. UCMで**設定 → SSO**に移動
5. **プロバイダーを追加** → OAuth2をクリック
6. **認可URL**と**トークンURL**を入力
7. **ユーザー情報URL**を入力（ログイン後のユーザー属性取得用）
8. クライアントIDとシークレットを入力
9. スコープを設定（openid、profile、email）
10. **保存**して**有効化**をクリック

### ユーザー自動作成
有効にすると、初回SSOログイン時にIDP提供の属性を使用して新しいUCMユーザーアカウントが自動的に作成されます。デフォルトのロールが割り当てられます。

## LDAP

### 設定
1. UCMで**設定 → SSO**に移動
2. **プロバイダーを追加** → LDAPをクリック
3. **LDAPサーバー**のホスト名と**ポート**を入力（LDAPは389、LDAPSは636）
4. 暗号化接続のために**SSLを使用**を有効化
5. **バインドDN**と**バインドパスワード**（サービスアカウントの資格情報）を入力
6. **ベースDN**（ユーザー検索の検索ベース）を入力
7. **ユーザーフィルター**を設定（例：\`(uid={username})\`またはADの場合\`(sAMAccountName={username})\`）
8. LDAP属性をマッピング：**ユーザー名**、**メール**、**フルネーム**
9. **接続テスト**をクリックして確認し、**保存**して**有効化**をクリック

### Active Directory
Microsoft Active Directoryの場合：
- ポート：**389**（SSLの場合636）
- ユーザーフィルター：\`(sAMAccountName={username})\`
- ユーザー名属性：\`sAMAccountName\`
- メール属性：\`mail\`
- フルネーム属性：\`displayName\`

## ログインフロー
1. ユーザーがUCMログインページで**SSOでログイン**をクリック（またはLDAP資格情報を入力）
2. SAML/OAuth2の場合：ユーザーはIDPにリダイレクトされ、認証後にリダイレクトバック
3. LDAPの場合：資格情報がLDAPサーバーに対して直接検証される
4. UCMがユーザーアカウントを作成または更新
5. ユーザーがログイン

> ⚠ SSOの設定ミスにより全員がロックアウトされた場合に備え、常に少なくとも1つのローカル管理者アカウントをフォールバックとして保持してください。

> 💡 主要な認証方法にする前に、まず管理者以外のアカウントでSSOをテストしてください。

> 💡 プロバイダーを有効にする前に、**接続テスト**ボタンを使用して設定を確認してください。
`
  }
}
