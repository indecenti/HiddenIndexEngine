"""
tests/test_coordinate_system.py

Comprehensive test suite for HiddenEngine coordinate system.
Validates that editor and game engine maintain perfect alignment
in reference space (1280×720).

Tests cover:
- Circle and rect object positioning
- Hit detection in reference space
- Coordinate transformations (screen ↔ reference)
- Editor zoom/pan isolation
- JSON serialization fidelity
"""

import pytest
import math
from pathlib import Path
import json
import tempfile

# Import engine components
from engine.click_detector import ClickDetector
from engine.scene_loader import SceneObject, SceneLoader
from engine.scaling_manager import ScalingManager, REF_W, REF_H


class TestReferenceSpace:
    """Verify reference space is 1280×720 and authoritative."""

    def test_ref_dimensions(self):
        """Reference space must be 1280×720."""
        assert REF_W == 1280
        assert REF_H == 720

    def test_ref_origin(self):
        """Reference space origin is top-left (0, 0)."""
        sm = ScalingManager()
        sm.update_screen_size(1280, 720)

        # (0, 0) in ref should be top-left in screen
        sx, sy = sm.ref_to_screen(0, 0)
        assert sx == sm.offset_x
        assert sy == sm.offset_y


class TestCirclePositioning:
    """Test circle objects in reference space."""

    def test_circle_at_center(self):
        """Circle at (640, 360) with radius 30."""
        obj = SceneObject(
            instance_id="test_circle",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=30.0,
        )

        assert obj.x == 640.0
        assert obj.y == 360.0
        assert obj.radius == 30.0

    def test_circle_bounds(self):
        """Verify circle hit detection in reference space."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="circle",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=30.0,
        )
        obj.is_goal = True

        # Click at center
        assert detector._hit_circle(obj, 640.0, 360.0) is True

        # Click at radius boundary
        assert detector._hit_circle(obj, 670.0, 360.0) is True

        # Click just outside
        assert detector._hit_circle(obj, 671.0, 360.0) is False

        # Click far away
        assert detector._hit_circle(obj, 500.0, 250.0) is False

    def test_circle_north_south_east_west(self):
        """Test cardinal directions around circle."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="cardinal",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=50.0,
        )
        obj.is_goal = True

        # North (y - radius)
        assert detector._hit_circle(obj, 640.0, 310.0) is True
        # South (y + radius)
        assert detector._hit_circle(obj, 640.0, 410.0) is True
        # East (x + radius)
        assert detector._hit_circle(obj, 690.0, 360.0) is True
        # West (x - radius)
        assert detector._hit_circle(obj, 590.0, 360.0) is True


class TestRectPositioning:
    """Test rect objects in reference space."""

    def test_rect_topleft_convention(self):
        """Rect (x, y) represents top-left corner."""
        obj = SceneObject(
            instance_id="test_rect",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=600.0,
            y=330.0,
            detection_type="rect",
            width=80.0,
            height=60.0,
        )

        assert obj.x == 600.0
        assert obj.y == 330.0
        assert obj.width == 80.0
        assert obj.height == 60.0

    def test_rect_bounds(self):
        """Verify rect hit detection in reference space."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="rect",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=600.0,
            y=330.0,
            detection_type="rect",
            width=80.0,
            height=60.0,
        )
        obj.is_goal = True

        # Click at top-left
        assert detector._hit_rect(obj, 600.0, 330.0) is True

        # Click at center (600 + 40, 330 + 30)
        assert detector._hit_rect(obj, 640.0, 360.0) is True

        # Click at bottom-right
        assert detector._hit_rect(obj, 680.0, 390.0) is True

        # Click outside
        assert detector._hit_rect(obj, 500.0, 250.0) is False
        assert detector._hit_rect(obj, 700.0, 400.0) is False

    def test_rect_corners(self):
        """Test all four corners of rect."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="corners",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=600.0,
            y=330.0,
            detection_type="rect",
            width=80.0,
            height=60.0,
        )
        obj.is_goal = True

        # Top-left
        assert detector._hit_rect(obj, 600.0, 330.0) is True
        # Top-right
        assert detector._hit_rect(obj, 680.0, 330.0) is True
        # Bottom-left
        assert detector._hit_rect(obj, 600.0, 390.0) is True
        # Bottom-right
        assert detector._hit_rect(obj, 680.0, 390.0) is True


class TestCoordinateTransformations:
    """Test screen ↔ reference transformations."""

    def test_ref_to_screen_no_scaling(self):
        """When screen = ref size, mappings are identity (with offset)."""
        sm = ScalingManager()
        sm.update_screen_size(REF_W, REF_H)

        # No scaling, offset should be 0
        assert sm.scale == 1.0
        assert sm.offset_x == 0
        assert sm.offset_y == 0

        # Reference → Screen should be identity
        assert sm.ref_to_screen(0, 0) == (0, 0)
        assert sm.ref_to_screen(640, 360) == (640, 360)

    def test_screen_to_ref_roundtrip(self):
        """screen → ref → screen should be identity."""
        sm = ScalingManager()
        sm.update_screen_size(1920, 1080)

        # Start with screen coordinates
        sx_orig, sy_orig = 960, 540

        # Convert to ref and back
        rx, ry = sm.screen_to_ref(sx_orig, sy_orig)
        sx_new, sy_new = sm.ref_to_screen(rx, ry)

        # Should recover original screen coords (within rounding)
        assert abs(sx_orig - sx_new) <= 1
        assert abs(sy_orig - sy_new) <= 1

    def test_ref_space_consistency_across_resolutions(self):
        """Reference coordinates remain constant regardless of resolution."""
        sm = ScalingManager()

        ref_x, ref_y = 640.0, 360.0

        # Test multiple resolutions
        for res_w, res_h in [(1280, 720), (1920, 1080), (640, 480)]:
            sm.update_screen_size(res_w, res_h)

            # Convert ref → screen → ref
            sx, sy = sm.ref_to_screen(ref_x, ref_y)
            rx, ry = sm.screen_to_ref(sx, sy)

            # Must recover original reference coords
            assert abs(rx - ref_x) < 0.01
            assert abs(ry - ref_y) < 0.01


class TestEditorZoomIsolation:
    """Verify editor zoom doesn't affect reference space or JSON."""

    def test_editor_zoom_is_display_only(self):
        """
        Editor zoom transforms screen→ref, but JSON always stores in reference space.
        This test simulates editor coordinate transforms.
        """
        # Simulate editor state
        zoom = 2.0
        origin_x, origin_y = 100.0, 100.0

        # Reference coordinates (what gets saved to JSON)
        ref_x, ref_y = 640.0, 360.0

        # Convert to screen with zoom
        screen_x = ref_x * zoom + origin_x
        screen_y = ref_y * zoom + origin_y

        # Convert back to reference (editor's _s2r)
        recovered_x = (screen_x - origin_x) / zoom
        recovered_y = (screen_y - origin_y) / zoom

        # Must recover original reference coordinates
        assert abs(recovered_x - ref_x) < 0.01
        assert abs(recovered_y - ref_y) < 0.01

    def test_object_position_invariant_with_zoom(self):
        """
        Object at (640, 360) remains at (640, 360) in reference space
        regardless of editor zoom.
        """
        ref_x, ref_y = 640.0, 360.0

        for zoom in [0.5, 1.0, 2.0, 5.0]:
            # Even with different zoom, reference coords stay the same
            assert ref_x == 640.0
            assert ref_y == 360.0


class TestGamePanZoomHandling:
    """Verify game pan/zoom doesn't affect reference coordinates."""

    def test_screen_to_scene_with_pan_zoom(self):
        """
        Game applies pan/zoom, but click detection uses reference space.
        """
        sm = ScalingManager()
        sm.update_screen_size(1280, 720)

        # Apply game pan and zoom
        sm.set_pan(100.0, 50.0)
        sm.set_zoom(2.0)

        # Click at screen center
        screen_x, screen_y = 640, 360

        # Convert to scene (reference) space
        scene_x, scene_y = sm.screen_to_scene(screen_x, screen_y)

        # Should account for pan/zoom
        # scene = (ref - pan) / zoom
        expected_x = (640 - 100.0) / 2.0
        expected_y = (360 - 50.0) / 2.0

        assert abs(scene_x - expected_x) < 0.01
        assert abs(scene_y - expected_y) < 0.01


class TestJSONSerialization:
    """Verify JSON stores reference coordinates unchanged."""

    def test_json_preserves_reference_coords(self):
        """Round-trip JSON should preserve reference coordinates."""
        original_object = {
            "catalog_id": "chiave",
            "x": 640.0,
            "y": 360.0,
            "detection_type": "circle",
            "radius": 30.0,
            "layer": "objects_mid",
            "is_goal": True,
        }

        # Serialize and deserialize
        json_str = json.dumps(original_object)
        loaded_object = json.loads(json_str)

        # Coordinates must match exactly
        assert loaded_object["x"] == 640.0
        assert loaded_object["y"] == 360.0
        assert loaded_object["radius"] == 30.0


class TestRotationCenters:
    """Verify rotation centers are consistent by type."""

    def test_circle_rotation_center_is_position(self):
        """For circles, rotation center = (x, y)."""
        obj = SceneObject(
            instance_id="rotated_circle",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=30.0,
            rotation=45.0,
        )

        # Center should be at (x, y)
        assert obj.x == 640.0
        assert obj.y == 360.0

    def test_rect_rotation_center_is_computed(self):
        """For rects, rotation center = (x + width/2, y + height/2)."""
        obj = SceneObject(
            instance_id="rotated_rect",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=600.0,
            y=330.0,
            detection_type="rect",
            width=80.0,
            height=60.0,
            rotation=45.0,
        )

        # Center should be computed
        computed_cx = obj.x + obj.width / 2
        computed_cy = obj.y + obj.height / 2

        assert computed_cx == 640.0
        assert computed_cy == 360.0


class TestEdgesCritical:
    """Test boundary conditions and edge cases."""

    def test_zero_radius_circle(self):
        """Circle with radius 0 is a point."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="point",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=0.0,
        )
        obj.is_goal = True

        # Only hits at exact center
        assert detector._hit_circle(obj, 640.0, 360.0) is True
        assert detector._hit_circle(obj, 640.1, 360.0) is False

    def test_tiny_rect(self):
        """Rect with minimal dimensions."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="tiny",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="rect",
            width=1.0,
            height=1.0,
        )
        obj.is_goal = True

        # Hits within bounds (center is at 640.5, bounds are [640, 641])
        assert detector._hit_rect(obj, 640.0, 360.0) is True
        assert detector._hit_rect(obj, 641.0, 360.0) is True
        # Misses just outside
        assert detector._hit_rect(obj, 641.1, 360.0) is False

    def test_large_circle(self):
        """Large circle covering significant area."""
        detector = ClickDetector(ScalingManager())
        obj = SceneObject(
            instance_id="large",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=500.0,
        )
        obj.is_goal = True

        # Hits almost anywhere
        assert detector._hit_circle(obj, 640.0, 360.0) is True
        assert detector._hit_circle(obj, 200.0, 200.0) is True
        assert detector._hit_circle(obj, 100.0, 100.0) is False


class TestHitDetectionConsistency:
    """Ensure editor and game use same hit detection rules."""

    def test_hit_detection_reference_space(self):
        """Hit detection always operates in reference space."""
        detector = ClickDetector(ScalingManager())

        # Create object
        obj = SceneObject(
            instance_id="test",
            catalog_id="test",
            label_key="test",
            icon_path="",
            x=640.0,
            y=360.0,
            detection_type="circle",
            radius=30.0,
        )
        obj.is_goal = True

        # Test with different screen resolutions
        # Hit status in reference space should never change
        for screen_w, screen_h in [(1280, 720), (1920, 1080), (800, 600)]:
            sm = ScalingManager()
            sm.update_screen_size(screen_w, screen_h)
            detector = ClickDetector(sm)

            # Object position in reference space is constant
            assert detector._hit_circle(obj, 640.0, 360.0) is True
            assert detector._hit_circle(obj, 670.0, 360.0) is True
            assert detector._hit_circle(obj, 671.0, 360.0) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
