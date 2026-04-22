"""
editor/debug/coordinate_inspector.py

Real-time coordinate inspector for debugging editor/game alignment.
Displays reference space coordinates, screen coordinates, and hit detection info.

Usage:
  Press 'D' in the editor to toggle the coordinate inspector overlay.
"""

import pygame
from editor.constants import TXT_DIM, TXT_HI, BORDER, ACCENT
from editor.ui.draw import _draw_text, _rect


class CoordinateInspector:
    """
    Live coordinate debugging overlay.
    Shows reference, screen, and scene coordinates for the mouse position.
    """

    def __init__(self, editor):
        self.editor = editor
        self.enabled = False
        self.show_grid_coords = True
        self.show_object_info = True
        self.show_hit_info = True

    def toggle(self):
        """Toggle inspector on/off."""
        self.enabled = not self.enabled

    def render(self, screen, mouse_pos):
        """Render coordinate information overlay."""
        if not self.enabled:
            return

        mx, my = mouse_pos
        w, h = screen.get_size()

        # Inspector panel dimensions
        panel_w, panel_h = 400, 300
        panel_x = w - panel_w - 10
        panel_y = 10

        # Draw semi-transparent background
        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill((20, 20, 30, 220))
        screen.blit(overlay, (panel_x, panel_y))

        # Draw border
        border_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(screen, ACCENT, border_rect, 2)

        # Y position for text lines
        y = panel_y + 10
        line_h = 20

        # Title
        _draw_text(
            screen,
            "COORDINATE INSPECTOR",
            "sm",
            ACCENT,
            panel_x + 10,
            y,
            panel_w - 20,
        )
        y += line_h + 5

        # Convert coordinates
        if self.editor.state == 1:  # STATE_MAIN
            ref_x, ref_y = self.editor._s2r(mx, my)
            screen_x, screen_y = mx, my

            # Line 1: Mouse screen coordinates
            _draw_text(
                screen,
                f"Screen:  ({int(screen_x):4d}, {int(screen_y):4d}) px",
                "sm",
                TXT_DIM,
                panel_x + 10,
                y,
                panel_w - 20,
            )
            y += line_h

            # Line 2: Reference space coordinates
            _draw_text(
                screen,
                f"Ref:     ({ref_x:7.1f}, {ref_y:7.1f})",
                "sm",
                TXT_HI,
                panel_x + 10,
                y,
                panel_w - 20,
            )
            y += line_h

            # Line 3: Zoom and pan info
            _draw_text(
                screen,
                f"Zoom: {self.editor.zoom:.2f}x | Pan: ({self.editor.origin_x:.0f}, {self.editor.origin_y:.0f})",
                "sm",
                TXT_DIM,
                panel_x + 10,
                y,
                panel_w - 20,
            )
            y += line_h + 10

            # Grid coordinates
            if self.show_grid_coords and self.editor.show_grid:
                grid_x = int(ref_x // self.editor.grid_size) * self.editor.grid_size
                grid_y = int(ref_y // self.editor.grid_size) * self.editor.grid_size
                _draw_text(
                    screen,
                    f"Grid ({self.editor.grid_size}): ({int(grid_x):4d}, {int(grid_y):4d})",
                    "sm",
                    TXT_DIM,
                    panel_x + 10,
                    y,
                    panel_w - 20,
                )
                y += line_h + 10

            # Object under cursor info
            if self.show_object_info:
                hits = self.editor._objs_at(ref_x, ref_y)
                if hits:
                    idx = hits[0]
                    obj = self.editor.scene_data["objects"][idx]
                    cat_id = obj.get("catalog_id", "?")
                    dt = obj.get("detection_type", "?")

                    _draw_text(
                        screen, "OBJECT UNDER CURSOR:", "sm", ACCENT, panel_x + 10, y,
                        panel_w - 20
                    )
                    y += line_h

                    _draw_text(
                        screen,
                        f"  ID: {cat_id} ({dt})",
                        "sm",
                        TXT_DIM,
                        panel_x + 10,
                        y,
                        panel_w - 20,
                    )
                    y += line_h

                    x, y_obj = obj.get("x", 0), obj.get("y", 0)
                    _draw_text(
                        screen,
                        f"  Pos: ({x:.1f}, {y_obj:.1f})",
                        "sm",
                        TXT_DIM,
                        panel_x + 10,
                        y,
                        panel_w - 20,
                    )
                    y += line_h

                    if dt == "circle":
                        r = obj.get("radius", 30)
                        _draw_text(
                            screen,
                            f"  Radius: {r:.1f}",
                            "sm",
                            TXT_DIM,
                            panel_x + 10,
                            y,
                            panel_w - 20,
                        )
                    else:
                        w_obj = obj.get("width", 60)
                        h_obj = obj.get("height", 60)
                        _draw_text(
                            screen,
                            f"  Size: {w_obj:.1f}×{h_obj:.1f}",
                            "sm",
                            TXT_DIM,
                            panel_x + 10,
                            y,
                            panel_w - 20,
                        )
                    y += line_h

                    rot = obj.get("rotation", 0)
                    if rot != 0:
                        _draw_text(
                            screen,
                            f"  Rotation: {rot:.1f}°",
                            "sm",
                            TXT_DIM,
                            panel_x + 10,
                            y,
                            panel_w - 20,
                        )
                else:
                    _draw_text(
                        screen,
                        "(no object)",
                        "sm",
                        TXT_DIM,
                        panel_x + 10,
                        y,
                        panel_w - 20,
                    )
                    y += line_h

            # Footer hint
            y = panel_y + panel_h - 20
            _draw_text(
                screen,
                "Press 'D' to toggle | Press '?' for help",
                "sm",
                TXT_DIM,
                panel_x + 10,
                y,
                panel_w - 20,
            )


class CoordinateDebugHelper:
    """
    Utilities for debugging coordinate misalignment.
    """

    @staticmethod
    def validate_object_consistency(obj):
        """
        Check if object has consistent coordinate definitions.
        Returns list of warnings.
        """
        warnings = []

        dt = obj.get("detection_type", "circle")

        if dt == "circle":
            if "radius" not in obj or obj["radius"] <= 0:
                warnings.append("Circle has invalid or missing radius")
        elif dt == "rect":
            if "width" not in obj or obj["width"] <= 0:
                warnings.append("Rect has invalid or missing width")
            if "height" not in obj or obj["height"] <= 0:
                warnings.append("Rect has invalid or missing height")

        if "x" not in obj or "y" not in obj:
            warnings.append("Object missing x or y coordinate")

        rotation = obj.get("rotation", 0)
        if rotation < 0 or rotation >= 360:
            warnings.append(f"Rotation should be in [0, 360), got {rotation}")

        return warnings

    @staticmethod
    def compare_editor_game_positions(editor_obj, game_obj):
        """
        Compare object position in editor vs game.
        Returns differences if any.
        """
        differences = []

        if abs(editor_obj.get("x", 0) - game_obj.x) > 0.01:
            differences.append(
                f"X mismatch: editor={editor_obj.get('x')}, game={game_obj.x}"
            )

        if abs(editor_obj.get("y", 0) - game_obj.y) > 0.01:
            differences.append(
                f"Y mismatch: editor={editor_obj.get('y')}, game={game_obj.y}"
            )

        if editor_obj.get("detection_type") == "circle":
            if abs(editor_obj.get("radius", 30) - game_obj.radius) > 0.01:
                differences.append(
                    f"Radius mismatch: editor={editor_obj.get('radius')}, game={game_obj.radius}"
                )

        elif editor_obj.get("detection_type") == "rect":
            if abs(editor_obj.get("width", 60) - game_obj.width) > 0.01:
                differences.append(
                    f"Width mismatch: editor={editor_obj.get('width')}, game={game_obj.width}"
                )
            if abs(editor_obj.get("height", 60) - game_obj.height) > 0.01:
                differences.append(
                    f"Height mismatch: editor={editor_obj.get('height')}, game={game_obj.height}"
                )

        return differences
