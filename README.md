# Physical AI Course 2026 — Go2 / Genesis / PPO

Mac Apple Siliconの既存Genesis1.4.5環境で、観測45・行動12を維持し、採用6500から単一PPO方策Dを継続学習します。FLATと承認済みROLLING_UNEVENを50:50で収集し、同じactor/critic/Adamを更新します。新センサー・方策切替は使用しません。

## 実測状況

- Issue #1の承認地形native衝突・接触検証と6500基準評価は完了済みです。6500の不整地基準走行は境界逸脱で不合格でした。
- Issue #2で元ローカルを保全して別cloneへ移行し、実PPOスモークと64→128比較を実施しました。
- 128環境の本学習4runで8,000 PPO更新・24,576,000環境stepを実行し、全状態の保存・読戻しを確認しました。独立スモーク/ベンチを含む全更新は結果サマリーへ分離しています。
- 比較候補D13550は平地3/3 A–E合格、不整地1/3合格です。不整地2条件は各2サンプルのFL_calf無荷重接触で不合格のため、正式採用とheldoutは保留です。接触罰則をさらに強めたv4は前進が退行し不採用としました。
- **学習の実行と走行の合格は別です。** 最終数値・不合格・採用判断は[Issue #2](https://github.com/toujit811/Physical-AI-Course-2026-Advanced1-Final-Assignment/issues/2)と`reports/issue2-results.json`に記録します。Fは本人の動画確認待ちです。
- モデル・生ログ・動画はGit対象外です。可動瓦礫の追加学習・Public化・提出は今回行いません。

## 構成

|パス|内容|
|---|---|
|`assets/approved/heightfield.npz`|承認原本の参照データ、約103 KiB|
|`src/go2_ppo/`|controller・native環境・PPO・評価・録画|
|`configs/training/`|混合報酬v1/v2・seed分離|
|`configs/natural-gait.json` / `stage2-uneven.json`|変更しない評価閾値|
|`terrain/rolling_uneven/v1/`|元generator・adapter・SHA検証|
|`manifests/`|移行元ソース・外部モデルの相対パス/SHA|
|`tests/` / `docs/`|可搬な回帰試験・手順|
|`logs/` / `reports/generated/`|モデル・実測・動画・失敗履歴、Git除外|

## 実行

標準Python3.9.6を使わず、既存Python3.12 Genesis venvを指定します。`requirements-macos-arm64.lock.txt`は実行環境の記録で、既存venvを自動更新しません。

```bash
# 手元の実パスを指定する
export GO2_PYTHON="/path/to/existing/venv/bin/python"
export GO2_LEGACY_ROOT="/path/to/preserved/legacy/repository"
export GO2_PARENT="$GO2_LEGACY_ROOT/logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt"

# 地形専用隔離venv。Genesis venvは変更しない
PYTHON_BIN="$GO2_PYTHON" bash scripts/bootstrap_terrain.sh
PYTHONPATH=src "$GO2_PYTHON" -m unittest discover -s tests -v

# 新run名を使用し、既存runを上書きしない
bash scripts/run_mixed_local.sh --name new-smoke64 --checkpoint "$GO2_PARENT" --num-envs 64 --iterations 5 --save-every 5 --max-wall-seconds 300 --reset-check

# 同じcheckpointを両環境で評価。--recordで3視点を保存
PYTHONPATH=src "$GO2_PYTHON" -m go2_ppo.evaluate --checkpoint logs/mixed-d/new-smoke64/policy_final.pt --name new-flat --kind FLAT --condition 2 --record
PYTHONPATH=src "$GO2_PYTHON" -m go2_ppo.evaluate --checkpoint logs/mixed-d/new-smoke64/policy_final.pt --name new-rolling --kind ROLLING_UNEVEN --condition 2 --record
PYTHONPATH=src "$GO2_PYTHON" -m go2_ppo.evidence logs/rolling-native/new-flat logs/rolling-native/new-rolling
```

[Mac手順](docs/SETUP_MAC.md)と[継続学習の条件](docs/MIXED_PPO.md)を参照してください。`native-media/native-side.mp4`が接近した真正側面、斜め・俯瞰は補助映像です。世界距離目盛り・標高配色・Y=0のX–Z断面を備え、t=0から直接撮影します。

## 厳密な地形参照と限界

承認NPZのSHAは`69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`です。Macで元generatorを隔離依存により実行すると、微小な数値差から`b74be40a…`となり厳密ゲートに不合格でした。既定bootstrapはGitに保存した一致原本を検証・配置します。`REGENERATE_TERRAIN=1 bash scripts/bootstrap_terrain.sh`で元生成経路を診断でき、SHAゲートは維持します。再生成の完全一致は未達です。

継続時は全actor/critic/Adamを復元し、RSL5 adaptive LR変数を復元AdamのLRへ同期します。親checkpointにRNG・rollout・simulator全状態がないため元runと同一軌跡の再開は保証しません。他OS・GPU・別バージョンは未検証です。

旧履歴は[Issue #1](https://github.com/toujit811/Physical-AI-Course-2026-Advanced1-Final-Assignment/issues/1)、今回の実測はIssue #2です。元モデル・失敗動画を保全し、Private設定とGitHub Actionsを変更しません。

## 追加の動画・台帳

[動画QA報告](reports/ISSUE2_MEDIA_QA.md)に、60秒比較の構成、旧/新の全件台帳、録画欠測、実転倒と境界逸脱の区別を記載しています。比較は各20秒評価と明示した別試行/過去転倒の編集枠で、30秒連続走行や最終採用を主張しません。
