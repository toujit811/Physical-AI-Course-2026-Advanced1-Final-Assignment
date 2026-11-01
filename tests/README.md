# 検証

`PYTHONPATH=src "$GO2_PYTHON" -m unittest discover -s tests -v`で可搬な回帰試験を実行します。元テストのpackage importを変更し、録画試験は過去のローカル動画への依存をsynthetic camera/RGB fixtureへ置換しました。元テスト・元素材は削除しません。

`terrain/rolling_uneven/v1/test_genesis_terrain_adapter.py`のオフライン試験も別途実行します。単体テストだけでnative/PPO成功とは扱いません。実PPOスモーク、多環境reset、64/128実測、保存読戻し、学習後同一checkpointの両環境評価、任意動画の全decodeは各runの証跡です。旧Issue #1の281テストを今回の移行suite数へ混ぜて報告しません。
