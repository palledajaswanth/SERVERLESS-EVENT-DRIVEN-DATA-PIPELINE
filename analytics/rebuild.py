from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    for script in [ROOT / "analytics" / "sync_s3.py", ROOT / "analytics" / "build_duckdb.py"]:
        result = subprocess.run([sys.executable, str(script)], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
