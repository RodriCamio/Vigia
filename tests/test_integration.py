import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.exporter import export_results


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado")
def test_short_video_generates_clip(tmp_path: Path):
    source = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10",
                    "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
                   check=True, capture_output=True)
    out = tmp_path / "out"
    events = [{"id": 1, "start": .5, "end": 2.0, "duration": 1.5,
               "classes": ["person"], "score": .8}]
    clips = export_results(source, out, events, False, "clips", {"test": True})
    assert clips == ["event_001.mp4"]
    assert (out / clips[0]).stat().st_size > 0
    assert (out / "eventos.csv").exists() and (out / "metadata.json").exists()
