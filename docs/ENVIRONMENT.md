# 既存Mac環境の記録（移行前）

`configs/environment/mac_reference_20261101.json` は、Issue #1に残る**これまでの実測報告**を転記した参照記録です。Gitへ登録したからといって、ユーザーのMacをこの構成にインストールしたわけではありません。

- Mac M5 Max / 64 GiB / macOS 27.0.1 / 18 CPU
- 既存venvの Python 3.12.14, Genesis 1.4.5, rsl-rl-lib 5.0.0
- Go2 URDFと baseline `model_6500.pt` のSHAをJSONに記録
- 観測45、行動12、制御50 Hz
- 新しい起伏地形のGenesis native接触・歩行は未実施

注意: `requirements-terrain.txt` は**承認地形のNPZ再現用の隔離した依存**です。既存MacのGenesis実行環境を自動的に変更するものではありません。まず `bash scripts/bootstrap_terrain.sh` で地形の原本SHAを確かめ、その後既存Mac venvでGenesis統合テストを実施してください。

Macの既存コード・checkpoint・映像を移す時は、ハッシュ確認、秘密情報、ライセンス、テスト、差分を確認し、原フォルダを削除しないでください。
