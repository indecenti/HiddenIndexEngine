"""
tools/gen_theme_icons.py

Procedural generator for the menu icon sets.

Why this exists
---------------
The shipped icon sets were inconsistent: `default` had no icons at all,
`android_std`/`horror`/`kids` had four of them and each PNG carried the caption
of the contact sheet it had been cut from ("Material Design", "CARTOON KIDS
(Colorful ...)"), which the menu then drew as ghost text over the buttons.
Metaphors were also duplicated - music and SFX shared one gramophone, screen
resolution and fullscreen shared one empty frame.

The set is therefore drawn here instead of being authored by hand: one geometry
per icon, one style per theme. Regenerating is idempotent, every theme gets the
complete set, and adding an icon means adding a geometry function - never
re-cutting a sprite sheet.

Rendering: pygame only (already a runtime dependency). Shapes are drawn on a
supersampled canvas and smoothscaled down, which is what gives the antialiased
edges pygame.draw does not provide on its own.

Usage
-----
    python tools/gen_theme_icons.py                 # every theme + system set
    python tools/gen_theme_icons.py --theme kids    # one theme
    python tools/gen_theme_icons.py --no-sync-games # skip the games/ copies
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from engine.utils import get_logger  # noqa: E402

logger = get_logger(__name__)

# Output size of one icon, and the supersampling factor used while drawing.
# 512 is the largest size a menu button ever asks for (icon_btn_size 150 at a
# 2160p UI scale); 4x supersampling is what removes the stair-stepping from
# pygame.draw, which has no antialiasing for thick primitives.
ICON_SIZE = 512
SUPERSAMPLE = 4
CANVAS = ICON_SIZE * SUPERSAMPLE

# Fraction of the canvas occupied by the glyph when the style draws no plate.
GLYPH_INSET = 0.80
# Same, when a plate is drawn behind: the glyph has to breathe inside it.
GLYPH_INSET_PLATED = 0.56

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

# Colour that punches a hole through a filled glyph: pygame.draw writes the raw
# RGBA, so drawing with alpha 0 clears the pixels and lets the plate show.
ERASE: RGBA = (0, 0, 0, 0)

# The icon names the menu asks for (engine/menu_theme.py::get_icon aliases).
ICON_NAMES = (
    "play", "levels", "settings", "quit", "back", "new_game",
    "audio", "sfx", "language", "fullscreen", "resolution", "vibration",
    "lock",
)


# ── Drawing primitives (round-capped strokes on a supersampled surface) ──────

def _pt(box: pygame.Rect, u: float, v: float) -> tuple[float, float]:
    """Map normalised glyph coordinates (0..1) to pixels inside `box`."""
    return (box.x + u * box.w, box.y + v * box.h)


def stroke_path(surf: pygame.Surface, pts: list[tuple[float, float]],
                width: float, color: RGBA, closed: bool = False) -> None:
    """Draw a polyline with round caps and joins.

    pygame.draw.lines has no round caps, so a thick polyline shows notched
    corners at every vertex. Drawing quad per segment plus a disc per vertex is
    the cheapest way to get the rounded look at supersampled resolution.
    """
    if len(pts) < 2:
        return
    half = max(1.0, width / 2.0)
    seq = list(pts) + ([pts[0]] if closed else [])
    for (x1, y1), (x2, y2) in zip(seq, seq[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = -dy / length * half, dx / length * half
        pygame.draw.polygon(surf, color, [
            (x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
            (x2 - nx, y2 - ny), (x1 - nx, y1 - ny),
        ])
    for x, y in seq:
        pygame.draw.circle(surf, color, (int(round(x)), int(round(y))), int(round(half)))


def arc_points(cx: float, cy: float, rx: float, ry: float,
               a0: float, a1: float, steps: int = 96) -> list[tuple[float, float]]:
    """Sample an elliptical arc (degrees, clockwise on screen axes)."""
    out: list[tuple[float, float]] = []
    for i in range(steps + 1):
        ang = math.radians(a0 + (a1 - a0) * i / steps)
        out.append((cx + math.cos(ang) * rx, cy + math.sin(ang) * ry))
    return out


def stroke_ring(surf: pygame.Surface, center: tuple[float, float], radius: float,
                width: float, color: RGBA, a0: float = 0.0, a1: float = 360.0) -> None:
    """Stroke a circular arc with round caps."""
    cx, cy = center
    closed = abs((a1 - a0) - 360.0) < 1e-6
    pts = arc_points(cx, cy, radius, radius, a0, a1 - (360.0 / 96 if closed else 0.0))
    stroke_path(surf, pts, width, color, closed=closed)


def rounded_rect(surf: pygame.Surface, rect: pygame.Rect, radius: float,
                 color: RGBA, width: float = 0.0) -> None:
    """Rounded rectangle, filled (width 0) or stroked."""
    pygame.draw.rect(surf, color, rect, width=int(round(width)),
                     border_radius=int(round(radius)))


def blur(surf: pygame.Surface, factor: float = 0.12) -> pygame.Surface:
    """Cheap gaussian-ish blur: smoothscale down and back up."""
    w, h = surf.get_size()
    small = (max(2, int(w * factor)), max(2, int(h * factor)))
    return pygame.transform.smoothscale(
        pygame.transform.smoothscale(surf, small), (w, h))


# ── Style of one theme ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class IconStyle:
    """How one theme paints the shared geometry."""

    stroke: RGB                       # main glyph colour
    accent: RGB                       # secondary detail colour
    width: float = 0.085              # stroke width, fraction of the glyph box
    plate: str = "none"               # "none" | "circle" | "squircle"
    plate_fill: RGBA = (0, 0, 0, 0)
    plate_border: RGBA = (0, 0, 0, 0)
    plate_border_w: float = 0.0       # fraction of the canvas
    glow: RGBA | None = None          # neon halo around the glyph
    shadow_alpha: int = 0             # drop shadow under the glyph
    filled: bool = False              # solid glyphs instead of strokes
    palette: tuple[RGB, ...] = field(default_factory=tuple)  # per-icon plate tint

    def plate_color(self, name: str) -> RGBA:
        """Plate fill for one icon: cycles `palette` when the theme has one."""
        if not self.palette:
            return self.plate_fill
        tint = self.palette[ICON_NAMES.index(name) % len(self.palette)]
        return (*tint, self.plate_fill[3] if len(self.plate_fill) > 3 else 255)


STYLES: dict[str, IconStyle] = {
    # Universal fallback set: neutral, legible on any background.
    "system": IconStyle(
        stroke=(233, 238, 247), accent=(150, 170, 205),
        width=0.082, shadow_alpha=110,
    ),
    # Clean/minimal: thin line work, no plate, soft depth.
    "default": IconStyle(
        stroke=(236, 240, 248), accent=(124, 168, 244),
        width=0.076, shadow_alpha=120,
    ),
    # Material-ish: solid glyph knocked out of a coloured disc.
    "android_std": IconStyle(
        stroke=(255, 255, 255), accent=(255, 255, 255),
        width=0.105, plate="circle", plate_fill=(62, 96, 226, 255),
        shadow_alpha=90, filled=True,
    ),
    # Retro-futuristic: neon stroke over a dark squircle, magenta accent.
    "cyber_neon": IconStyle(
        stroke=(64, 245, 205), accent=(255, 74, 205),
        width=0.080, plate="squircle", plate_fill=(6, 24, 26, 235),
        plate_border=(64, 245, 205, 255), plate_border_w=0.022,
        glow=(64, 245, 205, 150),
    ),
    # Nightmare: bone stroke, blood accent, heavy shadow, no plate.
    "horror": IconStyle(
        stroke=(221, 214, 202), accent=(150, 26, 26),
        width=0.090, shadow_alpha=190,
    ),
    # Playground: chunky white glyph on a bright rounded plate.
    "kids": IconStyle(
        stroke=(255, 255, 255), accent=(255, 236, 120),
        width=0.135, plate="squircle", plate_fill=(0, 0, 0, 255),
        plate_border=(255, 255, 255, 235), plate_border_w=0.020,
        shadow_alpha=120,
        palette=((242, 96, 122), (250, 168, 60), (86, 186, 236), (108, 198, 120),
                 (168, 130, 232), (240, 130, 180), (96, 200, 200)),
    ),
    # Noir: brass line work on an aged dark disc.
    "mystery": IconStyle(
        stroke=(228, 195, 128), accent=(150, 108, 46),
        width=0.078, plate="circle", plate_fill=(26, 22, 18, 240),
        plate_border=(190, 152, 84, 255), plate_border_w=0.016,
        shadow_alpha=140,
    ),
}


# ── Icon geometry (shared by every theme) ────────────────────────────────────
#
# Each function draws one icon inside `box` on a transparent surface, using
# `stroke` for the main shape and `accent` for the secondary detail. `w` is the
# stroke width in pixels, already resolved from the style.

def icon_play(s, box, w, stroke, accent, filled) -> None:
    pts = [_pt(box, 0.16, 0.06), _pt(box, 0.92, 0.50), _pt(box, 0.16, 0.94)]
    if filled:
        pygame.draw.polygon(s, stroke, pts)
        stroke_path(s, pts, w * 0.9, stroke, closed=True)   # rounds the corners
    else:
        stroke_path(s, pts, w, stroke, closed=True)


def icon_levels(s, box, w, stroke, accent, filled) -> None:
    """Three isometric plates: a stack of levels, not a list of rows."""
    for i, (cy, col) in enumerate(((0.80, stroke), (0.52, stroke), (0.24, accent))):
        pts = [_pt(box, 0.50, cy - 0.17), _pt(box, 0.95, cy),
               _pt(box, 0.50, cy + 0.17), _pt(box, 0.05, cy)]
        if filled and i == 2:
            pygame.draw.polygon(s, col, pts)
        stroke_path(s, pts, w, col, closed=True)


def icon_settings(s, box, w, stroke, accent, filled) -> None:
    cx, cy = _pt(box, 0.5, 0.5)
    r_out, r_in = box.w * 0.46, box.w * 0.335
    teeth, pts = 8, []
    for i in range(teeth * 4):
        seg = i % 4
        radius = r_out if seg in (1, 2) else r_in
        ang = math.radians(i * (360.0 / (teeth * 4)) - 90 + 5.5)
        pts.append((cx + math.cos(ang) * radius, cy + math.sin(ang) * radius))
    if filled:
        pygame.draw.polygon(s, stroke, pts)
        pygame.draw.circle(s, ERASE, (int(cx), int(cy)), int(box.w * 0.155))
    else:
        stroke_path(s, pts, w, stroke, closed=True)
        stroke_ring(s, (cx, cy), box.w * 0.155, w, accent)


def icon_quit(s, box, w, stroke, accent, filled) -> None:
    cx, cy = _pt(box, 0.5, 0.56)
    stroke_ring(s, (cx, cy), box.w * 0.38, w, stroke, a0=-58, a1=238)
    stroke_path(s, [(cx, cy - box.h * 0.50), (cx, cy - box.h * 0.10)], w, accent)


def icon_back(s, box, w, stroke, accent, filled) -> None:
    stroke_path(s, [_pt(box, 0.92, 0.50), _pt(box, 0.14, 0.50)], w, stroke)
    stroke_path(s, [_pt(box, 0.46, 0.14), _pt(box, 0.10, 0.50),
                    _pt(box, 0.46, 0.86)], w, stroke)


def icon_new_game(s, box, w, stroke, accent, filled) -> None:
    """A fresh sheet with a plus: start over, not 'add an item'."""
    card = pygame.Rect(int(box.x + box.w * 0.12), int(box.y + box.h * 0.06),
                       int(box.w * 0.66), int(box.h * 0.88))
    if filled:
        rounded_rect(s, card, box.w * 0.10, stroke)
    else:
        rounded_rect(s, card, box.w * 0.10, stroke, width=w)
    cx, cy = card.centerx, card.centery
    arm = box.w * 0.17
    # On a filled card the plus is punched out (alpha 0), otherwise a white
    # plus on a white sheet would be invisible.
    plus = ERASE if filled else accent
    stroke_path(s, [(cx - arm, cy), (cx + arm, cy)], w, plus)
    stroke_path(s, [(cx, cy - arm), (cx, cy + arm)], w, plus)


def icon_audio(s, box, w, stroke, accent, filled) -> None:
    """Music: a beamed pair of notes."""
    x1, x2 = box.x + box.w * 0.30, box.x + box.w * 0.86
    top, bottom = box.y + box.h * 0.10, box.y + box.h * 0.74
    stroke_path(s, [(x1, bottom), (x1, top), (x2, top - box.h * 0.06), (x2, bottom)],
                w, stroke)
    stroke_path(s, [(x1, top), (x2, top - box.h * 0.06)], w * 1.6, accent)
    for cx in (x1, x2):
        r = box.w * 0.135
        pygame.draw.ellipse(s, stroke, pygame.Rect(
            int(cx - r * 1.25), int(bottom - r * 0.85), int(r * 2.5), int(r * 1.7)))


def icon_sfx(s, box, w, stroke, accent, filled) -> None:
    """Sound effects: speaker cone plus two emission arcs."""
    left, mid = box.x + box.w * 0.06, box.x + box.w * 0.34
    cy = box.y + box.h * 0.50
    body = [(left, cy - box.h * 0.16), (mid, cy - box.h * 0.16),
            (box.x + box.w * 0.56, cy - box.h * 0.42),
            (box.x + box.w * 0.56, cy + box.h * 0.42),
            (mid, cy + box.h * 0.16), (left, cy + box.h * 0.16)]
    if filled:
        pygame.draw.polygon(s, stroke, body)
        stroke_path(s, body, w * 0.8, stroke, closed=True)
    else:
        stroke_path(s, body, w, stroke, closed=True)
    for i, r in enumerate((0.20, 0.34)):
        stroke_ring(s, (box.x + box.w * 0.58, cy), box.w * r, w,
                    accent if i else stroke, a0=-52, a1=52)


def icon_language(s, box, w, stroke, accent, filled) -> None:
    cx, cy = _pt(box, 0.5, 0.5)
    r = box.w * 0.46
    stroke_ring(s, (cx, cy), r, w, stroke)
    stroke_path(s, arc_points(cx, cy, r * 0.42, r, -90, 90), w * 0.8, accent)
    stroke_path(s, arc_points(cx, cy, r * 0.42, r, 90, 270), w * 0.8, accent)
    stroke_path(s, [(cx - r, cy), (cx + r, cy)], w * 0.8, accent)
    stroke_path(s, arc_points(cx, cy + r * 0.62, r * 0.86, r * 0.42, 180, 360),
                w * 0.7, accent)
    stroke_path(s, arc_points(cx, cy - r * 0.62, r * 0.86, r * 0.42, 0, 180),
                w * 0.7, accent)


def icon_fullscreen(s, box, w, stroke, accent, filled) -> None:
    """Corner brackets plus a diagonal expand arrow (a centred X reads 'close')."""
    arm = box.w * 0.30
    corners = ((0.06, 0.06, 1, 1), (0.94, 0.06, -1, 1),
               (0.06, 0.94, 1, -1), (0.94, 0.94, -1, -1))
    for u, v, sx, sy in corners:
        x, y = _pt(box, u, v)
        stroke_path(s, [(x + arm * sx, y), (x, y), (x, y + arm * sy)], w, stroke)
    cx, cy = _pt(box, 0.5, 0.5)
    d, head = box.w * 0.17, box.w * 0.09
    stroke_path(s, [(cx - d, cy + d), (cx + d, cy - d)], w * 0.75, accent)
    stroke_path(s, [(cx + d - head, cy - d), (cx + d, cy - d),
                    (cx + d, cy - d + head)], w * 0.75, accent)
    stroke_path(s, [(cx - d + head, cy + d), (cx - d, cy + d),
                    (cx - d, cy + d - head)], w * 0.75, accent)


def icon_resolution(s, box, w, stroke, accent, filled) -> None:
    """A display with its stand, plus the ratio marks that name a resolution."""
    screen = pygame.Rect(int(box.x + box.w * 0.04), int(box.y + box.h * 0.12),
                         int(box.w * 0.92), int(box.h * 0.60))
    rounded_rect(s, screen, box.w * 0.09, stroke, width=w)
    stroke_path(s, [(box.x + box.w * 0.36, box.y + box.h * 0.88),
                    (box.x + box.w * 0.64, box.y + box.h * 0.88)], w, stroke)
    stroke_path(s, [(box.x + box.w * 0.50, box.y + box.h * 0.72),
                    (box.x + box.w * 0.50, box.y + box.h * 0.88)], w, stroke)
    inner = pygame.Rect(int(box.x + box.w * 0.20), int(box.y + box.h * 0.26),
                        int(box.w * 0.44), int(box.h * 0.30))
    rounded_rect(s, inner, box.w * 0.04, accent, width=w * 0.7)


def icon_vibration(s, box, w, stroke, accent, filled) -> None:
    phone = pygame.Rect(int(box.x + box.w * 0.33), int(box.y + box.h * 0.08),
                        int(box.w * 0.34), int(box.h * 0.84))
    rounded_rect(s, phone, box.w * 0.10, stroke, width=w)
    stroke_path(s, [(phone.centerx - box.w * 0.05, phone.bottom - box.h * 0.09),
                    (phone.centerx + box.w * 0.05, phone.bottom - box.h * 0.09)],
                w * 0.8, stroke)
    for side in (-1, 1):
        for i, r in enumerate((0.10, 0.20)):
            x = phone.centerx + side * box.w * (0.24 + r)
            stroke_path(s, [(x, box.y + box.h * (0.34 - i * 0.06)),
                            (x, box.y + box.h * (0.66 + i * 0.06))],
                        w * 0.8, accent if i else stroke)


def icon_lock(s, box, w, stroke, accent, filled) -> None:
    body = pygame.Rect(int(box.x + box.w * 0.10), int(box.y + box.h * 0.44),
                       int(box.w * 0.80), int(box.h * 0.50))
    if filled:
        rounded_rect(s, body, box.w * 0.12, stroke)
    else:
        rounded_rect(s, body, box.w * 0.12, stroke, width=w)
    stroke_ring(s, (body.centerx, box.y + box.h * 0.44), box.w * 0.26, w, stroke,
                a0=180, a1=360)
    keyhole = ERASE if (filled and accent[:3] == stroke[:3]) else accent
    pygame.draw.circle(s, keyhole, (int(body.centerx), int(body.centery)),
                       int(box.w * 0.09))


GEOMETRY = {
    "play": icon_play, "levels": icon_levels, "settings": icon_settings,
    "quit": icon_quit, "back": icon_back, "new_game": icon_new_game,
    "audio": icon_audio, "sfx": icon_sfx, "language": icon_language,
    "fullscreen": icon_fullscreen, "resolution": icon_resolution,
    "vibration": icon_vibration, "lock": icon_lock,
}


# ── Composition ──────────────────────────────────────────────────────────────

def draw_plate(surf: pygame.Surface, style: IconStyle, name: str) -> None:
    """Paint the plate behind the glyph (disc or squircle), if the style has one."""
    if style.plate == "none":
        return
    pad = CANVAS * 0.045
    rect = pygame.Rect(int(pad), int(pad), int(CANVAS - pad * 2), int(CANVAS - pad * 2))
    fill = style.plate_color(name)
    border_w = style.plate_border_w * CANVAS
    if style.plate == "circle":
        pygame.draw.circle(surf, fill, rect.center, rect.w // 2)
        if border_w > 0:
            stroke_ring(surf, rect.center, rect.w / 2 - border_w / 2,
                        border_w, style.plate_border)
    else:
        radius = rect.w * 0.24
        rounded_rect(surf, rect, radius, fill)
        if border_w > 0:
            rounded_rect(surf, rect, radius, style.plate_border, width=border_w)


def render_icon(name: str, style: IconStyle) -> pygame.Surface:
    """Draw one icon at output resolution, plate + shadow + glow + glyph."""
    base = pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)
    draw_plate(base, style, name)

    inset = GLYPH_INSET_PLATED if style.plate != "none" else GLYPH_INSET
    side = CANVAS * inset
    box = pygame.Rect(int((CANVAS - side) / 2), int((CANVAS - side) / 2),
                      int(side), int(side))

    glyph = pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)
    width = style.width * box.w
    GEOMETRY[name](glyph, box, width, (*style.stroke, 255), (*style.accent, 255),
                   style.filled)

    if style.shadow_alpha:
        shadow = glyph.copy()
        shadow.fill((0, 0, 0, style.shadow_alpha), special_flags=pygame.BLEND_RGBA_MULT)
        shadow = blur(shadow, 0.10)
        base.blit(shadow, (0, int(CANVAS * 0.018)))

    if style.glow:
        halo = glyph.copy()
        halo.fill(style.glow, special_flags=pygame.BLEND_RGBA_MULT)
        halo = blur(halo, 0.07)
        base.blit(halo, (0, 0))
        base.blit(halo, (0, 0))          # twice: neon needs a hotter core

    base.blit(glyph, (0, 0))
    return pygame.transform.smoothscale(base, (ICON_SIZE, ICON_SIZE))


def write_set(out_dir: Path, style: IconStyle, names=ICON_NAMES) -> int:
    """Render `names` into `out_dir`, returning how many files were written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        pygame.image.save(render_icon(name, style), str(out_dir / f"{name}.png"))
    return len(names)


def sync_game_icons(root: Path, theme_id: str) -> list[str]:
    """Refresh the per-game copies of a theme's icons (editor harvest).

    A game keeps its own `ui_theme/icons/`, which overrides the theme set at
    runtime: regenerating only the theme would leave the shipped games on the
    old sprites.
    """
    import json
    import shutil

    touched: list[str] = []
    games = root / "games"
    if not games.exists():
        return touched
    for game in sorted(p for p in games.iterdir() if p.is_dir()):
        theme_file = game / "ui_theme" / "theme.json"
        if not theme_file.exists():
            continue
        try:
            with open(theme_file, "r", encoding="utf-8") as fh:
                if json.load(fh).get("id") != theme_id:
                    continue
        except (OSError, ValueError) as exc:
            logger.warning("theme.json unreadable for '%s': %s", game.name, exc)
            continue
        src = root / "engine" / "assets" / "themes" / theme_id / "icons"
        dst = game / "ui_theme" / "icons"
        dst.mkdir(parents=True, exist_ok=True)
        for png in src.glob("*.png"):
            shutil.copy2(png, dst / png.name)
        touched.append(game.name)
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the menu icon sets.")
    parser.add_argument("--theme", action="append", default=None,
                        help="only this theme (repeatable); default: all")
    parser.add_argument("--no-sync-games", action="store_true",
                        help="do not refresh the games/<id>/ui_theme/icons copies")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((64, 64))

    root = Path(__file__).resolve().parent.parent
    targets = args.theme or list(STYLES.keys())
    unknown = [t for t in targets if t not in STYLES]
    if unknown:
        logger.error("unknown theme(s): %s", ", ".join(unknown))
        return 2

    for theme_id in targets:
        style = STYLES[theme_id]
        if theme_id == "system":
            out = root / "engine" / "assets" / "icons" / "system"
        else:
            out = root / "engine" / "assets" / "themes" / theme_id / "icons"
        count = write_set(out, style)
        logger.info("theme '%s': %d icons -> %s", theme_id, count, out)
        if theme_id != "system" and not args.no_sync_games:
            for game in sync_game_icons(root, theme_id):
                logger.info("  synced game '%s'", game)

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
