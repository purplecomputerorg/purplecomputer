from purple_tui.canvas import screen_size

# `xrandr --query --prop` as i915 prints it: properties, then the mode list
RETINA = """Screen 0: minimum 320 x 200, current 2880 x 1800, maximum 16384 x 16384
eDP-1 connected primary 2880x1800+0+0 (normal left inverted right x axis y axis) 331mm x 207mm
\tEDID:
\t\t00ffffffffffff0006102ca000000000
\t\t2816010380211578020b9da35b4f9f27
\tscaling mode: Full aspect
\t\tsupported: Full, Center, Full aspect
\tBroadcast RGB: Automatic
\t\tsupported: Automatic, Full, Limited 16:235
\tmax bpc: 12
\t\trange: (6, 12)
   2880x1800     59.99*+
   2560x1600     59.99
   1920x1200     59.88
   1920x1080     60.01
   1680x1050     59.95
   1440x900      59.89
DP-1 disconnected (normal left inverted right x axis y axis)
\tscaling mode: None
\t\tsupported: None, Full, Center, Full aspect
"""

TV_4K = """HDMI-1 connected 3840x2160+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm
\tBroadcast RGB: Automatic
\t\tsupported: Automatic, Full, Limited 16:235
   3840x2160     30.00*+  25.00
   2560x1440     59.95
   1920x1080i    60.00
   1920x1080     60.00    50.00
   1280x720      60.00
"""

SURFACE = """eDP-1 connected primary 2736x1824+0+0 (normal) 260mm x 173mm
\tscaling mode: None
\t\tsupported: None, Full, Center, Full aspect
   2736x1824     59.96*+
   1920x1200     59.88
   1600x1200     60.00
"""


def _switch(query, monkeypatch, flag=False):
    """Run cap() on a 2880x1800 desktop against `query`; returns (xrandr switch args or None, log)."""
    calls, logs = [], []

    class Done:
        stdout, returncode = query, 0

    monkeypatch.setattr(screen_size, "_in_vm", lambda: False)
    monkeypatch.setattr(screen_size.os.path, "exists", lambda p: flag)
    monkeypatch.setattr(screen_size.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done)
    screen_size.cap(2880, 1800, logs.append)
    switch = [c[1:] for c in calls if "--mode" in c]
    return (switch[0] if switch else None), logs


def test_retina_switches_to_the_largest_same_shape_mode_and_fills_the_panel(monkeypatch):
    args, logs = _switch(RETINA, monkeypatch)
    assert args == ["--output", "eDP-1", "--set", "scaling mode", "Full aspect", "--mode", "1920x1200"]
    assert logs == ["screen size: eDP-1 2880x1800 -> 1920x1200"]


def test_a_monitor_that_scales_itself_gets_a_progressive_mode_only(monkeypatch):
    assert _switch(TV_4K, monkeypatch)[0] == ["--output", "HDMI-1", "--mode", "1920x1080"]


def test_no_mode_with_the_screens_shape_keeps_native(monkeypatch):
    args, logs = _switch(SURFACE, monkeypatch)
    assert args is None and "keeps 2736x1824" in logs[0]


def test_two_screens_keep_their_sizes(monkeypatch):
    args, logs = _switch(RETINA + TV_4K, monkeypatch)
    assert args is None and logs == ["screen size: 2 screens connected, each keeps its size"]


def test_flag_file_keeps_native(monkeypatch):
    assert _switch(RETINA, monkeypatch, flag=True) == (None, [])


def test_screens_under_the_cap_never_run_xrandr(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("xrandr ran for a screen under the cap")
    monkeypatch.setattr(screen_size.subprocess, "run", boom)
    for size in ((1366, 768), (1920, 1200), (1200, 1920), (800, 1280)):
        assert screen_size.cap(*size, print) is False
