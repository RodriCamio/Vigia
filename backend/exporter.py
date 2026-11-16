from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path


def _cut(source: Path, target: Path, start: float, end: float, exact: bool) -> tuple[str, str | None]:
    common = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end-start:.3f}"]
    copy_cmd = common + ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero", str(target)]
    encode_cmd = common + ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", str(target)]
    cmd = encode_cmd if exact else copy_cmd
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=max(120, int((end-start)*8)))
        return ("reencode" if exact else "stream-copy", None)
    except subprocess.CalledProcessError as exc:
        if exact:
            raise
        subprocess.run(encode_cmd, check=True, capture_output=True, timeout=max(120, int((end-start)*8)))
        return "reencode-fallback", exc.stderr.decode(errors="replace")[-500:]


def export_results(source: Path, output_dir: Path, events: list[dict], exact: bool, mode: str,
                   metadata: dict, progress=None) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    clips, warnings = [], []
    for i, event in enumerate(events, 1):
        name = f"event_{i:03d}.mp4"
        used, warning = _cut(source, output_dir / name, event["start"], event["end"], exact)
        event["file"], event["export_mode"] = name, used
        clips.append(name)
        if warning: warnings.append(f"{name}: stream copy falló; se recodificó el tramo")
        if progress: progress({"phase": "export", "exported": i, "events": len(events)})
    if mode == "concat" and clips:
        concat_file = output_dir / "concat.txt"
        concat_file.write_text("".join(f"file '{name}'\n" for name in clips), encoding="utf-8")
        target = output_dir / "video_recortado.mp4"
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                            "-c", "copy", str(target)], check=True, capture_output=True, timeout=600)
        except subprocess.CalledProcessError:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", str(target)],
                           check=True, capture_output=True, timeout=1200)
        clips.append(target.name)
    with (output_dir / "eventos.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "start", "end", "duration", "classes", "score", "file", "export_mode"])
        writer.writeheader()
        for event in events: writer.writerow({**event, "classes": ";".join(event["classes"])})
    payload = {**metadata, "events": events, "warnings": warnings}
    (output_dir / "metadata.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    archive_base = output_dir.parent / f".{output_dir.name}_resultados"
    archive = Path(shutil.make_archive(str(archive_base), "zip", output_dir))
    archive.replace(output_dir / "resultados.zip")
    return clips
