# Physical AI Course 2026 — Advanced 1 Final Assignment

Genesis 1.4.5 / Unitree Go2 / PPO の再現可能な研究・実装リポジトリです。

## 現状（重要）

- **承認済み起伏地形**: `terrain/rolling_uneven/v1/` にある生成コードから復元できます。
- **MacのGenesis実走行**: まだ未検証。地形の存在とGo2の走破成功は別です。
- **学習済み6500**: 現時点ではMacローカル保管。GitHubにアップロードしたとは主張しません。
- **追加PPO・未知コース評価**: 未実施。現在の工程は地形復元・物理検証・6500固定基準走行です。
- **開発履歴**: [Issue #1](https://github.com/toujit811/Physical-AI-Course-2026-Advanced1-Final-Assignment/issues/1)に保存されています。

## リポジトリ構成

```text
README.md
.gitignore
requirements-terrain.txt
docs/
  SETUP_MAC.md                 # Mac上の環境復元と原データ検証
  REPOSITORY_LAYOUT.md         # 役割・追加ファイル規則
terrain/
  rolling_uneven/
    v1/
      restore_approved_heightfield.py  # 承認済みheightfield.npzを厳密再生
      genesis_terrain_adapter.py       # Genesisへの地形接続（native未検証）
      test_genesis_terrain_adapter.py  # オフラインテスト
      terrain_metrics.json             # 元プレビューの測定結果
      SHA256SUMS.md                    # 正本ハッシュと取得方法
      heightfield.npz                  # ↑の生成コードでローカル作成（Git除外）
configs/                        # 地形・学習・評価の設定（後続工程）
src/                            # Macから移行するGo2/PPOの実装（後続工程）
tests/                          # 追加の実機・回帰検証（後続工程）
assets/                         # Go2/その他の合法的なソース資産
logs/                           # 各実験でローカル生成、Git管理外
reports/                        # 検証結果・分析（必要なものだけGit管理）
media/                          # 生成動画、通常Git管理外
models/                         # チェックポイント保管、通常Git管理外
```

`src/`、`configs/`、`tests/` などは後続のMacコード移行領域です。元Mac成果物をこの初期コミットで移行したという意味ではありません。無意味な空ファイルは作りません。

## 最初に実行するコマンド

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-terrain.txt
cd terrain/rolling_uneven/v1
python restore_approved_heightfield.py
python test_genesis_terrain_adapter.py
```

`restore_approved_heightfield.py` は生成した `heightfield.npz` のSHA256が承認済み原本と**完全一致しない場合は異常終了**します。参照元の原ZIPや画像を手動で別途探す必要はありません。Generationの数値配列と元NPZの同一性を確認済みです。

## 運用

Gitをコード・正本データの管理場所、Issueを工程指示と検証報告の管理場所とします。旧ログや動画を削除・上書きせず、検証完了後に成果を反映してください。現段階で追加PPO・heldout・GitHub公開設定変更・提出操作は実施しません。
