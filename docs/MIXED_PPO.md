# 混合PPOの再現条件

## モデルと報酬

`manifests/external-artifacts.json`の6500 SHAと、その隣の`cfgs.pkl`を使います。checkpointは信頼する自分のファイルだけを読み込みます。外部モデルをGitへコピーしません。

初回mixed-v1は旧報酬にworld velocity、横ドリフト、yaw、姿勢、非足接触、関節超過を追加します。mixed-v2はv1中間評価のRL_calf実角超過・calf接触を受け、**学習報酬だけ**に0.1radの関節内側ガード、非足接触ペナルティの強化を加えます。物理・controller・評価閾値は変えません。

```bash
GO2_TRAINING_CONFIG=configs/training/mixed-d-v2.json bash scripts/run_mixed_local.sh --name unique-v2 --checkpoint logs/mixed-d/prior-run/policy_final.pt --num-envs 128 --iterations 2000 --save-every 250 --max-wall-seconds 1200
```

1 PPO更新は24 control step × N環境、5 epochs ×4 minibatches =20 Adam stepです。`iter`は完了更新数（6500からの通算）です。独立ベンチbranchを本学習系譜へ二重加算せず、`parent_sha256`と`infos.cumulative_mixed_env_steps`を追います。

## 環境とreset

Genesis1.4.5では1Scene中の複数Terrainが衝突参照を共有するため、独立したFLAT SceneとROLLING Sceneを連結します。各SceneはN/2環境、obs/reward/done/timeoutの順序をそろえ同一PPOへ渡します。

FLATは旧URDF plane(Z=0)、ROLLINGは承認int16mm(dx0.05m、vscale0.001m、原点−1,−1.3,0)、摩擦1です。Kp20/Kd0.5、RL_calfのみKd1、50Hz/2substeps、遅延1周期、URDFトルク上限、target margin0.12radを維持します。

元のskip_forward resetはnative DOF読戻しが古い状態でした。学習reset後にforwardを実行し、policy順の関節観測へ戻します。他環境pose不変・接触clearを実機確認しました。resetで方策やAdamを初期化しません。

## seedと評価

train62001/62002、validation2101/2102/2103、heldout82001/82002/82003を分離します。validationの初期姿勢と閾値は旧プロトコルです。FLAT A–E、不整地の進行/姿勢/関節入力/非足接触、実転倒/境界逸脱、F本人確認を分けます。

heldoutは選抜SHA固定後だけ生成します。`--kind HELDOUT --selection selection.json --heldout-seed SEED`は固定SHA・未開封seedを確認し先にopened markerを記録します。HELDOUT_ROLLING_V1は承認地形に端で0となる最大5mmの滑らかな別乱数起伏を追加します。承認評価地形は改変せず、未知seedで再調整した結果をheldout成功に数えません。

## 成果と監査

- `logs/mixed-d/RUN/`: source/config、resume/roundtrip audit、iterations CSV/JSONL、TensorBoard、resources CSV、checkpoint、result。
- `logs/rolling-native/RUN/`: physics0.01秒・control0.02秒の測定、接触、設定・source、評価、任意の3視点動画、evidence audit。
- `reports/generated/issue2/`: 失敗・原因調査、試験出力、元成果物の全SHA manifest。

`go2_ppo.evidence`は時刻格子・全値有限・モデル不変・ソースSHA・URDF FK・支持高・接触数、録画時はカメラ行列・距離目盛り・同期・元PNG・MP4全decodeを検証します。証跡PASSは方策合格を意味しません。


mixed-v3はv2の関節改善後も残る横境界逸脱に対しlateral/heading/nonfootの重みを強化し、entropy係数を0.01→0.001に変更します。actor/critic/全Adamを継承し、アルゴリズムはPPOのままです。設定差は`mixed-d-v3.json`に保存します。

`natural_gait`、`stage1_flat`、`stage2_*`、`cpu_parallel_benchmark`は既存の測定・制御ヘルパーとして移行しました。過去のCLIには当時のログ/モデル配置への依存があり、今回のサポートする実行入口は`train`/`evaluate`/`evidence`です。旧CLI再実行が必要な場合は保全された元環境を参照してください。


学習のtilt終了条件は、親cfgのroll/pitch10度から混合学習では45度へ明示変更しました（configs.jsonへ凍結）。承認地形の斜面で学習経験を収集するためで、物理や採点閾値の変更ではありません。評価はFLATのRMS5度/最大10度、不整地のRMS10度/最大20度等の元閾値を保持します。

mixed-v4はD13550の20秒走行成立後に残るFL_calfの無荷重接触各2サンプルを受け、学習用guard0.10→0.15rad、nonfoot-10→-50のみを強化します。1000更新・最大300秒の1回に限定し、元閾値では接触を不合格のまま記録します。

heldout前は`go2_ppo.selection --checkpoint PATH --validations RESULT... --output selection.json`で同一SHA・FLAT/ROLLING各3条件の数値合格を検証して凍結します。未達候補はfreezeで拒否され、未知seedは開封しません。動画Fの人による判定は別に保留されます。


評価CLIの終了コードは0=数値合格（F未判定）、2=TASK_FAIL、1=ERROR/TIMEOUTです。録画要求と実フレームの保存成立も別フィールドです。途中で失敗した学習runは、完了PPO更新数・収集step・更新済みstepを分け、実更新があればlearning_performedを残します。


seed使用記録はselectionの場所に依存しない`.runtime/heldout-registry`へ排他作成します。この記録は試行失敗でも消さないこと。複数cloneを使う場合は`GO2_HELDOUT_REGISTRY`を同じ保全先の絶対パスに設定し、過去の記録を引き継いでください。unitテストはtemp registryを注入し、実heldoutは開封しません。

終了・FLAT A/ROLLING progressは全0.01秒substepの転倒・境界逸脱を保持します。0.02秒control時点へ回復しても合格に戻しません。閾値は据え置き、既存のcontrolから計算する歩容C/Dも変更しません。
