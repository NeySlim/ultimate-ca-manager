export default {
  helpContent: {
    title: '証明書テンプレート',
    subtitle: '再利用可能な証明書プロファイル',
    overview: 'サブジェクトフィールド、Key Usage、Extended Key Usage、有効期間、その他の拡張が事前設定された再利用可能な証明書プロファイルを定義します。証明書の発行または署名時にテンプレートを適用します。',
    sections: [
      {
        title: 'テンプレートタイプ',
        definitions: [
          { term: 'エンドエンティティ', description: 'サーバー、クライアント、コード署名、メール証明書用' },
          { term: 'CA', description: '中間CA作成用' },
        ]
      },
      {
        title: '機能',
        items: [
          { label: 'サブジェクトデフォルト', text: '組織、OU、国、都道府県、市区町村を事前入力' },
          { label: 'Key Usage', text: 'Digital Signature、Key Enciphermentなど' },
          { label: 'Extended Key Usage', text: 'Server Auth、Client Auth、Code Signing、Email Protection' },
          { label: '有効期間', text: 'デフォルトの有効期間（日数）' },
          { label: '複製', text: '既存のテンプレートをクローンして修正' },
          { label: 'インポート/エクスポート', text: 'UCMインスタンス間でテンプレートをJSONファイルとして共有' },
        ]
      },
    ],
    tips: [
      'TLSサーバー、クライアント、コード署名用に別々のテンプレートを作成してください',
      '複製アクションを使用してテンプレートのバリエーションをすばやく作成できます',
    ],
  },
  helpGuides: {
    title: '証明書テンプレート',
    content: `
## 概要

テンプレートは再利用可能な証明書プロファイルを定義します。毎回Key Usage、Extended Key Usage、有効期間、サブジェクトフィールドを手動で設定する代わりに、テンプレートを適用してすべてを事前入力します。

## テンプレートタイプ

### エンドエンティティテンプレート
サーバー証明書、クライアント証明書、コード署名、メール保護用。これらのテンプレートは通常以下を設定します：
- **Key Usage** — Digital Signature、Key Encipherment
- **Extended Key Usage** — Server Auth、Client Auth、Code Signing、Email Protection

### CAテンプレート
中間CA作成用。以下を設定します：
- **Key Usage** — Certificate Sign、CRL Sign
- **Basic Constraints** — CA:TRUE、オプションのパス長

## テンプレートの作成

1. **テンプレートを作成**をクリック
2. **名前**とオプションの説明を入力
3. テンプレート**タイプ**を選択（エンドエンティティまたはCA）
4. **サブジェクトデフォルト**を設定（O、OU、C、ST、L）
5. **Key Usage**フラグを選択
6. **Extended Key Usage**値を選択
7. **デフォルト有効期間**を日数で設定
8. **作成**をクリック

## テンプレートの使用

証明書の発行またはCSRの署名時に、ドロップダウンからテンプレートを選択します。テンプレートは以下を事前入力します：
- サブジェクトフィールド（上書き可能）
- Key UsageとExtended Key Usage
- 有効期間

## テンプレートの複製

**複製**をクリックして既存のテンプレートのコピーを作成します。元のテンプレートに影響を与えずにコピーを修正できます。

## インポートとエクスポート

### エクスポート
UCMインスタンス間で共有するためにテンプレートをJSONとしてエクスポート。

### インポート
以下からインポート：
- **JSONファイル** — テンプレートJSONファイルをアップロード
- **JSON貼り付け** — テキストエリアにJSONを直接貼り付け

## 一般的なテンプレート例

### TLSサーバー
- Key Usage: Digital Signature、Key Encipherment
- Extended Key Usage: Server Authentication
- 有効期間: 365日

### クライアント認証
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- 有効期間: 365日

### コード署名
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- 有効期間: 365日
`
  }
}
