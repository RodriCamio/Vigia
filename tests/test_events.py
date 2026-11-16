from backend.events import Hit, build_events


def test_padding_clamping_and_merge():
    hits = [Hit(1.0, {"person"}, .8), Hit(2.0, {"person"}, .9),
            Hit(4.0, {"car"}, .7), Hit(4.5, {"car"}, .6)]
    events = build_events(hits, duration=10, padding_before=2, padding_after=1,
                          merge_gap=1.5, min_duration=.5, sample_period=.5)
    assert len(events) == 1
    assert events[0]["start"] == 0
    assert events[0]["end"] == 6.0
    assert events[0]["classes"] == ["car", "person"]
    assert events[0]["score"] == .9


def test_empty_hits():
    assert build_events([], 10, 2, 2, 3, 1, 1/3) == []
