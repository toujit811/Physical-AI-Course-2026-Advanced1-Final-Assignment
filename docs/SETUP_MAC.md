# Macでの再構築手順

## 1. リポジトリを別フォルダへ取得

現在のMac上のGenesis・checkpoint・各ログを上書きしないこと。

```bash
git clone https://github.com/toujit811/Physical-AI-Course-2026-Advanced1-Final-Assignment.git
cd Physical-AI-Course-2026-Advanced1-Final-Assignment
git status --short
```

GitHub private repositoryの認証が必要です。既存Macプロジェクトといきなり混合せず、まずクローン先で検証します。

## 2. 承認済み標高データを復元

MacにPython 3.13がある場合の例です。Python 3.12でも依存パッケージが導入できれば実行できますが、**SHA一致は実測で確認**してください。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-terrain.txt
python terrain/rolling_uneven/v1/restore_approved_heightfield.py
python terrain/rolling_uneven/v1/test_genesis_terrain_adapter.py
shasum -a 256 terrain/rolling_uneven/v1/heightfield.npz
```

期待するSHA256: `69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913`

一致しなければ**そのデータを承認済みと扱わず、原因調査する**。Python / NumPy / SciPy のバージョン、NPZ格納順序、保存時の形式を確認してください。高さの統計値が一致することはバイト列一致の代替になりません。

この復元スクリプトはZIPの添付や前チャットのダウンロードに依存せず、Gitに保存された数式から**原NPZの全4配列とバイト列**を再現するものです。SHA照合のため、数式や出力形式を勝手に変更しないこと。

## 3. Genesis地形を既存Go2シーンへ接続

既存MacのGenesis 1.4.5が利用できるPython環境で実施。新しい仮想環境へのGenesisの無断再インストールはしません。

```python
from terrain.rolling_uneven.v1.genesis_terrain_adapter import add_approved_terrain
from pathlib import Path

repo = Path("/absolute/path/to/Physical-AI-Course-2026-Advanced1-Final-Assignment")
heightfield = repo / "terrain/rolling_uneven/v1/heightfield.npz"

# gs.init() 後、scene.build() より前:
terrain, diagnostics = add_approved_terrain(scene, heightfield)
# scene.build(...)
```

- 地形は `gs.morphs.Terrain` を用いる。既存Planeとの二重接地は禁止。
- 45次元観測・既存6500 checkpoint・Go2制御を勝手に変更しない。
- native地形接触・足裏clearance・標高の実測からコリジョンを検証。
- 固定6500の短いdevelopment基準走行を実施し、成功/FAILを分けて記録。
- この段階では **PPO追加学習・heldout・公開・提出はしない**。

Genesis 1.4.5: https://genesis-world.readthedocs.io/en/v1.4.5/user_guide/physics/terrain.html

## 4. Macの既存コード移行について

Macには既存のGo2/Genesisコード、モデル6500、旧FLAT/UNEVEN/RUBBLEのログ・動画があります。現在GitHubに全てアップロード済みとは**扱わない**。

1. ローカルの既存成果物 inventory・ハッシュ・git status を採取。
2. 原ファイルを保全し、コピー先で staged diff を確認。
3. 実装コードは `src/`、設定は `configs/`、テストは `tests/`、正本資料は `terrain/`、報告は `reports/` へ整理。
4. 実データ・既存checkpoint・動画を誤ってpushしない。再配布権/サイズ/秘密情報を確認。
5. 全テスト・native run・旧参照の整合を確認してからcommit/pushする。

## 5. 結果の区別

- Terrain geometry reproduction: SHAと標高一致
- Genesis physics: 衝突/readback/足裏接触が成立
- 6500 baseline: 固定方策の走行が完了し性能計測
- PPO: optimizerが実更新され、新checkpointが生成
- Held-out: 未知seedに対して固定checkpointで最終評価

上記は**別の完了ゲート**です。前段の成功を次段の成功と書かないこと。
