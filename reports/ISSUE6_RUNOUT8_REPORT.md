# Issue #6 実行結果 — 出口床X=8m・不整地6本撮り直し

2026-11-02 JST。最新指示のX=8mに従い、物理床を元の7mから1mだけ延長し、**終端を厳密にX=8m**とした新規native runで不整地c2の6本を撮り直した。D13550・再学習なし。旧12m版を含め既存成果物は保全し、既存平地6本は変更していない。

**検証PASS：29.90秒に全4足が初回ゴール通過し、32.90秒まで3.00秒の実走行を収録。床端落下・転倒・境界逸脱・画面外への消失なし。非足接触0、関節可動域超過0、計算異常なし。**

|対象|全4足の初回ゴール|実収録|ゴール後の区間|MP4長|フレーム／本|結果|
|---|---:|---|---|---:|---:|---|
|平地c2・既存6本|27.56秒|0–30.56秒|27.56–30.56秒、3秒|30.60秒|765|同じファイル・SHA不変|
|不整地c2・新規8m版6本|29.90秒|0–32.90秒|29.90–32.90秒、3秒|32.96秒|824|落下・転倒・消失なし、素材検証PASS|

FINISH X=6.40m・開始位置・凹凸・観測45次元・controller・seed／初期姿勢・モデルは保持。全4足球の中心X−半径がFINISHを越えた最初の100Hz実測をゴールとし、0.20秒保持やbase通過を追加条件にしていない。ゴール29.90秒と録画終了32.90秒は別の時刻。

## 8m床の物理・余裕の実測

- 元の承認NPZ（161×53、X=−1..7m）を上書きせず、末尾にゼロ標高20行を追加し、181×53・X=−1..8mの衝突するGenesis Terrainとして構築。元161行の整数mm高さ・元浮動小数標高は完全一致。X=7mの継ぎ目も高さ0、追加部も高さ0。
- Native Terrain全頂点の最大X=8mを確認。全28,313点のqueryとheightfield読戻しを照合し、整数誤差0、metre読戻し最大誤差1.526e−8m、query最大誤差1.085e−7m。物理entityはGo2＋Terrainの2体で、12m床や下敷きplaneを残していない。
- 境界監視は新床に整合（base X<7.95m、足球中心X<=8m）、Y監視は既存どおり。新不整地のX–Z断面・目盛りもX=8mで終了。旧平地動画の表示軸−1..9mはそのまま維持し、この表示軸の違いを同一とは扱わない。
- X>7mの新しい床上で正荷重の足裏接触が最終時刻近くまで続いていることを接触ログで確認。描画だけの床延長ではない。
- 全区間で足球の最前端（中心X＋半径）は最大X=7.603501m。床端X=8mまで最小0.396499mの余裕があった。32.90秒の本体位置は(7.340142, 0.573517, 0.327952)m。今回の3秒収録は8m床内で成立。
- 12m版と今回8m版の100Hz状態表3,291行は全項目が完全一致。モデル／制御／solverの変更で成立させたものではない。床の範囲と映像背景・断面は8m版として新規生成した。

ゴール後3秒の実測：

|項目|最小|最大|
|---|---:|---:|
|本体X（m）|6.719521|7.340142|
|本体Y（m）|0.159996|0.573517|
|本体高さ（m）|0.310622|0.332848|
|roll（度）|1.147754|8.420717|
|pitch（度）|-3.260388|-0.208506|
|関節可動域超過（rad）|0.000000|0.000000|

## 最終12本の実在する絶対パス

対応IDは同じ走行・視点・時間範囲・元RGBの相方。V01–V06は従来の平地ファイルをそのまま維持し、V07–V12は今回8m版の新規ファイル。12m版・旧落下版・停止済みrunは今回の納品へ混ぜていない。

|ID|環境|視点|形式|実収録（sim秒）|MP4秒|対応|フル絶対パス|
|---|---|---|---|---|---:|---|---|
|V01|平地・維持|真正側面90°|raw|0–30.56|30.60|V02|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-side-raw.mp4`|
|V02|平地・維持|真正側面90°|standard|0–30.56|30.60|V01|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-side.mp4`|
|V03|平地・維持|斜め|raw|0–30.56|30.60|V04|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-oblique-raw.mp4`|
|V04|平地・維持|斜め|standard|0–30.56|30.60|V03|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-oblique.mp4`|
|V05|平地・維持|俯瞰|raw|0–30.56|30.60|V06|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/native-overhead-raw.mp4`|
|V06|平地・維持|俯瞰|standard|0–30.56|30.60|V05|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-twelve-D13550-FLAT-c2/native-media/standard-final/course-overhead.mp4`|
|V07|不整地・8m新版|真正側面90°|raw|0–32.90|32.96|V08|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/native-side-raw.mp4`|
|V08|不整地・8m新版|真正側面90°|standard|0–32.90|32.96|V07|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/standard-final/course-side.mp4`|
|V09|不整地・8m新版|斜め|raw|0–32.90|32.96|V10|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/native-oblique-raw.mp4`|
|V10|不整地・8m新版|斜め|standard|0–32.90|32.96|V09|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/standard-final/course-oblique.mp4`|
|V11|不整地・8m新版|俯瞰|raw|0–32.90|32.96|V12|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/native-overhead-raw.mp4`|
|V12|不整地・8m新版|俯瞰|standard|0–32.90|32.96|V11|`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1/native-media/standard-final/course-overhead.mp4`|

## 映像・同期・保全・テスト

- 全12本を全フレームdecodeし、1280×720・25fps・H.264 High・yuv420p・SDR BT.709・progressive・無音・faststart・実PTSを検証。rawと標準版のフレーム数／長さ一致。rawは従来方式のnative RGB640×360→1280×720符号化で後付けHUDなし。標準版は別ファイル。
- 各環境のraw／標準版を同一runの実RGBから生成。3視点の時刻列が一致。全フレームのPNG SHA・sim時刻・video PTS・100Hz位置・HUD map／timelineを照合し、各動画の先頭／中間／ゴール付近／末尾のdecoded RGBも元画像と比較。標準版のRGB領域へのHUD侵入なし。
- 新不整地の3視点・全824フレームで本体中心と4足球中心が画面内。末尾の実画像を3視点で確認し、ロボットが床上に残っていることも確認。撮影前に物理を進めずt=0から収録し、ゴール後の実snapshotまで保存。
- 真横90°、斜め、俯瞰は従来と同じカメラ方式。実K/E・pos/lookat/up・FOV・世界Z固定を全数照合。side60°／Z0.34m、oblique55°／1.12m、overhead55°／3.30m。
- 世界X目盛り0.5m刻み・1m表示、画面Y=43px固定を実K/E投影と照合。下段は実地形Y=0のX–Z断面で終端X=8m、現在位置は実base Xと全フレーム同期。共通viridis標高0–0.20m・縦表示倍率4・パネル配置は維持。
- 結合・短縮・速度変更・補間・ループ・結果カード・末尾静止画追加なし。新動画の最終実snapshot32.90秒は25fps格子外のためPTS32.92秒へ対応し、MP4長は32.96秒。実走行を架空に延長していない。
- 平地6本は旧報告の全SHAに一致。旧12m版・旧落下動画・全モデル／過去ログ／PNG／旧報告／承認NPZを含む50,820ファイル、3,842,543,786bytesの保存前後SHAが全件一致。既存ファイルの削除・移動・改名・上書きなし。
- 122単体・回帰テストPASS（従来121＋8m床・境界・断面の新規1）。8m断面のテストは修正前FAIL→修正後PASS。既存の汎用床延長CLIに8mを指定し、断面の9m最小表示だけを修正。独立検証スクリプトは終端／run／保存先を引数化し、旧12m報告を上書きせず8m版へ全検証を適用した。

D13550 SHA256：`5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565`。元NPZ SHA256：`69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`。actor／optimizer／checkpoint不変、PPO更新0、heldoutなし。旧20秒評価やc0/c1の既知FAIL・正式モデル採用判断は変更していない。Fの主観確認はユーザー待ち。

## 保存先・再現

新run：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1`。100Hz状態・制御・接触・資源CSV／JSONL、derived地形NPZ、native頂点、terrain読戻し、config、結果、凍結ソース、全native RGB、カメラ／フレームmap、表示版HUD map／timeline／断面CSVを保存。

全12本のSHA・絶対パス・対応と結果：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/issue6-runout8-results.json`。保存前manifest・テスト／native／独立QAログ・画像・12mとの状態比較：`/Users/toujit811/Documents/ChatGPT/【最終課題】PhysicaAI/issue2-git/reports/generated/issue6-runout8`。

実行コマンド（再実行時は既存出力を守るため別run名を指定）：
```sh
PYTHONPATH=src XDG_CACHE_HOME="$PWD/.cache" NUMBA_CACHE_DIR="$PWD/.cache/numba" MPLCONFIGDIR="$PWD/.cache/matplotlib" "$PY" -m go2_ppo.course_native --name issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1 --kind ROLLING_UNEVEN --condition 2 --paired --post-goal-seconds 3 --runout-end-x 8
PYTHONPATH=src "$PY" scripts/verify_issue6_runout8.py
```
`PY`は既存Genesis1.4.5 venv。新runのnative＋新規6本生成／decodeは104.750秒。

平地の再走行・再生成、追加PPO、heldout、瓦礫、公開・提出、Actions・公開設定変更は行っていない。専用ブランチ`issue6/uneven-runout8-reshoot`へコード・テスト・軽量報告のみを反映し、mainは変更しない。

8m終端とゴール後3秒の素材条件は成立した。主観的な映像確認Fはユーザー待ち。報告後に停止する。

最終の別コンテキストレビューでも重大・重要・軽微の指摘なし。12本の実在／対応、3,291行の状態一致、ゴール29.90秒・終了32.90秒、最大足球前端7.603501m、凍結ソースと実行データの整合も別担当が確認した。主観評価Fの承認はしていない。
