# 実測Mac環境

Mac M5 Max / 64 GiB / macOS27.0.1 / arm64 / 18 CPU。既存Python3.12.14、Genesis1.4.5、RSL-RL5.0.0、PyTorch2.15を変更せず使用しました。標準Python3.9.6、他OS・GPUは未検証です。

Issue #1で承認地形native衝突・接触を検証済み、Issue #2で2Scene混合PPOと保存・全状態読戻し、同一Dの評価を実施します。過去の移行前記録は`configs/environment/mac_reference_20261101.json`、今回の結果は`reports/issue2-results.json`です。

`requirements-terrain.txt`は地形専用隔離依存です。既存Genesis venvへ上書きしません。学習用環境のlockは`requirements-macos-arm64.lock.txt`、Macの絶対パス・全生ログはGit除外のruntime記録に保全します。
