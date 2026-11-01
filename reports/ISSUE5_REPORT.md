# Issue5：新規native全コース走行

最終優先版は**ROLLING_UNEVEN c2が踏破成功、FLAT c2が未踏破**です。同じD13550でMac Genesis1.4.5 CPUをt=0から終了イベントまで新規に実行しました。元20秒映像の切り抜き・pose再描画・速度変更ではありません。PPO更新0、heldout未開封です。

|最終run|終了sim秒|base X/Y(m)|結果|
|---|---:|---|---|
|FLAT c2 v2|27.33|6.65939 / 0.88222|未踏破：前足がX=7mコース境界を超過|
|ROLLING_UNEVEN c2 v2|30.10|6.74990 / 0.17699|全4足の後端通過29.90s、0.20s保持を確認して踏破成功|

追加した既存条件FLAT c0は21.58sに足先のY方向コース境界逸脱、c1は27.33sにX方向境界逸脱で未踏破でした。いずれも転倒・solver異常・非足接触なし、関節入力安全判定PASSです。失敗を除外していません。これ以上の追加走行は実施しません。

## ゴールと安全判定

承認SHAのNPZを直接検査し、Genesisの整数mm地形では非ゼロ標高がX=0.20〜6.35m、最初の完全平坦な出口がX=6.40mでした。previewの主活動域終端6.00mより後に微小な起伏が残るため、**最初の試験より前にFINISH=6.40mへ固定**しました。地形X終端7.00mまでの余白は0.60mです。地形は変更していません。

成功はbase X>6.40かつ全4足のnative球中心X−native半径0.022m>6.40が0.20秒連続し、転倒・逸脱・計算異常がないことです。足先中心だけではなく球全体の後端を使い、100Hz同一時刻のnative geomとURDF FKを照合しました。初回通過・直前サンプル・各足通過・確認開始/完了・全足実座標を保存しています。最大60sim秒、wall cap900s、直近6sim秒の前進0.10m未満は別の停滞停止です。物理異常は最初の100Hz substepで止め、単発0N非足接触だけを転倒とは扱いません。

コース境界はbase内側X(-0.95,6.95)/Y(-1.25,1.25)、足先中心X[-1,7]/Y[-1.3,1.3]です。**FLATの物理平面は無限ですが、新規比較コースはこの有限レーンです。** 既存20秒FLAT評価を書き換えたものではありません。

FLAT c2の停止時はFL中心X=7.003469m、RR球後端X=6.388553mで、最後の後足は未通過でした。c1も同様にRR後端6.376427mで未達です。0.60mの出口余白に対して旧ログでの最大前後足中心間隔は約0.689mあり、**出口配置と歩容位相の制約**をモデルの転倒・学習失敗と混同しません。成功のためにゴールを前へ動かしたり、境界や0.20秒確認を緩めたりしていません。

不整地c2は全足通過29.90s→確認完了30.10s。完了時の最小足球後端X=6.433798m、転倒・境界逸脱・非足接触・計算異常なし、関節実角超過0です。地形端までの余白は小さいため、出口の安全余裕が十分広いとは主張しません。現行境界は足先中心の範囲判定です。

## 実装・録画・表示不具合の保全

`course_completion.py`が独立した終了判定、`course_native.py`が新規native runner、`course_media.py`が固定Zの直接録画です。既存`evaluate.py`、`rolling_native_evaluate.py`、環境、45次元観測/12行動、URDF、controller、旧20秒ゲートは不変です。RL_calfのKd=1.0、他Kd=0.5、Kp=20、URDF torque、target margin0.12、50Hz制御/100Hz物理を維持しました。旧モデル6500/D13550/不採用v4/承認NPZ/URDFの既知SHA一致を独立確認しました。

初回の優先2runと追加FLAT c0/c1の**v1計4runは、実RGB確認で地表ゲート線が非表示だったため表示QA FAIL**として残しました。Genesis1.4.5の通常カメラが`Mesh.is_marker=True`を除外するためです。外部描画Meshのrender-filter属性だけを変更し、衝突entityを増やさず優先2runをv2で再実行しました。実RGBの開始/終端付近でSTART/FINISHの色を確認し、v1/v2の**全states.csv SHAが完全一致**しました。表示修正による物理変更はありません。

従って新規nativeは**合計6回**です（優先2回＋追加条件2回＋表示修正後の優先2回）。MP4は**36本**（6run×3視点×raw/presentation）。最終優先v2は12本、そのうち提示用6本です。旧Issue4の18本、旧学習/評価成果、失敗したv1も上書きしていません。動画結合・最終編集・公開・提出は行っていません。

sideは世界Y方向からの真正90°、全カメラはworld Z固定です（side0.34m、oblique1.12m、overhead3.30m）。ロボットの実際の上下動やyawは保全しています。実K/Eと逆変換で位置を検証し、全フレームでZ変動1e-6m未満。固定HUDはY=43px、圧縮後の測定変動も1px以内でした。0.5m目盛り/1mラベル、地表START/FINISH、進行/足後端残距離/経過sim秒、実地形Y0断面と現在位置を維持しています。

全動画はt=0の実native RGBから終了イベントまでの全フレームを使います。終了が25fps格子の間なら、最後の実nativeスナップショットを明示して次のvideoPTSへ割り当てます（例、sim30.10sの実像をPTS30.12sに保存）。**そのPTSまで物理が進んだとは記載しません。** 間のpose補間・走行延長・原実フレームの切断はありません。末尾50フレーム/2秒の結果画面はシミュレーション時間外です。

## 検証と残課題

全6runで100Hz状態、50Hz制御、foot位置/FK/支持高、接触、初回通過と連続確認、最初の安全停止、K/E/カメラZ、raw PNG SHA、25fps/1280×720/H.264 High/yuv420p/BT.709/無音/faststart、全デコード・実PTS・フレーム数を独立スクリプトで検証しました。全36MP4を確認し、全6runの**最初の20秒の物理ログが旧同条件と完全一致**、v2は全期間がv1と完全一致です。v1の地表マーカーFAILをPASSへ上書きしていません。

新規16＋従来87＝**103テストPASS**。判定核10件は標準PythonだけでもPASSです。全足後端・base通過・0.20秒・後退で確認リセット・転倒/境界/計算異常優先・欠測/NaN・60秒上限・停滞・カメラZ・途中フレーム欠落・終端snapshot・既存条件のゲート参照・native描画filterの回帰を含みます。構文検証もPASSです。

生成前後の旧保護対象9,736ファイル695,314,553 bytesのSHAは一致。旧台帳も変更していません。Issue3の旧20秒結果は4/6数値合格、ROLLING c0/c1非足FL_calf接触FAILのまま、F本人評価未済、正式採用保留です。新runの踏破成功を旧安全評価の全面合格へ変換していません。

本人による動的視聴・F評価、平地の安全な出口余白に関する設計判断は残っています。再学習・モデル切替・地形延長・heldout・公開・提出は実施していません。主な制約は平地の未踏破と、保全したv1の表示QA FAILです。

## 保存場所・Git・時間

各runは`logs/course-native/issue5-D13550-<kind>-c<condition>-v<version>/`。`states.csv`、`controls.csv`、`contacts.jsonl`、`resources.csv`、`course-config.json`、`config.json`、`result.json`、凍結sourceを保存。`native-media/`に`course-side.mp4`/`course-oblique.mp4`/`course-overhead.mp4`と各`native-<view>-raw.mp4`、raw PNG、frame-map、実camera-map、HUD-map、timeline、validation、開始/中間/末尾/結果画像があります。

全素材索引は`reports/generated/issue5/index.html`、実測CSVは`course-results.csv`、グラフは`course-verification.png`、独立検証は`independent-qa.json`、軽量全結果は`reports/issue5-results.json`です。新native録画の再現CLIは`PYTHONPATH=src python -m go2_ppo.course_native --kind FLAT --condition 2 --name <new-name>`、不整地はkindを`ROLLING_UNEVEN`にします。既存ディレクトリへの上書きを拒否します。通常の固定20秒評価は別モードのままです。

Issue4ブランチdfcadd4を継承し、Issue5は`issue5/native-course-completion`へcommit/pushします。作業中にユーザーが明示承認した**Issue4のdfcadd4だけ**mainへfast-forward済みです（Issue4コメント6558475711、読み戻し一致）。Issue5コードはmainへmergeしません。最終SHAとclean statusはIssue5コメントへ記録します。巨大動画/モデル、Actions、Private設定の変更、Issue1〜4のcloseは行いません。

新規追加作業は13:07:54 UTC開始から実測し、旧負の実験残額を変更せず、別の`reports/generated/issue5/additional-work-ledger.json`へ記録します。旧台帳SHAを保持し、20時間総枠から旧消費と追加実測を差し引いた残量も別計算します。旧提出・予備欄を新たに全額利用できる余裕として主張しません。最終時間とGit結果をIssueへ報告して停止します。
