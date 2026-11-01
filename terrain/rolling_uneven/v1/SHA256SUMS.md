# 承認済み地形の出典とハッシュ

原本アーカイブ（今回の会話で実検証したもの）:

- `physicaai_uneven_genesis_package.zip`
  - SHA256: `f8bc0ec78026a7ce9632bfc240c39de5f38e266be2554a535ca1465185b28069`
- 原ZIP内の `heightfield.npz`
  - SHA256: `69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`
- 原ZIP内の `generate_rolling_terrain.py`
  - SHA256: `863780eec3b169dc767de24e8db37973889cc318c84d3122e26a2f41bd5421ee`
- 原ZIP内の `genesis_terrain_adapter.py`
  - SHA256: `01a77b16586bb6953aa07d8bd17c24cbcc8afbd26c0e62a5694efb83692a53fe`
- 原ZIP内の `test_genesis_terrain_adapter.py`
  - SHA256: `01e689f394cb57f3361843826f8d64e7d3f56977c05bc286a630412469ef17df`
- 原ZIP内の `terrain_metrics.json`
  - SHA256: `c813fc5e01a764ca8039e80b95f18ada3d0433529a8571bf91ca43a54691f5b4`

Git上の `restore_approved_heightfield.py` は上記原generatorと同じNPZを出すための最小化した復元専用コードであり、原generatorのハッシュと同じものではありません。

**検証実績**：検証環境 Python3.13.5 / NumPy2.3.5 / SciPy1.17.0 で生成したNPZ SHA256は承認済み原本と完全一致。原ZIPのテスト2件もPASS。GitHubコード読戻しのblob SHAは検証済みローカルソースと一致。

Macでの検証実績は未取得。復元SHAが一致するまで正式なGenesis地形として使用してはいけません。入力NPZを取得するために前のチャットの添付ファイルを探す必要はありません。
