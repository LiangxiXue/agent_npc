from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.memory_jobs import process_pending_memory_jobs  # noqa: E402
from src.storage import database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued long-term memory jobs.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    results = process_pending_memory_jobs(limit=args.limit)
    print(
        json.dumps(
            {
                "processed": len(results),
                "jobs": [
                    {
                        "id": job["id"],
                        "npc_id": job["npc_id"],
                        "status": job["status"],
                        "memory_writes": len(job.get("memory_writes", [])),
                        "embedding_updates": len(job.get("embedding_updates", [])),
                        "error": job.get("error", ""),
                    }
                    for job in results
                ],
                "counts": database.get_memory_job_counts(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
