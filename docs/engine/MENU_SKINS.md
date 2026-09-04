# Menu skins (game menu templates)

The game menus are drawn by a **core** plus a pluggable **skin**.

- **Core** — `engine/menu_system.py`: data, navigation, save/lock, i18n, audio, scroll,
  hit testing, carousel. Identical for every theme.
- **Skin** — `engine/menu_skins/<id>_skin.py`: look and feel only. Selected at runtime
  from `ui_theme` (the theme id in `games/<id>/ui_theme/theme.json`), fallback `default`.

Adding a theme means adding a skin, never touching the core. Themes with no registered
skin fall back to `DefaultSkin`, so nothing regresses.

Shipped skins: `default` (clean), `horror` (nightmare), `kids` (playground),
`cyber_neon` (retro-futuristic), `mystery` (noir). `android_std` has no dedicated skin
and uses `DefaultSkin` as its light variant.

## Hooks

The core calls the skin at fixed points of the frame. The base class
(`engine/menu_skins/base.py`) draws nothing extra, so a skin only overrides what it needs.

| Hook | When | Default |
|------|------|---------|
| `update(ms, dt)` | once per frame, before drawing | advances `self._t` |
| `arrange(ms)` | after `build_buttons`, before scroll/focus | core layout untouched |
| `draw_background_pre(ms, screen, sw, sh)` | over the background, under everything else | nothing |
| `draw_title(ms, screen)` | state title | `ms._draw_state_title(screen)` |
| `button_jitter(ms, b)` | per button, before drawing it | `(0.0, 0.0)` |
| `behind_button(ms, screen, b, draw_rect, is_locked)` | per button, behind it | nothing |
| `draw_overlay(ms, screen, sw, sh)` | over the contents | nothing |

`arrange` may only apply **vertical** offsets: horizontal positions drive the carousel
scroll and the zoom.

Motion knobs read from `theme.motion`: `carousel_zoom` (0.25), `float_amp` (4.0),
`magnetic` (true).

## Fail-soft: a broken skin never takes the menu down

Every hook is invoked through `skin_call(skin, "hook", ...)`. If a hook raises, the
failure is logged **once** with its traceback, the hook is disabled for the session and
the neutral base implementation takes over: the menu keeps working with the core look
instead of crashing on the main menu or spamming one traceback per frame.

The same applies to construction: a skin whose `__init__` raises falls back to
`DefaultSkin`, and then to the neutral `MenuSkin`.

`theme.json` is authored data (the editor harvests it into the game), so skins must not
trust its values. Read them through the coercers in `base.py` - `as_float`, `as_int`,
`as_bool`, `as_rgb` - which return the documented default on malformed input, and clamp
anything that sizes a loop (particle densities) with a module constant.

## Per-frame cost

A menu frame is drawn 60 times a second: nothing that only depends on size/colour/text
may be rebuilt inside the draw path.

- `cached_title(skin, key, build)` — caches the composed title surfaces. `render_spaced`
  performs one `font.render` **per character** per layer, so an uncached title is a large
  share of the frame. **The key must include the SCALED font size**
  (`sm.scale_value(size)`), otherwise the title stays at the old resolution after a
  resize or a fullscreen switch.
- `SurfaceCache(cap)` — bounded LRU for static surfaces (chip shadows, particle glows).
  Eviction is gradual (`popitem(last=False)`, the engine convention): clearing the whole
  dict when it fills rebuilds every surface on the same frame and shows up as a hitch.
- Layers that animate cannot be cached as pixels, but their **surface** can be reused
  (allocate once, `fill((0, 0, 0, 0))` per frame) — see the horror fog.

## Reduced motion (Android / low-end)

`skin.reduced(ms)` is true on the Android runtime. `skin.fx_on(ms, "feature")` returns
false when the theme lists `feature` under `motion.reduced_motion.disable`. Heavy effects
must degrade, the theme identity must survive: keep the cheap parts (sky, plates, tint)
and drop the expensive ones (particles, blur, grain).

## theme.json sections used by the skins

All optional; a theme without them keeps the historical behaviour.

```json
{
  "id": "kids",
  "motion":     { "carousel_zoom": 0.3, "float_amp": 6.0, "magnetic": true,
                  "bounce": true,
                  "reduced_motion": { "disable": ["bounce", "confetti"] } },
  "background": { "mode": "sky", "sky_top": [98, 192, 246],
                  "sky_bottom": [116, 207, 154], "sun": true,
                  "sun_color": [255, 215, 68] },
  "particles":  { "type": "confetti", "density": 22, "color": [255, 122, 162] },
  "typography": { "title": { "family": "...", "spacing": 3 } },
  "decor":      { "card_radius": 24, "card_border": [255, 255, 255],
                  "toy_shadow": [42, 126, 192] }
}
```

`background.mode` (`image`/`sky`/`fog`/`noir`/`shader`) and `particles.type`
(`fireflies`/`confetti`/`dust`/`digital`) are read by the skin that implements them; an
unknown value simply draws nothing.

## Adding a skin

1. `engine/assets/themes/<id>/theme.json` with `"id": "<id>"` and the sections above.
2. `engine/menu_skins/<id>_skin.py`: subclass `DefaultSkin` (or `MenuSkin` for a bare
   look), set `id = "<id>"`, override the hooks you need.
3. Register it in `engine/menu_skins/__init__.py` (`_REGISTRY`).
4. Add the id to `SKIN_THEMES` in `tests/test_menu_skins.py`: the suite then checks that
   it draws a full frame, survives reduced motion, a resize and a corrupt theme.

The editor applies a theme to a game from the dashboard (game settings): the theme folder
is copied into `games/<id>/ui_theme/` with a staged swap, so a failed copy leaves the
previous theme in place.
