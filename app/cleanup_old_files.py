from __future__ import annotations

import time
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    targets = [base_dir / "images", base_dir / "logs"]
    cutoff = time.time() - 24 * 60 * 60

    # To disable exclusion of the logs/temp directory, set this to False.
    EXCLUDE_LOGS_TEMP = True
    excluded_dir = base_dir / "logs" / "temp"

    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*"):
            # If exclusion is enabled, skip files within the excluded directory.
            if EXCLUDE_LOGS_TEMP and excluded_dir in path.parents:
                continue

            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()


if __name__ == "__main__":
    main()
