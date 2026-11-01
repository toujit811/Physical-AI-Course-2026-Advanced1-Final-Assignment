# Issue6：平地c2の人工X境界修正・無編集raw再走行

D13550で平地c2を新規native実行し、**27.56sim秒に全4足がFINISH X=6.40mを通過して終了**しました。前回27.33秒より後も実物理計算を継続しています。再学習0、モデル・seed・初期姿勢・URDF・controller・カメラ方式は不変です。

FLATに存在しない人工X境界だけを除去しました。Y逸脱、不整地の既存境界、転倒、非有限値、engine errorの監視は維持。従来の足球中心X−半径による幾何を維持し、全4足が通過した最初の100Hzサンプルで終了させ、ゴール後0.20秒保持やbase通過の追加条件を課していません。旧20秒評価と旧runは変更していません。履歴再現用の既定0.20秒モードは残し、今回の`--raw-only`モードは保持0秒を明示しています。

27.55秒のRR球後端X=6.398849mは未通過、27.56秒では6.409394mとなりました。同時刻のFL/FR/RL後端は6.998983 / 6.849226 / 6.483604mで、全4足通過を確認。転倒・Y逸脱・非足接触・関節入力異常・計算異常なし。旧runの全物理数値は27.33秒まで一致し、取り除いた境界フラグだけが異なります。

新規runは`logs/course-native/issue6-D13550-FLAT-c2-raw/`。生成MP4はside/oblique/overheadのraw3本だけです。各690実フレーム、25fps、1280×720、H.264 High/BT.709、無音。末尾カード0、後付けHUD0、静止画追加0、結合・短縮・速度変更なし。最後の実nativeフレームは27.56秒、MP4再生時間はフレーム表示幅を含む27.60秒です。

既存の`issue5-D13550-ROLLING_UNEVEN-c2-v2`は再走行していません。3視点rawの既存SHA一致、全decode、PTS、実フレームとの対応を確認しました。両環境のカメラは既存Issue5と同じ姿勢式・画角・intrinsics・世界Z固定（side0.34m / oblique1.12m / overhead3.30m）です。

検証は旧109＋新4＝113単体・回帰PASS、構文PASS。平地で足先X=7/9/100mでもX境界で停止しないこと、Y/不整地監視保持、初回全足通過即終了、rawフレーム増加なしを確認しました。独立scriptは`scripts/verify_issue6.py`、詳細は`reports/generated/issue6/verification.json`、軽量結果は`reports/issue6-results.json`です。新規平地3本＋既存不整地3本を全フレームdecodeし、実K/E・worldZ・PNG SHA・PTS・最後の実フレームを照合。QuickTimeで6本を開いて再生確認しました。F本人評価は別で未済です。

保護対象13,143ファイル877,796,350 bytesのSHAは不変。停止前の未コミット3ファイルとpatchは`reports/generated/issue6/preexisting/`へ内容とSHA付きで保全しました。Issue6に反するY監視除去や足の幾何変更は採用していません。旧素材の削除・移動・改名・上書き、動画索引/ビューア/レイアウト再設計、PPO、heldout、公開・提出は行っていません。

納品6本のフル絶対パスとSHAは`reports/issue6-results.json`およびIssue6コメントに記載します。検証済みコード・テスト・軽量結果のみ`issue6/flat-c2-raw-completion`へcommit/pushし、mainは変更しません。
