"""Tests for recording-setup/apply_zoom.py keyframe and expression math."""

import sys
from pathlib import Path

# Add recording-setup to path so we can import apply_zoom
sys.path.insert(0, str(Path(__file__).parent.parent / "recording-setup"))

from apply_zoom import (
    auto_generate_pans,
    build_keyframes,
    build_crop_expr,
    build_zoompan_expr,
    cursor_events_to_pans,
    get_crop_rect,
    keyframes_to_zoom,
)


# Test video dimensions (1920x1080 is standard)
VW = 1920
VH = 1080
DURATION = 10.0


class TestGetCropRect:
    def test_no_zoom_returns_full_frame(self):
        w, h, x, y = get_crop_rect(1.0, "viewport", VW, VH)
        assert w == VW
        assert h == VH
        assert x == 0
        assert y == 0

    def test_zoom_reduces_crop_size(self):
        w, h, x, y = get_crop_rect(2.0, "viewport", VW, VH)
        assert w == VW // 2
        assert h == VH // 2

    def test_crop_dimensions_are_even(self):
        w, h, x, y = get_crop_rect(3.0, "viewport", VW, VH)
        assert w % 2 == 0
        assert h % 2 == 0

    def test_crop_stays_in_bounds(self):
        # Use a region near the edge to test clamping
        w, h, x, y = get_crop_rect(2.0, "viewport", VW, VH)
        assert x >= 0
        assert y >= 0
        assert x + w <= VW
        assert y + h <= VH


class TestBuildKeyframes:
    def test_no_events_gives_two_keyframes(self):
        kf = build_keyframes([], VW, VH, DURATION)
        assert len(kf) == 2
        assert kf[0][0] == 0.0
        assert kf[-1][0] == DURATION
        # Both should be full frame
        assert kf[0][1] == VW
        assert kf[0][2] == VH

    def test_zoom_in_creates_four_keyframes(self):
        events = [
            {"time": 2.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        # t=0 (initial), t=2.0 (zoom start), t=2.2 (zoom end), t=10.0 (end)
        assert len(kf) == 4
        assert kf[0][0] == 0.0
        assert kf[1][0] == 2.0
        assert kf[2][0] == 2.2
        assert kf[3][0] == DURATION

    def test_zoom_in_out_creates_six_keyframes(self):
        events = [
            {"time": 2.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 5.0, "action": "zoom_out", "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        # t=0, t=2.0, t=2.2, t=5.0, t=5.2, t=10.0
        assert len(kf) == 6

    def test_zoom_in_changes_crop(self):
        events = [
            {"time": 2.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        # Before zoom: full frame
        assert kf[1][1] == VW  # w at zoom start
        # After zoom: half frame
        assert kf[2][1] == VW // 2  # w at zoom end

    def test_zoom_out_restores_full_frame(self):
        events = [
            {"time": 2.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 5.0, "action": "zoom_out", "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        # After zoom out: full frame
        assert kf[4][1] == VW
        assert kf[4][2] == VH

    def test_pan_to_changes_position_not_size(self):
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 3.0, "action": "pan_to", "y": 0.3, "duration": 0.3},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        # Find the pan keyframes (at t=3.0 and t=3.3)
        pan_start = [k for k in kf if abs(k[0] - 3.0) < 0.001][0]
        pan_end = [k for k in kf if abs(k[0] - 3.3) < 0.001][0]
        # Width and height should not change
        assert pan_start[1] == pan_end[1]  # w unchanged
        assert pan_start[2] == pan_end[2]  # h unchanged
        # Y should change
        assert pan_start[4] != pan_end[4]

    def test_keyframes_sorted_by_time(self):
        events = [
            {"time": 5.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        times = [k[0] for k in kf]
        assert times == sorted(times)


class TestBuildCropExpr:
    def test_single_keyframe(self):
        kf = [(0.0, 1920, 1080, 0, 0)]
        expr = build_crop_expr(kf, 0)
        assert expr == "1920"

    def test_static_hold(self):
        kf = [
            (0.0, 1920, 1080, 0, 0),
            (10.0, 1920, 1080, 0, 0),
        ]
        expr = build_crop_expr(kf, 0)  # width
        # Should contain the static value
        assert "1920" in expr

    def test_transition_contains_smoothstep(self):
        kf = [
            (0.0, 1920, 1080, 0, 0),
            (2.0, 1920, 1080, 0, 0),
            (2.2, 960, 540, 480, 270),
            (10.0, 960, 540, 480, 270),
        ]
        # Width transition from 1920 to 960
        expr = build_crop_expr(kf, 0)
        # Should contain smoothstep components (3-2*p)
        assert "3-2*" in expr
        # Should contain clip() for clamping progress
        assert "clip(" in expr

    def test_even_dimensions_enforced(self):
        kf = [
            (0.0, 1920, 1080, 0, 0),
            (1.0, 961, 541, 0, 0),
        ]
        # Width (param 0) should use trunc(x/2)*2 for even enforcement
        w_expr = build_crop_expr(kf, 0)
        assert "trunc(" in w_expr and "/2)*2" in w_expr
        # Height (param 1) should also enforce even
        h_expr = build_crop_expr(kf, 1)
        assert "trunc(" in h_expr and "/2)*2" in h_expr
        # X (param 2) should NOT enforce even
        x_expr = build_crop_expr(kf, 2)
        assert "/2)*2" not in x_expr

    def test_empty_keyframes(self):
        expr = build_crop_expr([], 0)
        assert expr == "0"

    def test_no_transition_when_values_equal(self):
        kf = [
            (0.0, 1920, 1080, 0, 0),
            (5.0, 1920, 1080, 0, 0),
            (10.0, 1920, 1080, 0, 0),
        ]
        expr = build_crop_expr(kf, 0)
        # No smoothstep needed for static values
        assert "3-2*" not in expr


class TestKeyframesToZoom:
    def test_full_frame_is_zoom_1(self):
        kf = [(0.0, 1920, 1080, 0, 0), (10.0, 1920, 1080, 0, 0)]
        zkf = keyframes_to_zoom(kf, 1920)
        assert len(zkf) == 2
        assert zkf[0] == (0.0, 1.0, 0, 0)
        assert zkf[1] == (10.0, 1.0, 0, 0)

    def test_half_frame_is_zoom_2(self):
        kf = [(0.0, 1920, 1080, 0, 0), (2.0, 960, 540, 480, 270)]
        zkf = keyframes_to_zoom(kf, 1920)
        assert zkf[1][1] == 2.0
        assert zkf[1][2] == 480
        assert zkf[1][3] == 270

    def test_zoom_3x(self):
        kf = [(0.0, 640, 360, 100, 200)]
        zkf = keyframes_to_zoom(kf, 1920)
        assert zkf[0][1] == 3.0

    def test_preserves_times(self):
        kf = [(1.5, 1920, 1080, 0, 0), (3.7, 960, 540, 480, 270)]
        zkf = keyframes_to_zoom(kf, 1920)
        assert zkf[0][0] == 1.5
        assert zkf[1][0] == 3.7

    def test_zero_width_gives_zoom_1(self):
        kf = [(0.0, 0, 0, 0, 0)]
        zkf = keyframes_to_zoom(kf, 1920)
        assert zkf[0][1] == 1.0


class TestBuildZoompanExpr:
    def test_empty_keyframes_z(self):
        assert build_zoompan_expr([], "z") == "1"

    def test_empty_keyframes_x(self):
        assert build_zoompan_expr([], "x") == "0"

    def test_single_keyframe_z(self):
        zkf = [(0.0, 2.5, 100, 200)]
        expr = build_zoompan_expr(zkf, "z")
        assert "2.5" in expr

    def test_single_keyframe_xy(self):
        zkf = [(0.0, 1.0, 150, 300)]
        assert build_zoompan_expr(zkf, "x") == "150"
        assert build_zoompan_expr(zkf, "y") == "300"

    def test_static_hold_no_smoothstep(self):
        zkf = [
            (0.0, 1.0, 0, 0),
            (5.0, 1.0, 0, 0),
            (10.0, 1.0, 0, 0),
        ]
        expr = build_zoompan_expr(zkf, "z")
        assert "3-2*" not in expr

    def test_transition_has_smoothstep(self):
        zkf = [
            (0.0, 1.0, 0, 0),
            (2.0, 1.0, 0, 0),
            (2.2, 3.0, 480, 270),
            (10.0, 3.0, 480, 270),
        ]
        z_expr = build_zoompan_expr(zkf, "z")
        assert "3-2*" in z_expr
        assert "clip(" in z_expr

    def test_uses_in_time(self):
        zkf = [
            (0.0, 1.0, 0, 0),
            (2.0, 1.0, 0, 0),
            (2.2, 2.0, 100, 100),
            (10.0, 2.0, 100, 100),
        ]
        expr = build_zoompan_expr(zkf, "z")
        assert "in_time" in expr

    def test_x_transition_uses_trunc(self):
        zkf = [
            (0.0, 1.0, 0, 0),
            (2.0, 2.0, 500, 300),
        ]
        x_expr = build_zoompan_expr(zkf, "x")
        # x uses integer values, should trunc
        assert "trunc" in x_expr

    def test_z_transition_no_trunc(self):
        zkf = [
            (0.0, 1.0, 0, 0),
            (2.0, 3.0, 500, 300),
        ]
        z_expr = build_zoompan_expr(zkf, "z")
        # z is a float, should NOT trunc
        assert "trunc" not in z_expr

    def test_zoom_in_out_roundtrip(self):
        """Full zoom in/out cycle produces correct expression structure."""
        events = [
            {"time": 2.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 5.0, "action": "zoom_out", "duration": 0.2},
        ]
        kf = build_keyframes(events, VW, VH, DURATION)
        zkf = keyframes_to_zoom(kf, VW)
        z_expr = build_zoompan_expr(zkf, "z")
        x_expr = build_zoompan_expr(zkf, "x")
        y_expr = build_zoompan_expr(zkf, "y")
        # All should be non-empty valid expressions
        assert len(z_expr) > 0
        assert len(x_expr) > 0
        assert len(y_expr) > 0
        # Should have transitions (smoothstep)
        assert "3-2*" in z_expr


class TestCursorEventsToPans:
    def test_no_cursor_events_strips_cursor_at(self):
        """Events without cursor_at are returned with cursor_at removed."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        result = cursor_events_to_pans(events, VW, VH)
        assert len(result) == 2
        assert all(ev["action"] != "cursor_at" for ev in result)

    def test_cursor_at_generates_pan(self):
        """Cursor moving outside safe zone generates a pan_to event."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            # Cursor at far-right edge, outside default crop center
            {"time": 2.0, "action": "cursor_at", "x": 0.9, "y": 0.5},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        result = cursor_events_to_pans(events, VW, VH)
        pan_events = [ev for ev in result if ev["action"] == "pan_to"]
        assert len(pan_events) >= 1

    def test_cursor_at_no_pan_when_in_center(self):
        """Cursor near center of crop region generates no pan."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            # Cursor at center (0.5, 0.5) matches viewport region center
            {"time": 2.0, "action": "cursor_at", "x": 0.5, "y": 0.5},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        result = cursor_events_to_pans(events, VW, VH)
        pan_events = [ev for ev in result if ev["action"] == "pan_to"]
        assert len(pan_events) == 0

    def test_cursor_at_stripped_from_output(self):
        """cursor_at events are removed from the output."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 2.0, "action": "cursor_at", "x": 0.5, "y": 0.5},
            {"time": 3.0, "action": "cursor_at", "x": 0.5, "y": 0.5},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        result = cursor_events_to_pans(events, VW, VH)
        assert all(ev["action"] != "cursor_at" for ev in result)

    def test_respects_min_pan_interval(self):
        """Pans are throttled by min_pan_interval."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 1.5, "action": "cursor_at", "x": 0.1, "y": 0.1},
            {"time": 1.6, "action": "cursor_at", "x": 0.9, "y": 0.9},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        result = cursor_events_to_pans(events, VW, VH, min_pan_interval=2.0)
        pan_events = [ev for ev in result if ev["action"] == "pan_to"]
        # Only first should generate pan, second is too soon
        assert len(pan_events) <= 1

    def test_no_zoomed_periods(self):
        """No zoomed periods means just strip cursor_at events."""
        events = [
            {"time": 1.0, "action": "cursor_at", "x": 0.5, "y": 0.5},
        ]
        result = cursor_events_to_pans(events, VW, VH)
        assert len(result) == 0


class TestAutoGeneratePans:
    def test_no_zoomed_periods(self):
        """Events with no zoom_in return unchanged."""
        events = [{"time": 1.0, "action": "pan_to", "y": 0.5, "duration": 0.3}]
        result = auto_generate_pans(events, Path("/fake"), VW, VH)
        assert result is events

    def test_skips_periods_with_manual_pans(self):
        """Periods that already have manual pan_to events are skipped."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 3.0, "action": "pan_to", "y": 0.3, "duration": 0.3},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        log_msgs = []
        result = auto_generate_pans(events, Path("/fake"), VW, VH, log_fn=log_msgs.append)
        assert result is events
        assert any("manual pans" in m for m in log_msgs)

    def test_no_activity_returns_unchanged(self):
        """When video can't be opened, no pans are generated."""
        events = [
            {"time": 1.0, "action": "zoom_in", "region": "viewport", "zoom": 2.0, "duration": 0.2},
            {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        ]
        log_msgs = []
        result = auto_generate_pans(events, Path("/nonexistent.mp4"), VW, VH, log_fn=log_msgs.append)
        # No pans generated (video can't be read), original events returned
        assert len(result) == len(events)
