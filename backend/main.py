from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .jobs import JobManager
from .media import extract_reference, ffprobe
from .schemas import PreviewRequest, StartRequest

ROOT = Path(__file__).resolve().parents[1]
UPLOADS, OUTPUTS = ROOT / "uploads", ROOT / "outputs"
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)
ALLOWED = {".mp4", ".mkv", ".avi", ".mov", ".ts"}
manager = JobManager()
app = FastAPI(title="Local Video Events", version="0.1.0")


def video_path(video_id: str) -> Path:
    matches = list(UPLOADS.glob(f"{video_id}.*"))
    if not matches: raise HTTPException(404, "Video no encontrado")
    return matches[0]


@app.post("/api/videos")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED: raise HTTPException(400, "Formato no admitido")
    video_id = uuid.uuid4().hex
    target = UPLOADS / f"{video_id}{suffix}"
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(8 * 1024 * 1024): handle.write(chunk)
        meta = await asyncio.to_thread(ffprobe, target)
        ref = UPLOADS / f"{video_id}.jpg"
        await asyncio.to_thread(extract_reference, target, ref, min(1.0, meta["duration"]/2))
        return {"video_id": video_id, "filename": file.filename, "metadata": meta,
                "reference_url": f"/api/videos/{video_id}/frame"}
    except Exception:
        target.unlink(missing_ok=True)
        raise


@app.get("/api/videos/{video_id}/frame")
def reference_frame(video_id: str):
    path = UPLOADS / f"{video_id}.jpg"
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path)


@app.post("/api/jobs")
def start_job(request: StartRequest):
    source = video_path(request.video_id)
    free = shutil.disk_usage(OUTPUTS).free
    estimated = min(source.stat().st_size, int(source.stat().st_size * .5 + 100_000_000))
    if free < estimated: raise HTTPException(507, "Espacio insuficiente para la salida estimada")
    out = OUTPUTS / uuid.uuid4().hex
    job = manager.start(source, out, [r.model_dump() for r in request.rois], request.config.model_dump())
    job.state.update(output_dir=out.name, video_id=request.video_id)
    return {"job_id": job.id}


@app.post("/api/preview")
def preview(request: PreviewRequest):
    source = video_path(request.video_id); out = OUTPUTS / f"preview_{uuid.uuid4().hex}"
    job = manager.start(source, out, [r.model_dump() for r in request.rois], request.config.model_dump(), request.seconds)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = manager.get(job_id)
    if not job: raise HTTPException(404)
    return job.state


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    job = manager.get(job_id)
    if not job: raise HTTPException(404)
    job.cancel.set(); return {"ok": True}


@app.websocket("/api/jobs/{job_id}/ws")
async def job_socket(websocket: WebSocket, job_id: str):
    job = manager.get(job_id)
    if not job: await websocket.close(code=4404); return
    await websocket.accept(); last = None
    try:
        while True:
            payload = json.dumps(job.state, ensure_ascii=False, default=str)
            if payload != last: await websocket.send_text(payload); last = payload
            if job.state.get("phase") in {"done", "error", "cancelled"}: break
            await asyncio.sleep(.5)
    except WebSocketDisconnect: pass


@app.get("/api/results/{folder}/{filename}")
def result_file(folder: str, filename: str):
    if Path(folder).name != folder or Path(filename).name != filename: raise HTTPException(400)
    path = OUTPUTS / folder / filename
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path)


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
