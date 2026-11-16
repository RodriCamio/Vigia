from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import av
import cv2
import numpy as np

from .events import Hit, build_events
from .exporter import export_results
from .media import ffprobe
from .schemas import AnalysisConfig, ROI

LOG = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".ultralytics"))


def _resize(frame: np.ndarray, width: int) -> np.ndarray:
    if frame.shape[1] <= width: return frame
    ratio = width / frame.shape[1]
    return cv2.resize(frame, (width, max(1, round(frame.shape[0] * ratio))), interpolation=cv2.INTER_AREA)


def _rotate(frame: np.ndarray, rotation: int) -> np.ndarray:
    normalized = rotation % 360
    if normalized == 90: return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if normalized == 180: return cv2.rotate(frame, cv2.ROTATE_180)
    if normalized == 270: return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def _roi_crops(frame: np.ndarray, rois: list[ROI]):
    h, w = frame.shape[:2]
    for roi in rois:
        x1, y1 = int(roi.x*w), int(roi.y*h)
        x2, y2 = int((roi.x+roi.width)*w), int((roi.y+roi.height)*h)
        if x2 > x1 and y2 > y1: yield frame[y1:y2, x1:x2]


def analyze_video(source: str, output: str, rois_data: list[dict], config_data: dict, queue=None,
                  cancel=None, preview_seconds: float | None = None) -> dict:
    """Cascada de alto rendimiento: PyAV muestreado -> MOG2 barato -> YOLO solo en candidatos."""
    started = time.monotonic(); source_path, output_dir = Path(source), Path(output)
    cfg, rois = AnalysisConfig.model_validate(config_data), [ROI.model_validate(r) for r in rois_data]
    meta = ffprobe(source_path); duration = min(meta["duration"], preview_seconds or meta["duration"])
    emit = (lambda payload: queue.put(payload)) if queue else (lambda payload: None)
    emit({"phase": "loading_model", "progress": 0})
    from ultralytics import YOLO  # import/carga diferida: evita penalizar el arranque de la API
    import torch
    device = 0 if torch.cuda.is_available() else "cpu"
    model_file = Path(cfg.model_path)
    if not model_file.is_absolute(): model_file = Path.cwd() / model_file
    if not model_file.exists():
        raise FileNotFoundError(f"Falta el modelo local {model_file}. Copie allí los pesos YOLO antes de procesar.")
    model = YOLO(str(model_file))
    names = model.names
    allowed_ids = [i for i, name in names.items() if name in cfg.classes]
    emit({"phase": "analyzing", "device": "cuda" if device == 0 else "cpu", "progress": 0})

    # Un MOG2 por ROI evita contaminar modelos de fondo con zonas de tamaños/contenidos distintos.
    subtractors = [cv2.createBackgroundSubtractorMOG2(history=cfg.mog2_history,
                   varThreshold=cfg.var_threshold, detectShadows=True) for _ in rois]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    hits, candidates, sampled, decoded, last_luma = [], 0, 0, 0, None
    next_sample, last_emit = 0.0, 0.0
    container = av.open(str(source_path))
    stream = container.streams.video[0]
    try:
        for avframe in container.decode(stream):
            decoded += 1
            if cancel is not None and cancel.is_set(): raise InterruptedError("Cancelado por el usuario")
            if avframe.pts is None: continue
            timestamp = float(avframe.pts * avframe.time_base)  # VFR: timestamp real, no contador/fps.
            if timestamp > duration: break
            if timestamp + 1e-6 < next_sample: continue
            next_sample = timestamp + 1.0 / cfg.fps_analysis
            sampled += 1
            frame = _resize(_rotate(avframe.to_ndarray(format="bgr24"), meta.get("rotation", 0)), cfg.analysis_width)
            luma = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
            illumination_jump = last_luma is not None and abs(luma-last_luma) > 45
            last_luma = luma
            if illumination_jump:
                emit({"phase": "analyzing", "log": f"Salto de iluminación ignorado en {timestamp:.1f}s"})
                continue
            candidate_crops = []
            for index, crop in enumerate(_roi_crops(frame, rois)):
                # CUELLO 1: morfología por muestra, barata y en ROI reducida; descarta la enorme mayoría.
                mask = subtractors[index].apply(crop)
                _, mask = cv2.threshold(mask, cfg.motion_threshold, 255, cv2.THRESH_BINARY)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if any(cv2.contourArea(c) >= cfg.min_blob_area for c in contours): candidate_crops.append(crop)
            if candidate_crops:
                candidates += 1
                # CUELLO 2 (dominante): inferencia. Solo recibe frames que superaron motion gating.
                results = model.predict(candidate_crops, imgsz=cfg.analysis_width, conf=cfg.yolo_conf,
                                        iou=cfg.yolo_iou, classes=allowed_ids, device=device, verbose=False)
                detected, score = set(), 0.0
                for result in results:
                    if result.boxes is None: continue
                    for cls, conf in zip(result.boxes.cls.cpu().tolist(), result.boxes.conf.cpu().tolist()):
                        detected.add(names[int(cls)]); score = max(score, float(conf))
                if detected: hits.append(Hit(timestamp, detected, score))
            now = time.monotonic()
            if now-last_emit >= 1:
                elapsed, progress = now-started, min(1.0, timestamp/max(duration, .001))
                emit({"phase": "analyzing", "progress": progress, "timestamp": timestamp,
                      "sampled": sampled, "candidates": candidates, "hits": len(hits),
                      "eta": elapsed/progress-elapsed if progress > .001 else None})
                last_emit = now
    except av.error.FFmpegError as exc:
        emit({"phase": "analyzing", "log": f"Video dañado/truncado; se conserva lo procesado: {exc}"})
    finally:
        container.close()

    events = build_events(hits, duration, cfg.padding_before, cfg.padding_after, cfg.merge_gap,
                          cfg.min_event_duration, 1/cfg.fps_analysis)
    clips = []
    if preview_seconds is None:
        clips = export_results(source_path, output_dir, events, cfg.exact_reencode, cfg.output_mode,
                               {"source": source_path.name, "video": meta, "config": cfg.model_dump(),
                                "stats": {"decoded": decoded, "sampled": sampled, "candidates": candidates}}, emit)
    result = {"events": events, "clips": clips, "duration": duration, "elapsed": time.monotonic()-started,
              "stats": {"decoded": decoded, "sampled": sampled, "candidates": candidates, "hits": len(hits)}}
    emit({"phase": "done", "progress": 1, "result": result})
    return result
