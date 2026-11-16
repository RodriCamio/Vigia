from __future__ import annotations

import multiprocessing as mp
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .pipeline import analyze_video


def _worker(source, output, rois, config, queue, cancel, preview_seconds):
    try:
        analyze_video(source, output, rois, config, queue, cancel, preview_seconds)
    except InterruptedError as exc:
        queue.put({"phase": "cancelled", "error": str(exc)})
    except Exception as exc:
        queue.put({"phase": "error", "error": str(exc), "traceback": traceback.format_exc()})


@dataclass
class Job:
    id: str
    process: mp.Process
    queue: mp.Queue
    cancel: mp.Event
    state: dict = field(default_factory=lambda: {"phase": "queued", "progress": 0, "logs": []})


class JobManager:
    """Procesos dedicados: aislamiento de torch/FFmpeg y cero bloqueo del event loop web."""
    def __init__(self): self.jobs: dict[str, Job] = {}

    def start(self, source: Path, output: Path, rois: list[dict], config: dict,
              preview_seconds: float | None = None) -> Job:
        ctx = mp.get_context("spawn")
        job_id, queue, cancel = uuid.uuid4().hex, ctx.Queue(), ctx.Event()
        process = ctx.Process(target=_worker, args=(str(source), str(output), rois, config, queue, cancel, preview_seconds), daemon=True)
        job = Job(job_id, process, queue, cancel); self.jobs[job_id] = job
        process.start()
        threading.Thread(target=self._consume, args=(job,), daemon=True).start()
        return job

    @staticmethod
    def _consume(job: Job):
        terminal = {"done", "error", "cancelled"}
        while job.state.get("phase") not in terminal:
            try: update = job.queue.get(timeout=1)
            except Exception:
                if not job.process.is_alive() and job.state.get("phase") not in terminal:
                    job.state.update(phase="error", error=f"Worker terminó con código {job.process.exitcode}")
                    break
                continue
            if "log" in update:
                job.state.setdefault("logs", []).append(update.pop("log"))
                job.state["logs"] = job.state["logs"][-200:]
            job.state.update(update)

    def get(self, job_id: str) -> Job | None: return self.jobs.get(job_id)
