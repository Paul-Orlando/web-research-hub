"""Recompute deterministic metrics for saved eval runs, with no API calls:

    python -m evals.rescore results/2026-10-22.json [more files ...]

Re-parses each stored report with the current metrics.score_run. Judge labels,
guard stats, latency, usage and cost are kept as recorded.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from evals import metrics

EVALS_DIR = Path(__file__).resolve().parent


def rescore(path: Path) -> tuple[int, int]:
    """Rescores `path` in place. Returns (invented URLs before, after)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    before = after = 0
    for run in data["runs"]:
        if run["error"]:
            continue
        old = run["metrics"]
        before += len(old["invented_urls"])
        old.update(metrics.score_run(run["report"], run["results"]))
        after += len(old["invented_urls"])
    data["meta"]["rescored_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return before, after


def main():
    parser = argparse.ArgumentParser(description="Recompute deterministic metrics for saved eval runs")
    parser.add_argument("files", nargs="+", help="results files, relative to evals/")
    args = parser.parse_args()
    for f in args.files:
        before, after = rescore(EVALS_DIR / f)
        print(f"{f}: invented URLs {before} -> {after}")


if __name__ == "__main__":
    main()
