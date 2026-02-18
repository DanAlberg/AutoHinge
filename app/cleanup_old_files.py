from __future__ import annotations

import time
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    targets = [base_dir / "images", base_dir / "logs"]
    cutoff = time.time() - 24 * 60 * 60

    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()


if __name__ == "__main__":
    main()
