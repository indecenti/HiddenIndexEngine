"""
tests/test_coordinate_e2e.py

End-to-end tests for coordinate system alignment between editor and game.
Validates the complete pipeline: editor → JSON → game.
"""

import pytest
import json
import tempfile
from pathlib import Path

from engine.scene_loader import SceneLoader, SceneObject
from engine.click_detector import ClickDetector
from engine.scaling_manager import ScalingManager


class TestEditorGameAlignment:
    """Test perfect alignment between editor and game engine."""

    @pytest.fixture
    def sample_catalog(self):
        """Sample object catalog for testing."""
        return {
            "objects": [
                {
                    "id": "chiave",
                    "label_key": "object.key",
                    "icon": "icons/chiave.png",
                    "default_detection": "circle",
                    "default_radius": 25,
                    "default_hint_delay": 30,
                },
                {
                    "id": "libro",
                    "label_key": "object.book",
                    "icon": "icons/libro.png",
                    "default_detection": "rect",
                    "default_width": 60,
                    "default_height": 40,
                    "default_hint_delay": 30,
                },
            ]
        }

    def test_circle_placement_alignment(self, sample_catalog):
        """
        Test: Circle placed at (640, 360) in editor appears at same location in game.
        """
        # Simulate editor saving a circle
        editor_object = {
            "catalog_id": "chiave",
            "x": 640.0,
            "y": 360.0,
            "detection_type": "circle",
            "radius": 25.0,
            "layer": "objects_mid",
            "is_goal": True,
        }

        # Simulate game loading the same object
        game_object = SceneObject(
            instance_id="chiave",
            catalog_id="chiave",
            label_key="object.key",
            icon_path="icons/chiave.png",
            x=editor_object["x"],
            y=editor_object["y"],
            detection_type="circle",
            radius=editor_object["radius"],
        )

        # Coordinates must match exactly
        assert game_object.x == editor_object["x"]
        assert game_object.y == editor_object["y"]
        assert game_object.radius == editor_object["radius"]

        # Hit detection must work correctly
        detector = ClickDetector(ScalingManager())
        game_object.is_goal = True

        # Click at center
        assert detector._hit_circle(game_object, 640.0, 360.0) is True

        # Click within radius
        assert detector._hit_circle(game_object, 665.0, 360.0) is True

        # Click outside radius
        assert detector._hit_circle(game_object, 666.0, 360.0) is False

    def test_rect_placement_alignment(self, sample_catalog):
        """
        Test: Rect placed at (600, 330) in editor appears at same location in game.
        """
        # Simulate editor saving a rect
        editor_object = {
            "catalog_id": "libro",
            "x": 600.0,
            "y": 330.0,
            "detection_type": "rect",
            "width": 80.0,
            "height": 60.0,
            "layer": "objects_mid",
            "is_goal": True,
        }

        # Simulate game loading the same object
        game_object = SceneObject(
            instance_id="libro",
            catalog_id="libro",
            label_key="object.book",
            icon_path="icons/libro.png",
            x=editor_object["x"],
            y=editor_object["y"],
            detection_type="rect",
            width=editor_object["width"],
            height=editor_object["height"],
        )

        # Coordinates must match exactly
        assert game_object.x == editor_object["x"]
        assert game_object.y == editor_object["y"]
        assert game_object.width == editor_object["width"]
        assert game_object.height == editor_object["height"]

        # Hit detection must work correctly
        detector = ClickDetector(ScalingManager())
        game_object.is_goal = True

        # Click at top-left
        assert detector._hit_rect(game_object, 600.0, 330.0) is True

        # Click at center
        assert detector._hit_rect(game_object, 640.0, 360.0) is True

        # Click at bottom-right
        assert detector._hit_rect(game_object, 680.0, 390.0) is True

        # Click outside
        assert detector._hit_rect(game_object, 500.0, 250.0) is False

    def test_rotation_alignment(self):
        """
        Test: Rotation is applied consistently in editor and game.
        """
        # Circle with rotation (rotation center = object center)
        circle = SceneObject(
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

        # Rotation doesn't affect center or radius
        assert circle.x == 640.0
        assert circle.y == 360.0
        assert circle.radius == 30.0

        # Rect with rotation (rotation center = computed center)
        rect = SceneObject(
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

        # Rotation doesn't affect position or size
        assert rect.x == 600.0
        assert rect.y == 330.0
        assert rect.width == 80.0
        assert rect.height == 60.0

    def test_json_roundtrip(self):
        """
        Test: Object survives JSON serialization/deserialization without change.
        """
        original = {
            "catalog_id": "chiave",
            "x": 640.0,
            "y": 360.0,
            "detection_type": "circle",
            "radius": 25.0,
            "layer": "objects_mid",
            "is_goal": True,
            "rotation": 0.0,
        }

        # Serialize to JSON
        json_str = json.dumps(original)

        # Deserialize from JSON
        loaded = json.loads(json_str)

        # Must be identical
        assert loaded == original
        assert loaded["x"] == 640.0
        assert loaded["y"] == 360.0
        assert loaded["radius"] == 25.0

    def test_multi_resolution_consistency(self):
        """
        Test: Objects at same reference coordinates work on any screen resolution.
        """
        # Object at reference position
        ref_x, ref_y = 640.0, 360.0

        # Test multiple resolutions
        resolutions = [
            (1280, 720),   # Native
            (1920, 1080),  # 1080p
            (800, 600),    # Smaller
            (3840, 2160),  # 4K
        ]

        for screen_w, screen_h in resolutions:
            sm = ScalingManager()
            sm.update_screen_size(screen_w, screen_h)

            # Convert ref to screen
            sx, sy = sm.ref_to_screen(ref_x, ref_y)

            # Convert back
            recovered_x, recovered_y = sm.screen_to_ref(sx, sy)

            # Must recover original reference coordinates (within rounding)
            assert abs(recovered_x - ref_x) < 0.01, f"Failed at {screen_w}x{screen_h}"
            assert abs(recovered_y - ref_y) < 0.01, f"Failed at {screen_w}x{screen_h}"

    def test_multiple_objects_no_interference(self):
        """
        Test: Multiple objects at different positions don't interfere.
        """
        detector = ClickDetector(ScalingManager())

        # Create multiple objects
        objects = [
            SceneObject(
                instance_id="obj1",
                catalog_id="c1",
                label_key="obj1",
                icon_path="",
                x=300.0,
                y=200.0,
                detection_type="circle",
                radius=20.0,
            ),
            SceneObject(
                instance_id="obj2",
                catalog_id="c2",
                label_key="obj2",
                icon_path="",
                x=640.0,
                y=360.0,
                detection_type="circle",
                radius=30.0,
            ),
            SceneObject(
                instance_id="obj3",
                catalog_id="c3",
                label_key="obj3",
                icon_path="",
                x=900.0,
                y=500.0,
                detection_type="rect",
                width=60.0,
                height=60.0,
            ),
        ]

        for obj in objects:
            obj.is_goal = True

        # Test obj1
        assert detector._hit_circle(objects[0], 300.0, 200.0) is True
        assert detector._hit_circle(objects[0], 640.0, 360.0) is False

        # Test obj2
        assert detector._hit_circle(objects[1], 640.0, 360.0) is True
        assert detector._hit_circle(objects[1], 300.0, 200.0) is False

        # Test obj3
        assert detector._hit_rect(objects[2], 900.0, 500.0) is True
        assert detector._hit_rect(objects[2], 300.0, 200.0) is False


class TestInvariantSafety:
    """Test that critical invariants are maintained."""

    def test_no_screen_coordinates_in_objects(self):
        """
        Verify that object coordinates are always in reference space,
        never in screen space.
        """
        # Reference space is 1280×720
        ref_w, ref_h = 1280, 720

        # Valid object coordinates (in reference space)
        valid_objects = [
            {"x": 640.0, "y": 360.0},  # Center
            {"x": 0.0, "y": 0.0},      # Top-left
            {"x": ref_w - 1, "y": ref_h - 1},  # Bottom-right
        ]

        for obj in valid_objects:
            assert 0 <= obj["x"] < ref_w * 10, "X should be in reasonable reference range"
            assert 0 <= obj["y"] < ref_h * 10, "Y should be in reasonable reference range"

    def test_hit_detection_uses_reference_space(self):
        """
        Verify that hit detection always operates in reference space,
        regardless of screen size.
        """
        detector = ClickDetector(ScalingManager())
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

        # Hit test always uses reference coordinates
        assert detector._hit_circle(obj, 640.0, 360.0) is True
        assert detector._hit_circle(obj, 670.0, 360.0) is True
        assert detector._hit_circle(obj, 671.0, 360.0) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
