# Issue3：下腿接触の診断と6条件再検証

追加PPOは0更新、新checkpointなし。残実験755秒の中で原因診断・6条件の新規単独3視点録画・全decode・Git正本化を優先し、未検証の報酬改修と再学習は省略しました。提出8h＋予備3hを侵食しません。

geom9はFL_calf本体の円筒ではなく、固定jointで統合されたFL_calflower1（半径15.5mm/長30mm）です。URDFの全固定joint変換・記録body quaternion・各関節実角から有限円筒を独立再計算し、承認int16mm地形の三角面支持高と照合しました。c0の積分前15.31sで最小垂直gap約-1.670mm、c1の14.68sで-2.263mm。GJKのpenetrationと整合します。積分後15.32/14.69sには+2.992/+2.656mmへ離れています。力0Nでも名目形状の重なりを無視しません。

各条件の「2サンプル」は同じ1物理時刻の2接触点です。c0の15.32sは制御50Hzにも現れますが、c1の14.69sは物理100Hzだけに現れ、14.68/14.70sの制御ログにはありません。現行学習の非足接触報酬は制御終端だけを見るため、この事象を取り逃す可能性があります。v4の単純な罰則増量を繰り返す根拠とはしません。

native GJK法線は元ログに未保存です。有限円筒128角度×17軸方向点の計算は独立した近似で、native連続mesh/GJKの完全な証明ではありません。力0のsolver能動拘束の因果、制御上の回避可能性は未確定です。追加学習の成功とは書きません。

同じD13550/同じSHAでFLAT c0/c1/c2はA–E合格、ROLLING c0/c1は非足接触FAIL、c2は数値合格。全て20秒、転倒・境界逸脱なし。4/6合格で正式採用保留、F本人確認待ち、heldout未開封です。閾値・45次元観測・URDF・地形・controller・初期条件は不変です。

全6runに個別のside/oblique/overhead、raw/annotatedを保存し、36MP4を全decode。元RGB、K/E、PTS、物理時刻、FK、支持高、接触、モデル不変の監査はPASS。切り貼り・結合・最終編集はしていません。旧動画の再編集もしていません。

結果と個別動画の相対パスはissue3-results.json、隣接substep・関節速度・target・支持足・姿勢はissue3-contact-diagnosis.jsonに保存しています。診断scriptはscripts/diagnose_issue3_contacts.py、詳細native geom表とログはreports/generated/issue3/です。旧6500/D13550/承認NPZのSHAは一致、旧成果物は保全。68単体・回帰試験PASS。

mainは旧f98e4d0がd724228の祖先であることをremote fetch後に独立確認しました。検証済みIssue2成果と本診断をfast-forwardで正本化し、実際のcommit/push/HEADはIssue3コメントで報告します。未達を全合格と誤記せず、Private・Actions・公開・提出設定を変更しません。
