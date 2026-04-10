from __future__ import annotations

import json
import os
import socket
import time

from .cli import run_masking_job
from .controlplane import claim_next_job, heartbeat_job, init_db, record_audit_event, update_job


def run_once(worker_name: str | None = None) -> bool:
    worker_name = worker_name or os.environ.get("DS_WORKER_NAME") or socket.gethostname()
    init_db()
    job = claim_next_job(worker_name)
    if not job:
        return False
    job_id = job["job_id"]
    try:
        heartbeat_job(job_id, worker_name)
        result = run_masking_job(
            config=job["config_path"],
            mode=job.get("mode"),
            tables=job.get("tables") or [],
            verbose=bool(job.get("verbose")),
        )
        update_job(job_id, status="completed", result_json=json.dumps(result, ensure_ascii=False, default=str), error=None)
        record_audit_event("job_complete", job["created_by"], json.dumps({"job_id": job_id, "worker": worker_name, "total_rows": result.get("total_rows", 0)}, ensure_ascii=False))
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
        record_audit_event("job_failed", job["created_by"], json.dumps({"job_id": job_id, "worker": worker_name, "error": str(exc)}, ensure_ascii=False))
    return True


def main() -> int:
    poll_interval = float(os.environ.get("DS_WORKER_POLL_INTERVAL", "2"))
    worker_name = os.environ.get("DS_WORKER_NAME") or socket.gethostname()
    init_db()
    while True:
        found = run_once(worker_name)
        if not found:
            time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
