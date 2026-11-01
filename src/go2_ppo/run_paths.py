"""Keep each experiment inside logs and never overwrite an existing run."""
import re
from pathlib import Path


def create_run_dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("Use a simple experiment name: letters, numbers, _, . or -.")
    path = root / name
    path.mkdir(parents=True, exist_ok=False)
    return path
