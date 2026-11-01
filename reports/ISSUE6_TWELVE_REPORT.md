# Issue #6 実行報告 — raw／標準表示の12本（2026-11-02 JST）

最新Issue本文とユーザー指定「ゴール通過後3秒」に従い、Mac Genesis1.4.5 CPUでFLAT c2と承認済みROLLING_UNEVEN c2を新規走行した。D13550は共通で、PPO更新0・heldout実行なし。

**動画12本の生成・形式／同期／全フレームdecode検証は完了。平地はゴール後も転倒なし。不整地はゴール到達後、有限地形の端から逸脱・落下しているため、余走の安全性はFAIL。**

|環境|全4足初回通過（sim秒）|実収録範囲|ゴール後の実収録|MP4長|フレーム／本|結果|
|---|---:|---|---|---:|---:|---|
|FLAT c2|27.56（直前27.55）|0–30.56秒|27.56–30.56秒、3.00秒|30.60秒|765|ゴール到達、転倒・境界逸脱・非足接触・計算異常なし|
|ROLLING_UNEVEN c2|29.90（直前29.89）|0–32.90秒|29.90–32.90秒、3.00秒|32.96秒|824|ゴール到達後、30.18秒境界逸脱、30.50秒非足接触、30.88秒転倒・落下。計算異常なし|

ゴールは従来の幾何（全4足球の中心X−半径 > FINISH X=6.40m）の100Hz初回実測。0.20秒保持やbase通過を条件に追加していない。成功時刻を余走終了時刻へ遅らせていない。

不整地の物理領域はX=−1..7mのまま。地形を延長せず、出口床も追加していない。ゴール前の安全停止条件は維持し、ゴール後3秒は逸脱・転倒の監視と実測を続け、実際の落下を記録した。非有限値・solver・資源・wall異常は引き続き停止対象。32.90秒のbase位置は(8.357950, 0.381596, −19.972263)m。側面は31.16秒、斜めは31.48秒からbase中心が固定Zの画面外となる。俯瞰のbase中心は最後まで投影範囲内。撮影方法は変更していない。

全区間の関節判定：FLAT PASS（最大超過0rad）、UNEVEN FAIL（落下を含む最大超過0.072826469rad）。UNEVENの非足接触52点。可動域閾値0.002radを初めて超えたのは30.96秒のFR_calf_joint、最大は31.86秒のFL_hip_joint=1.120026469rad（URDF上限1.0472rad）で、いずれもゴール・転倒検出後。旧20秒評価の4/6合格やc0/c1の既知FAILを変更・昇格していない。Fはユーザー動画確認待ち。

## 今回の12本（すべて実在するMac絶対パス）

rawと標準表示は各環境の同一run・同一視点・同一開始／終了・同一native RGBを対にした。下表の「対応」は同じ表のID。ファイルは個別保存、結合なし。

|ID|環境|視点|形式|実走行（sim秒）|MP4秒|対応|絶対パス|
|---|---|---|---|---|---:|---|---|
|V01|FLAT|真正側面90°|raw|0–30.56|30.60|V02|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-side-raw.mp4`|
|V02|FLAT|真正側面90°|standard|0–30.56|30.60|V01|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-side.mp4`|
|V03|FLAT|斜め|raw|0–30.56|30.60|V04|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-oblique-raw.mp4`|
|V04|FLAT|斜め|standard|0–30.56|30.60|V03|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-oblique.mp4`|
|V05|FLAT|俯瞰|raw|0–30.56|30.60|V06|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-overhead-raw.mp4`|
|V06|FLAT|俯瞰|standard|0–30.56|30.60|V05|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-overhead.mp4`|
|V07|ROLLING_UNEVEN|真正側面90°|raw|0–32.90|32.96|V08|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/native-side-raw.mp4`|
|V08|ROLLING_UNEVEN|真正側面90°|standard|0–32.90|32.96|V07|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/standard-final/course-side.mp4`|
|V09|ROLLING_UNEVEN|斜め|raw|0–32.90|32.96|V10|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/native-oblique-raw.mp4`|
|V10|ROLLING_UNEVEN|斜め|standard|0–32.90|32.96|V09|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/standard-final/course-oblique.mp4`|
|V11|ROLLING_UNEVEN|俯瞰|raw|0–32.90|32.96|V12|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/native-overhead-raw.mp4`|
|V12|ROLLING_UNEVEN|俯瞰|standard|0–32.90|32.96|V11|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2/native-media/standard-final/course-overhead.mp4`|

## 検証

- 全12本を先頭から末尾までdecode。H.264 High、1280×720、25fps、yuv420p、SDR BT.709、progressive、無音、faststart。rawは640×360のnative RGBを既存方式で1280×720へ拡大して符号化し、後付けHUDなし。scene内の既存START／FINISH線はnative撮影内容に含まれる。
- raw／標準表示で各フレームの元PNG SHA・run・sim時刻・PTSを全数照合。3視点の収録時刻列一致、表示版RGB領域へのHUD侵入なし。全12本のdecodeと各3点のdecoded RGB比較もPASS。
- 末尾結果カード0、静止画・ループ・補間・短縮・速度変更・音楽・結合なし。最後の実snapshotはFLAT30.56秒、UNEVEN32.90秒。UNEVENの最終実snapshotのみ25fps格子外で、video PTS32.92秒へ対応。MP4の1フレーム長と量子化による差を実sim延長とは扱わない。
- カメラの実K/E・pos/lookat/upを全フレーム検証。side真正90°、FOV60°・世界Z0.34m。oblique FOV55°・Z1.12m。overhead FOV55°・Z3.30m。各視点のFOV・intrinsics・固定高さは環境間で一致。obliqueのupは光軸に直交化された実値を検証。
- 上段目盛りは世界Xの0.5m刻み／1m表示、画面Y=43px固定。実K/Eの投影Xと全数照合。下段は実地形Y=0のX–Z断面、0.5m刻み／1m表示、現在base Xと全フレーム同期。共通viridis標高範囲0–0.20m、表示Z倍率4。物理設定・物理縮尺は不変。
- ゴール後の実X=8.358mまで現在位置を表示するため、両環境の断面表示軸を共通X=−1..9mにした。これは表示範囲であり、停止境界や物理地形の拡張ではない。実地形データは−1..7mのみ描画し、その先の高さを捏造・外挿しない。
- 初回FLAT表示版とX上限8mの表示試作は削除・上書きせず保全。採用した表示版は`native-media/standard-final/course-*.mp4`。元rawと物理時系列は再走行・再編集していない。
- 既存224ファイル（モデル・動画・主要数値ログ・旧報告・承認地形）のSHA256が実行前後で一致。両runの既存時系列に重なる全物理値が完全一致、物理build・制御・effective cfgも旧runと一致。新runのsourceスナップショットSHAも照合済み。
- 118単体／回帰テストPASS（既存113＋新規5）。最初のテスト実行はcache環境変数の不足で2 import error、設定後に全件PASS。独立QAの初回はサイズのtuple/list比較誤りで停止したが、検証コードを修正後PASS。これらの失敗ログも保全。

## 保存物・再現

モデルSHA256: `5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565`。承認地形SHA256: `69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`。

各runディレクトリに`states.csv`（100Hz）、`controls.csv`、`contacts.jsonl`、`resources.csv`、`config.json`、`result.json`、`source/`、native RGB全PNG・camera-frame-map・raw動画を保存。`standard-final/`に表示動画・全フレームHUD map／timeline・地形断面CSV・section-layout・render-provenanceを保存。

検証JSON（各動画SHA・全12絶対パス・対応・数値結果）: `/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/issue6-twelve-results.json`。

全テスト・失敗ログ・保存前SHA manifest・QA静止画: `/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/generated/issue6-twelve`。

実走行コマンド（既存名へ再実行せず、新しい`--name`を指定する）:
```sh
PYTHONPATH=src XDG_CACHE_HOME="$PWD/.cache" NUMBA_CACHE_DIR="$PWD/.cache/numba" MPLCONFIGDIR="$PWD/.cache/matplotlib" "$PY" -m go2_ppo.course_native --name <NEW-RUN-NAME> --kind FLAT --condition 2 --paired --post-goal-seconds 3
# 同じ形式で --kind ROLLING_UNEVEN。PYは既存のGenesis1.4.5 venvの絶対パス。
```

今回の最終表示版は、保存済みRGBから`PYTHONPATH=src "$PY" scripts/render_course_standard.py logs/course-native/<run>`で生成。物理再実行0。出力先が既存なら拒否し保全する。

追加PPO・heldout・瓦礫・公開・提出・Actions・公開設定変更は実施しない。mainは変更しない。専用ブランチ`issue6/twelve-paired-recordings`へコード／テスト／軽量報告だけを反映し、大きな動画はGitへ入れない。

残課題は不整地ゴール後の有限地形端からの落下と、それに伴う非足接触・関節超過、F本人確認。今回は修正対象を拡大せず、実映像と結果をそのまま報告して停止する。

最終の別コンテキストレビュー：重大・重要指摘なし。今回の12本に影響しない既知制約として、将来の57秒以降の遅いゴールでは60秒台の外側ループ上限で3秒余走を取り切れない可能性を残す（今回は27.56秒／29.90秒のため影響なし）。動画の主観評価Fはユーザー確認待ち。
