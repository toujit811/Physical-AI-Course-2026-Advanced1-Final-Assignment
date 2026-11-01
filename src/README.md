# Go2 / Genesis / PPO source

既存Macローカルの `go2_env.py`、学習・評価スクリプト、接触計測、動画出力などを保全・テストのうえ移行する場所です。Mac側の実装がここに存在するとはまだ主張しません。

- `src/environments/`: FLAT/UNEVEN（将来）
- `src/controllers/`: Go2制御・観測
- `src/training/`: PPO混合継続学習
- `src/evaluation/`: Validation/heldout（最終許可後）
- `src/recording/`: 物理ログ/動画

現在の地形用アダプタは `terrain/rolling_uneven/v1/` に実際のコードとしてあります。
