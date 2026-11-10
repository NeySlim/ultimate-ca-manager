export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
  },
  helpGuides: {
    title: 'ダッシュボード',
    content: `
## 概要

ダッシュボードは中央監視ハブです。カスタマイズ可能なウィジェットを通じて、PKIインフラストラクチャ全体のリアルタイムメトリクス、チャート、アラートを表示します。

## ウィジェット

### 統計カード
次のカウンターを表示：
- **証明書**: すべての証明書（期限切れ・失効済みを含む）
- **CA**: ルートCAと中間CA
- **CSR**: 署名待ちの証明書署名要求
- **ACME**: 登録済みACMEアカウント
- **SSH証明書**: SSH CAがある場合に表示

### 証明書アクティビティ
選択した期間の日ごとに発行・失効・期限切れの証明書数を示す面グラフ。データポイントにカーソルを合わせると正確な数が表示されます。

### ステータス分布
証明書ステータスの内訳を示す円グラフ：
- **有効**: 有効期間内で失効していない
- **期限切れ間近**: 30日以内に期限切れ
- **期限切れ**: 「Not After」の日付を過ぎている
- **失効済み**: 明示的に失効

### 次の有効期限
有効期限が最も近い有効な証明書6件を、日付に関係なくリスト表示。証明書をクリックすると詳細に移動します。

### システムステータス
UCMサービスのヘルス状態を表示：
- ACMEサーバー（有効/無効）
- SCEPサーバー
- ESTプロトコル（有効/無効、割り当てCA）
- CDPカウント付きCRL自動再生成
- OCSPレスポンダー
- TSA、SMTP、Webhook
- 自動更新ステータス

システムヘルスパネルには、WebSocket接続、データベース、API、最終更新時刻も表示されます。

### 最近のアクティビティ
最新の操作のライブフィード：証明書の発行、失効、インポート、ユーザーログイン。WebSocket経由でリアルタイム更新されます。

### 認証局
最新のCAのクイックビュー。それぞれルートまたはSubと表示されます。

### トラストストアの有効期限
有効期限が最も近い信頼済み証明書。

### ACMEアカウント
登録済みACMEクライアントアカウントとオーダー数のリスト。

## カスタマイズ

### ウィジェットの並べ替え
ページヘッダーの**レイアウトを編集**をクリックし、ウィジェットのヘッダーをドラッグして位置を変更します。レイアウトは画面サイズに適応するレスポンシブグリッドを使用しています。

### ウィジェットの表示/非表示
ページヘッダーの**カスタマイズ**（スライダーのアイコン）をクリックし、ウィジェット横の目のアイコンで表示を切り替えます。非表示のウィジェットはセッション間で記憶されます。

### レイアウトの永続化
レイアウトはアカウントではなくブラウザに保存されます。同じブラウザプロファイルからサインインするすべてのアカウントで共有され、別のブラウザではデフォルトのレイアウトから始まります。

## リアルタイム更新
ダッシュボードはWebSocket経由でライブ更新を受信します。手動更新は不要です: 新しい証明書、ステータス変更、アクティビティエントリは自動的に表示されます。

> 💡 サイドバーの緑のドットはWebSocketのライブ接続を示し、切断されると消えます。再接続時にデータが更新されます。
`
  }
}
