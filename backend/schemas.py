from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ROI(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_frame(self):
        if self.x + self.width > 1.0001 or self.y + self.height > 1.0001:
            raise ValueError("La ROI debe quedar dentro del frame")
        return self


class AnalysisConfig(BaseModel):
    fps_analysis: float = Field(default=3, ge=1, le=10)
    analysis_width: int = Field(default=640, ge=160, le=1280)
    mog2_history: int = Field(default=500, ge=20, le=2000)
    var_threshold: float = Field(default=16, ge=1, le=100)
    min_blob_area: int = Field(default=300, ge=10, le=100000)
    motion_threshold: int = Field(default=25, ge=1, le=255)
    yolo_conf: float = Field(default=0.4, ge=0.05, le=0.95)
    yolo_iou: float = Field(default=0.5, ge=0.1, le=0.95)
    classes: list[str] = ["person", "car", "truck", "motorcycle", "bicycle"]
    padding_before: float = Field(default=2, ge=0, le=10)
    padding_after: float = Field(default=2, ge=0, le=10)
    merge_gap: float = Field(default=3, ge=0, le=10)
    min_event_duration: float = Field(default=1, ge=0.2, le=5)
    exact_reencode: bool = False
    output_mode: str = Field(default="clips", pattern="^(clips|concat)$")
    save_audit_frames: bool = False
    model_path: str = "models/yolo11n.pt"


class StartRequest(BaseModel):
    video_id: str
    rois: list[ROI] = Field(min_length=1)
    config: AnalysisConfig = AnalysisConfig()


class PreviewRequest(StartRequest):
    seconds: float = Field(default=10, ge=1, le=30)
