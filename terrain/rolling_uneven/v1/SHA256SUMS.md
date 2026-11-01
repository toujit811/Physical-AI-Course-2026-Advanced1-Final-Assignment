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

## Macでの実測（Issue #1 / #2）

Macの原ZIP/NPZの上記SHA一致とGenesis1.4.5 native衝突・足裏接触はIssue #1で確認済みです。Issue #2のPython3.12.14 / NumPy2.3.5 / SciPy1.17.0隔離venvでは、元復元コードの出力SHAは`b74be40adf6e1f4380623fc8aab9aa433510a82ec396a02fae99e1d98df07a96`となり、厳密ゲートに不合格でした。元generatorの完全一致実績を全Macへ一般化しません。

承認NPZの一致原本を`assets/approved/heightfield.npz`に保存しています。既定bootstrapはこれを厳密確認してruntimeへ配置します。再生成診断は別runへ保存し、承認原本やruntimeコピーを上書きしません。統計値が似ている不一致NPZを承認済みとして使わないこと。
