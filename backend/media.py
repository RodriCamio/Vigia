from __future__ import annotations

import json
import subprocess
from pathlib import Path


def ffprobe(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-show_entries",
           "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,rotation:stream_tags=rotate",
           "-of", "json", str(path)]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    duration = float(data.get("format", {}).get("duration") or 0)
    avg = video.get("avg_frame_rate", "0/1")
    rate = video.get("r_frame_rate", avg)
    def ratio(value: str) -> float:
        a, b = value.split("/"); return float(a) / float(b) if float(b) else 0
    rotation = int(video.get("tags", {}).get("rotate", video.get("rotation", 0)) or 0)
    return {"duration": duration, "size": int(data.get("format", {}).get("size") or path.stat().st_size),
            "format": data.get("format", {}).get("format_name"), "codec": video.get("codec_name"),
            "width": video.get("width"), "height": video.get("height"), "fps": ratio(avg),
            "nominal_fps": ratio(rate), "vfr": abs(ratio(avg) - ratio(rate)) > 0.01, "rotation": rotation}


def extract_reference(path: Path, output: Path, timestamp: float) -> None:
    subprocess.run(["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(path), "-frames:v", "1",
                    "-vf", "scale='min(1280,iw)':-2", str(output)], check=True, capture_output=True, timeout=120)
