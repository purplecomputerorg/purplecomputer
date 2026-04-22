"""Tests for purple_tui.audio_hotplug.

Covers:
- udev event line parsing (known-good and unrelated lines)
- debounce: a burst of adds within the window fires exactly one callback
- debounce: events separated by quiet periods fire separately
- debounce: end-of-stream flushes a pending event
"""

from purple_tui.audio_hotplug import debounce_events, parse_event_line


def test_parse_add_event():
    line = "UDEV  [1234.567] add      /devices/pci/sound/card1 (sound)"
    assert parse_event_line(line) == "add"


def test_parse_remove_event():
    line = "KERNEL[1234.567] remove   /devices/pci/sound/card1 (sound)"
    assert parse_event_line(line) == "remove"


def test_parse_non_sound_line_returns_none():
    assert parse_event_line("UDEV [1234.567] add /devices/pci/block/sda (block)") is None
    assert parse_event_line("random unrelated output") is None
    assert parse_event_line("") is None


def test_debounce_coalesces_burst():
    """Three adds within 0.5s debounce window fire one callback."""
    fires: list[str] = []
    # Fake clock: each call returns an incremented time in 0.1s steps.
    now = [0.0]
    def clock():
        now[0] += 0.1
        return now[0]

    lines = [
        "UDEV [1.0] add /devices/pci/sound/card1 (sound)",
        "UDEV [1.1] add /devices/pci/sound/card1/controlC1 (sound)",
        "UDEV [1.2] add /devices/pci/sound/card1/pcmC1D0p (sound)",
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add"]


def test_debounce_separates_distant_events():
    """Events with a quiet period between them fire separately."""
    fires: list[str] = []
    # Clock returns widely-separated times.
    times = iter([0.0, 10.0, 20.0, 30.0])
    def clock():
        return next(times)

    lines = [
        "UDEV [1] add /devices/pci/sound/card1 (sound)",
        "",  # silence flush
        "UDEV [2] remove /devices/pci/sound/card1 (sound)",
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add", "remove"]


def test_debounce_flushes_on_end_of_stream():
    """A trailing pending event fires even if stream ends without silence."""
    fires: list[str] = []
    def clock() -> float:
        return 0.0
    lines = ["UDEV [1] add /devices/pci/sound/card1 (sound)"]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add"]


def test_debounce_ignores_non_matching_lines_alone():
    """Lines that don't match the sound pattern don't trigger callbacks."""
    fires: list[str] = []
    def clock() -> float:
        return 0.0
    lines = [
        "some random stderr",
        "UDEV [1] add /devices/pci/block/sda (block)",  # wrong subsystem
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == []
