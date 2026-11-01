#!/usr/bin/env bash
# Deterministic approved terrain setup; does not touch Mac Genesis project or train a policy.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON_BIN:-${GO2_PYTHON:-python3}}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Terrain dependencies require Python >=3.11; set PYTHON_BIN or GO2_PYTHON"'
if [[ ! -d "$REPO_ROOT/.venv-terrain" ]]; then
  "$PYTHON" -m venv "$REPO_ROOT/.venv-terrain"
fi
source "$REPO_ROOT/.venv-terrain/bin/activate"
python -m pip install -r "$REPO_ROOT/requirements-terrain.txt"
if [[ "${REGENERATE_TERRAIN:-0}" == "1" ]]; then
  mkdir -p "$REPO_ROOT/reports/generated"
  DIAGNOSTIC_DIR="$(mktemp -d "$REPO_ROOT/reports/generated/terrain-regeneration.XXXXXX")"
  cp "$REPO_ROOT/terrain/rolling_uneven/v1/restore_approved_heightfield.py" "$DIAGNOSTIC_DIR/"
  # The original generator writes beside __file__. Isolate it so even a strict
  # checksum failure cannot overwrite the already approved runtime target.
  python "$DIAGNOSTIC_DIR/restore_approved_heightfield.py"
else
  PYTHONPATH="$REPO_ROOT/src" python -m go2_ppo.bootstrap_source
fi
python "$REPO_ROOT/terrain/rolling_uneven/v1/test_genesis_terrain_adapter.py"
echo "Terrain reference/checksum/offline tests PASS; this command does not run Genesis native."
