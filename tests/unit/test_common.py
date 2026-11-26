from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workload"))
from common import make_event, percentile


def test_make_event_is_deterministic():
    assert make_event(3, 7, "r") == make_event(3, 7, "r")


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
