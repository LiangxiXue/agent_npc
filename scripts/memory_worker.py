from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.memory_jobs import process_pending_memory_jobs  # noqa: E402
from src.storage import database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously process queued long-term memory jobs.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true", help="Process one batch and exit.")
    args = parser.parse_args()

    database.initialize_database()
    while True:
        jobs = process_pending_memory_jobs(limit=args.limit)
        print(
            json.dumps(
                {
                    "processed": len(jobs),
                    "jobs": [
                        {
                            "id": job["id"],
                            "npc_id": job["npc_id"],
                            "status": job["status"],
                            "memory_writes": len(job.get("memory_writes", [])),
                            "embedding_updates": len(job.get("embedding_updates", [])),
                            "error": job.get("error", ""),
                        }
                        for job in jobs
                    ],
                    "counts": database.get_memory_job_counts(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if args.once:
            return
        if not jobs:
            time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    main()
