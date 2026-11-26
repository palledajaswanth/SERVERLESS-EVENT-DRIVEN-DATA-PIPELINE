from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDES = {".git", ".venv", ".terraform", "__pycache__", ".pytest_cache"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "evidence" / "evidence_manifest.json"))
    args = parser.parse_args()
    entries = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in EXCLUDES for part in path.parts):
            continue
        rel = path.relative_to(ROOT)
        if str(rel).replace("\\", "/") == "evidence/evidence_manifest.json":
            continue
        entries.append({"path": str(rel).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "SHA-256",
        "files": entries,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"MANIFEST={out} ({len(entries)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
