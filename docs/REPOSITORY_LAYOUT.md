# フォルダと保全

READMEの構成表を正本とします。既存controller・PPO・native計測の依存コードを`src/go2_ppo/`へ移し、package importとroot参照を整合しました。移行元SHA・移行後SHAは`manifests/code-port.json`、旧6500参照は`manifests/external-artifacts.json`です。旧ローカルは別cloneの外に保全します。

承認NPZは約103KiBの自作正本として`assets/approved/`だけをGitに保存します。runtimeコピーやgenerator診断の不一致ファイルはGit除外です。チェックポイント・全学習ログ・生動画・キャッシュ・venv・絶対パスmanifestをcommitしません。

`logs/mixed-d`は学習、`logs/rolling-native`は評価、`reports/generated/issue2`は詳細診断です。旧FLAT/UNEVEN/RUBBLE・失敗runは削除せず、異なるrun名で追記します。小さな数値サマリー・再現コード・テストだけをレビュー・検証後にGitへ反映します。ActionsとPrivate設定は変更しません。
