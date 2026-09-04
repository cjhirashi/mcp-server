"""Tests for image_pipeline.stability_aspect_ratio (mapeo purpose -> aspect_ratio Stability)."""

from services.bedrock.image_pipeline import PurposeSpec, stability_aspect_ratio


def test_square_purpose_maps_to_1_1():
    spec = PurposeSpec(width=500, height=500, category="agentes")
    assert stability_aspect_ratio(spec) == "1:1"


def test_widescreen_purpose_maps_to_16_9():
    spec = PurposeSpec(width=1920, height=1080, category="proyectos")
    assert stability_aspect_ratio(spec) == "16:9"


def test_result_is_always_a_valid_stability_ratio():
    valid = {"16:9", "21:9", "1:1", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"}
    for width, height in [(500, 500), (1920, 1080), (300, 1000), (1000, 300)]:
        spec = PurposeSpec(width=width, height=height, category="x")
        assert stability_aspect_ratio(spec) in valid
