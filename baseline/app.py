import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("BASELINE_DB", "/data/events.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = _conn()
    conn.close()
    yield


app = FastAPI(title="Always-On Baseline", version="1.0.0", lifespan=lifespan)


class Event(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=100)
    timestamp: str
    value: float
    source: str = "simulator"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          event_type TEXT NOT NULL,
          timestamp TEXT NOT NULL,
          value REAL NOT NULL,
          source TEXT NOT NULL,
          stored_at TEXT NOT NULL
        )
        """
    )
    return conn


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "always-on-baseline"}


@app.get("/stats")
def stats() -> dict:
    conn = _conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"ok": True, "events": count}
    finally:
        conn.close()


@app.post("/events", status_code=202)
def ingest(event: Event) -> dict:
    if event.value < -1_000_000 or event.value > 1_000_000:
        raise HTTPException(status_code=422, detail="value_out_of_range")
    conn = _conn()
    try:
        with _lock:
            before = conn.total_changes
            conn.execute(
                "INSERT OR IGNORE INTO events(event_id,event_type,timestamp,value,source,stored_at) VALUES(?,?,?,?,?,?)",
                (
                    event.event_id,
                    event.event_type,
                    event.timestamp,
                    event.value,
                    event.source,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            inserted = conn.total_changes > before
        return {"ok": True, "status": "stored" if inserted else "duplicate", "event_id": event.event_id}
    finally:
        conn.close()
