from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "config" / "evidence_contract.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out = ROOT / "evidence" / "claim_to_evidence.csv"
    rows = []
    for item in CONTRACT["claims"]:
        matched = []
        for pattern in item["evidence_globs"]:
            matched.extend(p for p in ROOT.glob(pattern) if p.is_file())
        if matched:
            for p in sorted(set(matched)):
                rows.append({"claim_id": item["claim_id"], "claim": item["claim"], "evidence_file": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(p), "status": "RESOLVED"})
        else:
            rows.append({"claim_id": item["claim_id"], "claim": item["claim"], "evidence_file": "", "sha256": "", "status": "MISSING_EVIDENCE"})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["claim_id", "claim", "evidence_file", "sha256", "status"])
        writer.writeheader(); writer.writerows(rows)
    print(f"CLAIM_MAP={out}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
