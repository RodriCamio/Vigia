from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hit:
    timestamp: float
    classes: set[str] = field(default_factory=set)
    score: float = 0.0


def build_events(hits: list[Hit], duration: float, padding_before: float, padding_after: float,
                 merge_gap: float, min_duration: float, sample_period: float) -> list[dict]:
    """Agrupa hits consecutivos, aplica padding, recorta y fusiona solapamientos."""
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: h.timestamp)
    raw: list[list[Hit]] = [[ordered[0]]]
    # Una muestra ausente se tolera; gaps mayores cierran el evento candidato.
    split_gap = max(sample_period * 2.1, merge_gap)
    for hit in ordered[1:]:
        if hit.timestamp - raw[-1][-1].timestamp <= split_gap:
            raw[-1].append(hit)
        else:
            raw.append([hit])

    padded = []
    for group in raw:
        active_duration = group[-1].timestamp - group[0].timestamp + sample_period
        if active_duration < min_duration:
            continue
        start = max(0.0, group[0].timestamp - padding_before)
        end = min(duration, group[-1].timestamp + sample_period + padding_after)
        padded.append({"start": start, "end": end, "classes": set().union(*(h.classes for h in group)),
                       "score": max(h.score for h in group)})

    merged: list[dict] = []
    for event in padded:
        if merged and event["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"] = max(merged[-1]["end"], event["end"])
            merged[-1]["classes"] |= event["classes"]
            merged[-1]["score"] = max(merged[-1]["score"], event["score"])
        else:
            merged.append(event)
    for i, event in enumerate(merged, 1):
        event.update(id=i, duration=round(event["end"] - event["start"], 3),
                     start=round(event["start"], 3), end=round(event["end"], 3),
                     classes=sorted(event["classes"]), score=round(event["score"], 4))
    return merged
