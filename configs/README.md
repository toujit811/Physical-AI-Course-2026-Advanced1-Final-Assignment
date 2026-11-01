# 設定

`natural-gait.json`のFLAT A–Eと`stage2-uneven.json`の既定ゲートを変更せず評価します。`training/mixed-d-v1/v2/v3.json`は学習報酬とseedの版です。変更理由も保存し、評価用地形を緩和しません。新runの有効設定はcheckpoint隣のconfigs.json/cfgs.pklとtraining-config.jsonへ凍結します。

`environment/mac_reference_20261101.json`はremote初期段階の過去参照で、検証状態のfalseはその時点の記録です。今回の実測状態はreports/issue2-results.jsonとIssue #2を参照してください。
