from purple_tui.canvas import screen_size

RETINA = """Screen 0: minimum 320 x 200, current 2880 x 1800, maximum 16384 x 16384
eDP-1 connected primary 2880x1800+0+0 (normal left inverted right x axis y axis) 331mm x 207mm
   2880x1800     59.99*+
   2560x1600     59.99
   1920x1200     59.88
   1920x1080     60.01
   1680x1050     59.95
   1440x900      59.89
DP-1 disconnected (normal left inverted right x axis y axis)
"""

TV_4K = """eDP-1 disconnected
HDMI-1 connected 3840x2160+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm
   3840x2160     30.00*+  25.00
   2560x1440     59.95
   1920x1080i    60.00
   1920x1080     60.00    50.00
   1280x720      60.00
"""

SURFACE = """eDP-1 connected primary 2736x1824+0+0 (normal) 260mm x 173mm
   2736x1824     59.96*+
   1920x1200     59.88
   1600x1200     60.00
"""



def _pick(query):
    (modes,) = screen_size.outputs(query).values()
    return screen_size.pick(modes)


def test_retina_drops_to_largest_same_shape_mode():
    assert _pick(RETINA) == "1920x1200"


def test_4k_tv_gets_progressive_1080p():
    assert _pick(TV_4K) == "1920x1080"


def test_no_mode_with_the_panels_shape_keeps_native():
    assert _pick(SURFACE) is None


def test_only_connected_outputs_are_read():
    assert list(screen_size.outputs(TV_4K)) == ["HDMI-1"]
    assert list(screen_size.outputs(RETINA)) == ["eDP-1"]


def test_small_screen_never_queries_xrandr(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("xrandr ran for a screen under the cap")
    monkeypatch.setattr(screen_size.subprocess, "run", boom)
    assert screen_size.cap(1366, 768, print) is False
    assert screen_size.cap(1920, 1200, print) is False


def test_cap_switches_the_output_over_the_cap(monkeypatch):
    calls = []

    class Done:
        stdout, returncode = RETINA, 0

    monkeypatch.setattr(screen_size, "_in_vm", lambda: False)
    monkeypatch.setattr(screen_size.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done)
    logs = []
    assert screen_size.cap(2880, 1800, logs.append) is True
    assert calls[-1] == ["xrandr", "--output", "eDP-1", "--mode", "1920x1200"]
    assert logs == ["screen size: eDP-1 2880x1800 -> 1920x1200"]
