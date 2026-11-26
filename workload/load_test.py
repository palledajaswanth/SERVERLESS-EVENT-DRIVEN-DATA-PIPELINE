from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from common import EVIDENCE_DIR, make_event, project_config, runtime_config, summarize_latencies


async def send_one(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str, event: dict, index: int) -> dict:
    async with semaphore:
        started_ns = time.perf_counter_ns()
        status = 0
        error = ""
        body = ""
        try:
            response = await client.post(url, json=event)
            status = response.status_code
            body = response.text[:500]
        except Exception as exc:
            error = repr(exc)
        elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        return {
            "index": index,
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "status_code": status,
            "latency_ms": round(elapsed_ms, 3),
            "ok": 200 <= status < 300,
            "error": error,
            "response": body,
        }


async def run(url: str, count: int, concurrency: int, seed: int, run_id: str, timeout_s: float) -> tuple[list[dict], float]:
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=max(concurrency * 2, 20), max_keepalive_connections=max(concurrency, 10))
    async with httpx.AsyncClient(timeout=timeout_s, limits=limits) as client:
        started = time.perf_counter()
        tasks = [send_one(client, semaphore, url, make_event(i, seed, run_id), i) for i in range(count)]
        rows = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - started
    return rows, elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["aws", "baseline"], required=True)
    parser.add_argument("--url")
    parser.add_argument("--count", type=int)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    cfg = project_config()
    count = args.count or cfg["default_events"]
    concurrency = args.concurrency or cfg["default_concurrency"]
    seed = args.seed or cfg["seed"]
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{args.target}"

    if args.url:
        url = args.url
    elif args.target == "baseline":
        url = "http://127.0.0.1:8000/events"
    else:
        url = runtime_config()["api_url"]

    started_at = datetime.now(timezone.utc)
    rows, elapsed = asyncio.run(run(url, count, concurrency, seed, run_id, args.timeout))
    ended_at = datetime.now(timezone.utc)
    latencies = [r["latency_ms"] for r in rows if r["ok"]]
    ok = sum(1 for r in rows if r["ok"])
    summary = {
        "target": args.target,
        "url": url,
        "run_id": run_id,
        "seed": seed,
        "count": count,
        "concurrency": concurrency,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "elapsed_seconds": round(elapsed, 6),
        "throughput_events_per_second": round(ok / elapsed, 3) if elapsed else 0,
        "success_count": ok,
        "failure_count": count - ok,
        "error_rate_percent": round((count - ok) * 100 / count, 4) if count else 0,
        **summarize_latencies(latencies),
    }

    run_dir = EVIDENCE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / f"{args.target}_trace.csv"
    summary_path = run_dir / f"{args.target}_summary.json"
    with trace_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["index"])
        writer.writeheader()
        writer.writerows(rows)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"TRACE={trace_path}")
    print(f"SUMMARY={summary_path}")
    return 0 if summary["failure_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
