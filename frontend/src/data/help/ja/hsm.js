export default {
  helpContent: {
    title: 'ハードウェアセキュリティモジュール',
    subtitle: '外部鍵ストレージ',
    overview: 'HSMと統合して秘密鍵を安全に保管します。PKCS#11、AWS CloudHSM、Azure Key Vault、Google Cloud KMS、OpenBao/Vault Transitをサポートしています。',
    sections: [
      {
        title: '対応プロバイダー',
        definitions: [
          { term: 'PKCS#11', description: '業界標準のHSMインターフェース（Thales、Entrust、SoftHSM）' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Servicesクラウドベースのhsm' },
          { term: 'Azure Key Vault', description: 'Microsoft Azureマネージドキーストレージ' },
          { term: 'Google KMS', description: 'Google Cloud鍵管理サービス' },
          { term: 'OpenBao / Vault Transit', description: 'OpenBaoまたはVault Transit Secrets Engineによるサービスとしての鍵管理' },
        ]
      },
      {
        title: 'アクション',
        items: [
          { label: 'プロバイダーの追加', text: 'HSMへの接続を設定（ライブラリパス、資格情報、スロット）' },
          { label: '接続テスト', text: 'HSMが到達可能で資格情報が有効であることを確認。PKCS#11モジュールの場合は、モジュールが報告する情報（ライブラリ、製造元、ライブラリとファームウェアのバージョン）も記録し、プロバイダーのページに表示' },
          { label: '鍵の生成', text: 'HSM上で直接新しいキーペアを作成' },
          { label: 'ステータス', text: 'プロバイダーの接続状態を監視' },
          { label: '認証 (Certification)', text: 'HSM の認証を申告します: Common Criteria EAL 4+、EUCC high、FIPS 140-3 レベル 3、FIPS 140-2 レベル 3、またはその他。空の場合は未申告です。eu-acm コンプライアンスプロファイルは、HSM 裏付けの CA に対して Common Criteria EAL 4+、EUCC high、FIPS 140-3 レベル 3 (2030年12月31日まで) のみを受け付けます' },
          { label: '使用済みの名前 (v2.249)', text: 'OpenBao または Azure Key Vault がすでに保持している名前で鍵を生成すると拒否されます (409)。既存の鍵は鍵同期 (POST /api/v2/hsm/providers/<id>/sync) で取り込んでください' },
          { label: '同時に 1 件の生成 (v2.249)', text: '鍵の生成はプロバイダーごとに順番に実行され、60 秒を過ぎても待機中のものには 409 が返されます。レコードを保存できなかった鍵は HSM から削除されます' },
          { label: 'バックアップ内の PIN (v2.249)', text: 'バックアップには、プロバイダーの PIN またはトークンが、パスワードで保護されたアーカイブ内に平文で含まれるため、別のインストールでも復元できます。別のインストールの鍵でしか開けない値は復元時に破棄され、再入力を求めるログエントリが残ります' },
          { label: 'FIPS モードの SoftHSM (v2.247)', text: 'SoftHSM は検証済みモジュールではないため、FIPS モードでは新しい SoftHSM プロバイダーが拒否されます。テスト用には UCM_FIPS_ALLOW_SOFTHSM=1 で許可できます' },
        ]
      },
      {
        title: 'HSM 裏付けの CA(v2.130+)',
        content: 'プロバイダを構成すれば、CA の秘密鍵を作成時にその HSM にピン留めできます:',
        items: [
          { label: 'Key Storage トグル', text: 'CA 作成フォームで Local(DB 内で暗号化)または HSM を選択。プロバイダ + キーラベルを選択' },
          { label: '署名パス', text: 'その CA の発行・CRL 署名・OCSP 署名はすべて HSM 経由, 鍵は決して外に出ません' },
          { label: 'エクスポート制限', text: 'HSM-CA では PKCS#12、JKS、鍵単独エクスポートは無効(公開証明書 / チェーンのみエクスポート可)' },
          { label: 'CRL と OCSP', text: '両方とも HSM-CA で透過的に動作(HSM 経由で署名)' },
          { label: 'マイグレーション', text: '既存のローカル CA は作成後に HSM へ移動できません, 作成時に選択' },
        ]
      },
      {
        title: 'ML-DSA 鍵',
        content: 'ML-DSA-44、ML-DSA-65、ML-DSA-87（FIPS 204）鍵は、それらで署名できるプロバイダーでのみ利用できます。データ自体に署名するため、ダイジェストは選択しません。',
        items: [
          { label: 'PKCS#11', text: 'ML-DSA メカニズムを備えた PKCS#11 3.2 実装のトークン' },
          { label: 'OpenBao / Vault Transit', text: 'Transit 鍵タイプ mldsa-44、mldsa-65、mldsa-87' },
          { label: 'Google Cloud KMS', text: 'PQ_SIGN_ML_DSA 鍵バージョン。KMS API からマッピングされていますが、サービスに対する検証は未実施です。KMS が署名できるデータは最大 64 KiB のため、それより大きい CRL には署名できません' },
          { label: '利用不可', text: 'Azure Key Vault と AWS CloudHSM のプロバイダーは ML-DSA 鍵を保持せず、FIPS モードではすべてのプロバイダーで ML-DSA が拒否されます' },
        ]
      },

    ],
    tips: [
      '物理HSMをデプロイする前に、テスト用にSoftHSMを使用してください',
      'HSMで生成された鍵はハードウェアを離れることはありません: エクスポートできません',
      'CA署名にHSMプロバイダーを使用する前に接続をテストしてください',
      '本番環境の長寿命ルート CA には HSM 裏付けの鍵保管を優先してください',
    ],
    warnings: [
      '申告された認証はオペレーターによる HSM についての申告であり、UCM はハードウェアを検証しません。eIDAS に準拠したプロファイルは、CA 鍵の保護を確認するためにこの値を参照します',
      'HSMプロバイダーの設定ミスは証明書署名を妨げる可能性があります',
      'HSMへのアクセスを失うと、そこに保存されている鍵へのアクセスも失われます',
    ],
  },
  helpGuides: {
    title: 'ハードウェアセキュリティモジュール',
    content: `
## 概要

ハードウェアセキュリティモジュール（HSM）は暗号鍵の耐タンパー性ストレージを提供します。HSMに保存された秘密鍵はハードウェアを離れることがないため、最高レベルの鍵保護を提供します。

## 対応プロバイダー

### PKCS#11
業界標準のHSMインターフェース。対応デバイス：
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM**（ソフトウェアベース、テスト用）
- 任意のPKCS#11準拠デバイス

> 💡 **Docker**: SoftHSMはDockerイメージにプリインストールされています。初回起動時にデフォルトトークンが自動初期化され、\`SoftHSM-Default\`プロバイダーとして登録されます, すぐに使用できます。FIPSモードではSoftHSMは検証済みモジュールではないため、デフォルトプロバイダーは作成されず、SoftHSMプロバイダーも拒否されます（テスト用に \`UCM_FIPS_ALLOW_SOFTHSM=1\` で許可した場合を除く）。

設定：
- **ライブラリパス**: PKCS#11共有ライブラリ（.so/.dll）へのパス
- **スロット**: HSMスロット番号
- **PIN**: 認証用のユーザーPIN

### AWS CloudHSM
Amazon Web Servicesクラウドベースのhsm：
- **クラスターID**: CloudHSMクラスター識別子
- **トークンラベル**: CloudHSM の PKCS#11 トークンのラベル
- **暗号ユーザー / 暗号パスワード**: UCM がログインに使う暗号ユーザー (CU)。AWS アクセスキーは不要です

### Azure Key Vault
Microsoft Azureマネージドキーストレージ：
- **Vault URL**: Azure Key Vaultエンドポイント
- **テナントID**: Azure ADテナント
- **クライアントID/シークレット**: サービスプリンシパルの資格情報

### Google Cloud KMS
Google Cloud鍵管理サービス：
- **プロジェクト**: GCPプロジェクトID
- **ロケーション**: KMSキーリングのロケーション
- **キーリング**: キーリングの名前
- **資格情報**: サービスアカウントのJSONキー

### OpenBao / Vault Transit
OpenBaoまたはHashiCorp Vault Transit Secrets Engine。鍵はTransit APIを介してリモートで管理されます: PKCS#11ライブラリは不要です。

設定：
- **URL**: サーバーアドレス（例：\`https://openbao.example.com:8200\`）
- **トークン**: 認証トークン
- **マウントパス**: Transitエンジンのマウントポイント（デフォルト：\`transit\`）
- **名前空間**: マルチテナント設定用のオプション名前空間
- **TLS検証をスキップ**: TLS証明書の検証をスキップ（自己署名証明書用）

サポートされている鍵タイプ：
- RSA 2048、3072、4096
- ECDSA P-256、P-384、P-521
- ML-DSA-44、ML-DSA-65、ML-DSA-87（Transit の \`mldsa-*\` 鍵、対応する OpenBao リリースの場合）
- AES-256-GCM（対称）

> 💡 OpenBaoはHashiCorp Vaultのコミュニティフォークです。UCMは両方で動作します。

## プロバイダーの管理

### プロバイダーの追加
1. **プロバイダーを追加**をクリック
2. **プロバイダータイプ**を選択
3. 接続情報を入力
4. **接続テスト**をクリックして検証
5. **保存**をクリック

### 接続テスト
プロバイダーを作成または変更した後は、必ず接続をテストしてください。UCMがHSMと通信して認証できることを確認します。PKCS#11モジュールの場合は、テストでモジュールが報告する情報（ライブラリ、製造元、ライブラリとファームウェアのバージョン）も記録され、プロバイダーのページに表示されます。

### プロバイダーステータス
各プロバイダーには接続ステータスインジケーターが表示されます：
- **接続済み**: HSMが到達可能で認証済み
- **切断**: HSMに到達できない
- **エラー**: 認証または設定の問題

## 鍵管理

### 鍵の生成
1. 接続済みのプロバイダーを選択
2. **鍵を生成**をクリック
3. アルゴリズムを選択（RSA 2048/4096、ECDSA P-256/P-384）
4. 鍵のラベル/エイリアスを入力
5. **生成**をクリック

鍵はHSM上で直接作成されます。UCMは参照のみを保存します。

### ML-DSA 鍵
ML-DSA-44、ML-DSA-65、ML-DSA-87（FIPS 204）は、それらで署名できるプロバイダーでのみ利用できます：
- **PKCS#11**: ML-DSA メカニズムを備えた PKCS#11 3.2 実装のトークン
- **OpenBao / Vault Transit**: 鍵タイプ \`mldsa-44\`、\`mldsa-65\`、\`mldsa-87\`
- **Google Cloud KMS**: \`PQ_SIGN_ML_DSA_*\` 鍵バージョン。KMS API からマッピングされていますが、サービスに対する検証は未実施です。KMS が署名できるデータは最大 64 KiB のため、それより大きい CRL には署名できません

Azure Key Vault と AWS CloudHSM のプロバイダーは ML-DSA 鍵を保持せず、FIPS モードではすべてのプロバイダーで ML-DSA が拒否されます。ML-DSA 鍵はデータ自体に署名するため、ダイジェストは選択しません。

### HSM鍵の使用
CAを作成する際、ソフトウェアキーを生成する代わりにHSMプロバイダーと鍵を選択します。CAの署名操作はHSM上で実行されます。

> ⚠ HSM上で生成された鍵はエクスポートできません。HSMへのアクセスを失うと、鍵も失われます。

> 💡 物理HSMをデプロイする前に、開発とテストにはSoftHSMを使用してください。
`
  }
}
