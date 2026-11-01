#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GO2_PYTHON:?Set GO2_PYTHON to the existing Genesis venv Python}"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export XDG_CACHE_HOME="$PWD/.cache"
export NUMBA_CACHE_DIR="$PWD/.cache/numba"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
exec "$GO2_PYTHON" -m go2_ppo.train "$@"
