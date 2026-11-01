#!/usr/bin/env bash
# Deterministic approved terrain setup; does not touch Mac Genesis project or train a policy.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON_BIN:-python3}"
if [[ ! -d "$REPO_ROOT/.venv-terrain" ]]; then
  "$PYTHON" -m venv "$REPO_ROOT/.venv-terrain"
fi
source "$REPO_ROOT/.venv-terrain/bin/activate"
python -m pip install -r "$REPO_ROOT/requirements-terrain.txt"
python "$REPO_ROOT/terrain/rolling_uneven/v1/restore_approved_heightfield.py"
python "$REPO_ROOT/terrain/rolling_uneven/v1/test_genesis_terrain_adapter.py"
echo "Terrain generation/checksum/offline tests PASS; Genesis native is NOT tested."
