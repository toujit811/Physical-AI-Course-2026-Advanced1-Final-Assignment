# Mac上の実行環境

元ローカルを上書きせず別cloneを作成し、既存Genesis venvを指定します。標準Python3.9.6からの実行は検証していません。今回の実測はPython3.12.14 / Genesis1.4.5 / RSL-RL5.0.0 / PyTorch2.15 / NumPy2.5.4です。

```bash
# 認証済みGitHubへ別の安全なフォルダからclone
# 既存成果物のあるフォルダ内へ直接pullしない

git clone https://github.com/toujit811/Physical-AI-Course-2026-Advanced1-Final-Assignment.git issue2-git
cd issue2-git
export GO2_PYTHON="/path/to/existing/venv/bin/python"
export GO2_LEGACY_ROOT="/path/to/preserved/legacy/repository"
PYTHON_BIN="$GO2_PYTHON" bash scripts/bootstrap_terrain.sh
PYTHONPATH=src "$GO2_PYTHON" -m unittest discover -s tests -v
```

地形bootstrap専用の`.venv-terrain`は`requirements-terrain.txt`だけを導入します。Genesis venvへこの依存を上書きしません。既定bootstrapはtrackedの承認NPZを厳密照合し配置します。元generatorのMac再生成はb74be40a…となり、指定69979149…と一致しませんでした。`REGENERATE_TERRAIN=1`は診断経路であり、不一致を自動承認しません。高さの統計一致はSHAの代替ではありません。

Go2 URDF・meshはインストール済みGenesisのassetsを参照し、Gitへ複製していません。元6500とcfgsは`manifests/external-artifacts.json`に相対パス/SHAを記録しています。全実行例は[README](../README.md)、継続・評価の条件は[MIXED_PPO](MIXED_PPO.md)を参照してください。

Issue #1の地形・足裏接触・6500基準評価を完了済みの前工程として使い、Issue #2では連携スモークの後に実PPO更新へ進みました。地形の成立、学習の実更新、走行の数値合格、動画Fの本人判断、heldoutは別の判定です。

`requirements-macos-arm64.lock.txt`は実測runtimeの凍結記録です。別Macで全依存が同じものを取得できること、GPU、別OS、別バージョンで同じ軌跡が再現することまでは未確認です。既存venvを破棄・更新しないでください。
