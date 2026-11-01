# Issue #6 修正結果 — 不整地出口床12m・不整地6本撮り直し

2026-11-02 JST。最新修正指示に従い、不整地の出口床を物理的にX=7mから12mへ延長し、**D13550・再学習なしで不整地c2を新しいnative runで撮り直した**。平地6本は元ファイルを維持。旧不整地の落下動画・停止済み2run・未コミット差分も保全した。

**素材の完成確認PASS：不整地は29.90秒に全4足初回ゴール通過、32.90秒まで3.00秒の実走行を収録。床端落下・転倒・境界逸脱・非足接触・画面外への消失・関節可動域超過・計算異常なし。**

|対象|全4足の初回通過|実収録|ゴール後の実収録|MP4長|フレーム／本|扱い|
|---|---:|---|---|---:|---:|---|
|平地c2|27.56秒|0–30.56秒|27.56–30.56秒、3.00秒|30.60秒|765|既存6本、SHA不変|
|修正版不整地c2|29.90秒|0–32.90秒|29.90–32.90秒、3.00秒|32.96秒|824|新規6本、受入検証PASS|

FINISHはX=6.40mのまま。判定は従来の全4足球の中心X−半径がFINISHを越えた最初の100Hz実測。29.89秒は未通過、29.90秒に通過。0.20秒保持やbase通過を追加条件にせず、余走終了をゴール時刻にしていない。

## 物理修正と実測

- 元の承認NPZ（161×53、X=−1..7m）は上書きせず、承認済み凹凸・開始位置・高さ・Y幅・摩擦・URDF・制御・seed／初期姿勢を保持。実行時にゼロ標高の100行を加え、Genesisの衝突するTerrainを261×53、X=−1..12mへ拡張した。隣接するX=7m行も高さ0で段差なし。見た目だけの床ではない。
- 新runの`terrain-source-and-quantized.npz`で元の161行のint16 mm／元の浮動小数標高が承認データに完全一致し、追加部は高さ0。元NPZ SHA=`69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`不変。
- 衝突境界監視は新しい床端に一致（base X<11.95m、足球中心X<=12m）。既存Y監視を維持。元の7mコースを使う既存モードの境界は変えない。
- Native Terrain頂点はX=12mまで存在。実query40,873点、整数heightfield誤差0、metre読戻し最大誤差1.526e−8m、query最大誤差1.085e−7m。追加床上X>7mで実際の正荷重の足裏接触が最終時刻近くまで続くことを確認。
- Go2＋Terrainの物理entity2体、観測45次元、D13550、Kp20／通常Kd0.5・RL_calf Kd1.0、URDFトルク・可動域制約は保持。旧runとゴールまでの全物理ログ・初期qpos・effective cfg・制御・solver設定が完全一致。PPO更新0・heldoutなし。

ゴール後3秒の不整地の実測範囲：

|項目|最小|最大|
|---|---:|---:|
|本体X（m）|6.719521|7.340142|
|本体Y（m）|0.159996|0.573517|
|本体高さ（m）|0.310622|0.332848|
|地表から本体高さ（m）|0.310622|0.332848|
|roll（度）|1.147754|8.420717|
|pitch（度）|-3.260388|-0.208506|
|関節可動域超過（rad）|0.000000|0.000000|

32.90秒の本体位置は(7.340142, 0.573517, 0.327952)m。旧落下runの同時刻Z=−19.972263mに対し、修正版は床上で歩行を継続。全区間で非足接触0、可動域最大超過0rad、入力制約PASS、FK最大誤差9.093e−7m。

## 最終納品12本 — フル絶対パス

「対応」は同一run・視点・開始／終了・元RGBの相方ID。各動画は単独MP4。停止済みrun（v1／v2）はこの納品に混ぜていない。

|ID|環境|視点|形式|実収録（sim秒）|MP4秒|対応|実在する絶対パス|
|---|---|---|---|---|---:|---|---|
|V01|平地・既存維持|真正側面90°|raw|0–30.56|30.60|V02|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-side-raw.mp4`|
|V02|平地・既存維持|真正側面90°|standard|0–30.56|30.60|V01|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-side.mp4`|
|V03|平地・既存維持|斜め|raw|0–30.56|30.60|V04|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-oblique-raw.mp4`|
|V04|平地・既存維持|斜め|standard|0–30.56|30.60|V03|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-oblique.mp4`|
|V05|平地・既存維持|俯瞰|raw|0–30.56|30.60|V06|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-overhead-raw.mp4`|
|V06|平地・既存維持|俯瞰|standard|0–30.56|30.60|V05|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-overhead.mp4`|
|V07|不整地・床12m修正版|真正側面90°|raw|0–32.90|32.96|V08|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/native-side-raw.mp4`|
|V08|不整地・床12m修正版|真正側面90°|standard|0–32.90|32.96|V07|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/standard-final/course-side.mp4`|
|V09|不整地・床12m修正版|斜め|raw|0–32.90|32.96|V10|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/native-oblique-raw.mp4`|
|V10|不整地・床12m修正版|斜め|standard|0–32.90|32.96|V09|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/standard-final/course-oblique.mp4`|
|V11|不整地・床12m修正版|俯瞰|raw|0–32.90|32.96|V12|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/native-overhead-raw.mp4`|
|V12|不整地・床12m修正版|俯瞰|standard|0–32.90|32.96|V11|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3/native-media/standard-final/course-overhead.mp4`|

## 映像・同期・保全の検証

- 全12本を全フレームdecodeし、25fps・1280×720・H.264 High・yuv420p・SDR BT.709・progressive・無音・faststart・実PTSを検証。raw／標準表示のフレーム数と長さが一致。rawは既存方式のnative RGB 640×360→1280×720符号化で、後付けHUDなし。
- 3視点で同じ走行時刻列。各raw PNGのSHA・元フレーム・100Hz位置・表示時刻・標準版のHUD map／timelineを全数照合。先頭／中間／ゴール付近／末尾のdecoded RGBを元画像と比較。標準版のRGB領域へのHUD侵入なし。
- 3視点すべて、全824フレームで本体中心＋4足球中心が画面内。末尾のraw／標準版を実画像で確認し、ロボットが床上に残っていることも確認。真横90°、斜め、俯瞰を個別保存。カメラの姿勢・画角・世界Z固定は旧方式のまま（side FOV60°／Z0.34m、oblique55°／1.12m、overhead55°／3.30m）。K/Eと光軸・up・固定高さを全フレーム実測照合した。
- 上段の世界X目盛りは0.5m刻み／1m表示、固定画面Y=43pxで実K/E投影と一致。下段は実物理のY=0 X–Z断面でX=12mの出口床まで描画。現在位置は実base Xと同期。色は共通viridis0–0.20m、縦表示倍率4。平地の既存表示軸−1..9mは維持し、不整地は実床に合わせ−1..12mとした。この軸範囲差は確認済みで、同一とは報告しない。パネル配置・映像サイズ・配色・撮影方法は共通。
- raw／標準表示とも結果カード0、末尾静止画・ループ・補間・結合・短縮・速度変更なし。最終実snapshotは32.90秒で、25fps格子外のため最終PTS32.92秒に対応。MP4長32.96秒との違いは符号化フレーム幅であり、架空の実走行を加えていない。
- 平地6本は前回報告の全SHAと一致。旧落下動画・停止済みrun・全過去モデル／ログ／PNG・旧報告・元NPZを含む48,260ファイル、3,602,776,721bytesの実行前SHAと実行後SHAが全件一致。既存未コミット5ファイル＋テスト1ファイルとpatchも変更前にバックアップ。
- 121単体・回帰テストPASS（従来118＋床延長3）。12m断面の新テストは修正前FAIL→修正後PASS。既存の床延長差分をレビューして利用し、断面の9m固定と監査queryの旧7m固定を最小修正した。

モデルD13550 SHA256：`5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565`。actor／optimizer／checkpointの不変を確認。旧20秒評価の4/6・c0/c1の既知FAILや正式モデル採用判断は変更していない。Fの主観確認はユーザー待ち。

## 保存物・再現

新run絶対パス：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3`。`states.csv`（100Hz）／`controls.csv`／`contacts.jsonl`／`resources.csv`／`terrain-readback.csv`／`terrain-slopes.csv`／native terrain頂点／derived地形NPZ／config／結果／凍結ソース／全native RGBとカメラmapを保存。標準版ディレクトリにはHUD map、timeline、section-layout、実地形断面CSVを保存。

全12本のSHA・対応・数値・検証結果：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/issue6-runout-results.json`。検証ログとQA静止画・保全manifest・元差分バックアップ：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/generated/issue6-runout-reshoot`。

実走行コマンド（同名runが存在すれば拒否。再実行時は別名を使う）：
```sh
PYTHONPATH=src XDG_CACHE_HOME="$PWD/.cache" NUMBA_CACHE_DIR="$PWD/.cache/numba" MPLCONFIGDIR="$PWD/.cache/matplotlib" "$PY" -m go2_ppo.course_native --name issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3 --kind ROLLING_UNEVEN --condition 2 --paired --post-goal-seconds 3 --runout-end-x 12
```
`PY`は既存Genesis1.4.5 venv。新run全処理（native＋表示6本＋decode）は103.366秒。

PPO再学習・heldout・瓦礫・公開・提出・Actions・公開設定変更は行っていない。平地は再走行・再生成していない。専用ブランチ`issue6/uneven-runout12-reshoot`へ検証済みコード・テスト・軽量結果だけを反映し、mainを変更しない。

今回の床端落下の未達は解消。残る確認はユーザーによるFの主観的な映像確認であり、これを合格済みとはしない。結果報告後に停止する。

最終の別コンテキストレビュー：重大・重要指摘なし。軽微な残事項はcode-port manifestの説明文に床延長の記述が不足している点（実装SHA・仕様・本報告は一致し、今回の物理・映像検証に影響なし）。この記述整理は今回追加せず、Fの主観確認もユーザー待ちとする。
