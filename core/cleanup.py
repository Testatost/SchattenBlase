from __future__ import annotations

import shutil
from pathlib import Path

from config import CACHE_DIR, CONFIG_DIR, DATA_DIR


def remove_app_data() -> list[Path]:
    removed: list[Path] = []
    for path in [CACHE_DIR, CONFIG_DIR, DATA_DIR]:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(path)
    return removed
