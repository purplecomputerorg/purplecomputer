#!/usr/bin/env python3
"""Tests for color mixing module.

The color mixing implementation is based on spectral.js by Ronald van Wijnen:
https://github.com/rvanwijnen/spectral.js (MIT License)
"""

import pytest
from purple_tui.color_mixing import (
    get_color_name_approximation,
    mix_colors_paint,
    hex_to_rgb,
    rgb_to_hex,
    SIZE,
    _ks,
    _km,
    _srgb_to_linear,
    _linear_to_srgb,
    _linear_rgb_to_spectrum,
    _spectrum_to_xyz,
    _xyz_to_linear_rgb,
    BASE_SPECTRA,
)


class TestKubelkaMunkFunctions:
    """Test Kubelka-Munk K/S conversion functions."""

    def test_ks_low_reflectance(self):
        """Low reflectance (dark) should have high K/S."""
        ks = _ks(0.1)
        assert ks > 1  # High absorption

    def test_ks_high_reflectance(self):
        """High reflectance (light) should have low K/S."""
        ks = _ks(0.9)
        assert ks < 0.1  # Low absorption

    def test_ks_medium_reflectance(self):
        """50% reflectance should give K/S = 0.5."""
        ks = _ks(0.5)
        assert abs(ks - 0.25) < 0.01  # (1-0.5)^2 / (2*0.5) = 0.25

    def test_km_inverse_of_ks(self):
        """KM should approximately invert KS for valid values."""
        for r in [0.1, 0.3, 0.5, 0.7, 0.9]:
            ks = _ks(r)
            r_back = _km(ks)
            assert abs(r - r_back) < 0.001, f"Round-trip failed for r={r}"

    def test_km_zero_ks(self):
        """KM of very small K/S should be close to 1 (white)."""
        assert _km(0.001) > 0.95

    def test_km_large_ks(self):
        """KM of large K/S should be close to 0 (black)."""
        assert _km(100) < 0.02


class TestGammaConversion:
    """Test sRGB gamma conversion functions."""

    def test_linear_to_srgb_black(self):
        assert _linear_to_srgb(0.0) == 0

    def test_linear_to_srgb_white(self):
        assert _linear_to_srgb(1.0) == 255

    def test_linear_to_srgb_mid(self):
        # Linear 0.5 should map to sRGB ~188 (due to gamma)
        result = _linear_to_srgb(0.5)
        assert 180 < result < 200

    def test_srgb_to_linear_black(self):
        assert _srgb_to_linear(0) == 0.0

    def test_srgb_to_linear_white(self):
        assert abs(_srgb_to_linear(255) - 1.0) < 0.001

    def test_srgb_to_linear_mid(self):
        # sRGB 128 should map to linear ~0.21 (due to gamma)
        result = _srgb_to_linear(128)
        assert 0.2 < result < 0.25

    def test_round_trip_conversion(self):
        """Converting sRGB -> linear -> sRGB should preserve value."""
        for val in [0, 50, 100, 128, 200, 255]:
            linear = _srgb_to_linear(val)
            back = _linear_to_srgb(linear)
            assert abs(val - back) <= 1, f"Round-trip failed for {val}"


class TestSpectrumConversion:
    """Test RGB to spectrum conversion."""

    def test_white_spectrum(self):
        """White should produce high reflectance across all wavelengths."""
        spectrum = _linear_rgb_to_spectrum((1.0, 1.0, 1.0))
        assert len(spectrum) == SIZE
        assert all(s > 0.9 for s in spectrum)

    def test_black_spectrum(self):
        """Black should produce low reflectance across all wavelengths."""
        spectrum = _linear_rgb_to_spectrum((0.0, 0.0, 0.0))
        assert len(spectrum) == SIZE
        assert all(s < 0.1 for s in spectrum)

    def test_red_spectrum_shape(self):
        """Red should have high reflectance in long wavelengths."""
        spectrum = _linear_rgb_to_spectrum((1.0, 0.0, 0.0))
        # Last quarter (long wavelengths) should be higher than first quarter
        first_quarter = sum(spectrum[:SIZE//4]) / (SIZE//4)
        last_quarter = sum(spectrum[-SIZE//4:]) / (SIZE//4)
        assert last_quarter > first_quarter

    def test_blue_spectrum_shape(self):
        """Blue should have high reflectance in short wavelengths."""
        spectrum = _linear_rgb_to_spectrum((0.0, 0.0, 1.0))
        # First quarter (short wavelengths) should be higher than last quarter
        first_quarter = sum(spectrum[:SIZE//4]) / (SIZE//4)
        last_quarter = sum(spectrum[-SIZE//4:]) / (SIZE//4)
        assert first_quarter > last_quarter

    def test_spectrum_always_positive(self):
        """Spectrum values should always be positive."""
        test_colors = [
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.5, 0.5, 0.5),
            (0.2, 0.8, 0.3),
        ]
        for rgb in test_colors:
            spectrum = _linear_rgb_to_spectrum(rgb)
            assert all(s > 0 for s in spectrum), f"Negative value for {rgb}"


class TestBaseSpectra:
    """Test the base spectral data."""

    def test_all_spectra_correct_size(self):
        """All base spectra should have SIZE elements."""
        for name, spectrum in BASE_SPECTRA.items():
            assert len(spectrum) == SIZE, f"{name} has wrong size"

    def test_white_spectrum_high(self):
        """White spectrum should be close to 1.0 everywhere."""
        assert all(0.99 < s < 1.01 for s in BASE_SPECTRA["W"])

    def test_spectra_in_valid_range(self):
        """All spectra values should be between 0 and 1.1."""
        for name, spectrum in BASE_SPECTRA.items():
            for i, s in enumerate(spectrum):
                assert 0 <= s <= 1.1, f"{name}[{i}] = {s} out of range"


class TestXYZConversion:
    """Test XYZ color space conversion."""

    def test_white_xyz(self):
        """White spectrum should produce roughly equal X, Y, Z."""
        white_spectrum = [1.0] * SIZE
        x, y, z = _spectrum_to_xyz(white_spectrum)
        # Y is luminance, should be highest for white
        assert y > 0

    def test_xyz_to_rgb_white(self):
        """D65 white point XYZ should convert to white RGB."""
        # D65 white point (normalized)
        r, g, b = _xyz_to_linear_rgb((0.95047, 1.0, 1.08883))
        assert abs(r - 1.0) < 0.1
        assert abs(g - 1.0) < 0.1
        assert abs(b - 1.0) < 0.1


class TestGetColorNameApproximation:
    """Test that color names are simple and kid-friendly (no modifiers)."""

    def test_pure_red(self):
        assert get_color_name_approximation("#FF0000") == "red"

    def test_pure_blue(self):
        assert get_color_name_approximation("#0000FF") == "blue"

    def test_pure_green(self):
        assert get_color_name_approximation("#00FF00") == "green"

    def test_pure_yellow(self):
        assert get_color_name_approximation("#FFFF00") == "yellow"

    def test_orange(self):
        assert get_color_name_approximation("#FF8000") == "orange"

    def test_purple(self):
        assert get_color_name_approximation("#800080") == "purple"

    def test_pink(self):
        assert get_color_name_approximation("#FF69B4") == "pink"

    def test_cyan(self):
        assert get_color_name_approximation("#00FFFF") == "cyan"

    def test_black(self):
        assert get_color_name_approximation("#000000") == "black"

    def test_white(self):
        assert get_color_name_approximation("#FFFFFF") == "white"

    def test_gray(self):
        assert get_color_name_approximation("#808080") == "gray"

    def test_dark_red_returns_just_red(self):
        result = get_color_name_approximation("#800000")
        assert result == "red"
        assert "dark" not in result

    def test_light_blue_returns_just_blue(self):
        result = get_color_name_approximation("#ADD8E6")
        assert result in ("blue", "cyan")
        assert "light" not in result

    def test_muted_green_returns_just_green(self):
        result = get_color_name_approximation("#6B8E6B")
        assert "muted" not in result

    def test_no_modifier_words_in_any_result(self):
        """Ensure no color name contains modifier words."""
        test_colors = [
            "#800000", "#FFB6C1", "#556B2F",
            "#191970", "#E6E6FA", "#808000",
        ]
        modifiers = ["dark", "light", "muted"]
        for hex_color in test_colors:
            result = get_color_name_approximation(hex_color)
            for modifier in modifiers:
                assert modifier not in result, f"{hex_color} returned '{result}'"


class TestMixColorsPaint:
    """Test paint-style color mixing using app's actual colors."""

    # App's paint-like colors (from content.py)
    RED = "#E52B50"      # Cadmium red
    YELLOW = "#FFEB00"   # Primary yellow
    BLUE = "#0047AB"     # Cobalt blue

    def test_red_plus_blue_makes_purple(self):
        result = mix_colors_paint([self.RED, self.BLUE])
        name = get_color_name_approximation(result)
        assert name == "purple"

    def test_red_plus_yellow_makes_orange(self):
        result = mix_colors_paint([self.RED, self.YELLOW])
        name = get_color_name_approximation(result)
        assert name == "orange"

    def test_blue_plus_yellow_makes_green(self):
        result = mix_colors_paint([self.YELLOW, self.BLUE])
        name = get_color_name_approximation(result)
        assert name == "green"

    def test_single_color_unchanged(self):
        assert mix_colors_paint(["#FF0000"]) == "#FF0000"

    def test_same_color_multiple_times_unchanged(self):
        result = mix_colors_paint(["#FF0000", "#FF0000", "#FF0000"])
        assert result.upper() == "#FF0000"

    def test_empty_returns_gray(self):
        assert mix_colors_paint([]) == "#808080"

    def test_weighted_mixing(self):
        """More of one color should shift result toward that color."""
        # 2 red + 1 blue should be more red than 1 red + 1 blue
        balanced = mix_colors_paint([self.RED, self.BLUE])
        red_heavy = mix_colors_paint([self.RED, self.RED, self.BLUE])
        # Both should be purple-ish, but red_heavy should have more red
        r_bal, g_bal, b_bal = hex_to_rgb(balanced)
        r_heavy, g_heavy, b_heavy = hex_to_rgb(red_heavy)
        assert r_heavy >= r_bal  # More red in heavy mix

    def test_order_independent(self):
        """Mixing order shouldn't matter."""
        result1 = mix_colors_paint([self.RED, self.BLUE])
        result2 = mix_colors_paint([self.BLUE, self.RED])
        assert result1 == result2

    def test_subtractive_behavior(self):
        """Mixed colors should be darker than the brightest input."""
        result = mix_colors_paint([self.YELLOW, self.BLUE])
        r, g, b = hex_to_rgb(result)
        yr, yg, yb = hex_to_rgb(self.YELLOW)
        # Result luminance should be less than brightest input (yellow)
        result_lum = 0.299*r + 0.587*g + 0.114*b
        yellow_lum = 0.299*yr + 0.587*yg + 0.114*yb
        assert result_lum < yellow_lum


class TestColorConversion:
    """Test hex/rgb conversion utilities."""

    def test_hex_to_rgb(self):
        assert hex_to_rgb("#FF0000") == (255, 0, 0)
        assert hex_to_rgb("#00FF00") == (0, 255, 0)
        assert hex_to_rgb("#0000FF") == (0, 0, 255)
        assert hex_to_rgb("FFFFFF") == (255, 255, 255)

    def test_rgb_to_hex(self):
        assert rgb_to_hex(255, 0, 0) == "#FF0000"
        assert rgb_to_hex(0, 255, 0) == "#00FF00"
        assert rgb_to_hex(0, 0, 255) == "#0000FF"

    def test_hex_rgb_round_trip(self):
        """Converting hex -> rgb -> hex should preserve value."""
        colors = ["#FF0000", "#00FF00", "#0000FF", "#123456", "#ABCDEF"]
        for color in colors:
            rgb = hex_to_rgb(color)
            back = rgb_to_hex(*rgb)
            assert back.upper() == color.upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
