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

## Chrome: what the core draws for every theme

The skin paints the atmosphere; the **chrome** is what the player reads, and it is
identical everywhere so that switching theme never changes what a screen means.

| Element | Where | Notes |
|---------|-------|-------|
| Game wordmark | main state | `game_config.title_key` resolved through the language manager, else the game id turned into words. It travels through `_state_title_text()`, so every skin renders it in its own typography. |
| Title scrim + rule | every state with a title | A soft glow tinted with `background_overlay` (a black band would cut across the kids sky) and an accent rule that closes the header band. |
| Breadcrumb | scenes | The level the scene list belongs to. Without it the screen could be any level's. |
| Icon caption | main / pause | The word under each icon glyph, on one shared baseline: skins float, bounce and arc the buttons, the words stay in line. |
| Primary action | main / pause | The first entry (Play, Continue, Resume) is drawn `PRIMARY_SCALE` larger and carries the `play` glyph, because on the main menu `goto_levels` means Play, not "level list". |
| Focus bar | main / pause | Accent bar under the caption of the button being pointed at. |
| Settings row | settings | One grid: icon column, label, control, value. Sliders and toggles share it, the value pill has one width, and the volume shows its percentage. Rows are grouped under AUDIO / GENERAL / DISPLAY headers. |
| Level / scene card | levels / scenes | Caption over a baked gradient, name resolved from the strings (never a raw id), padlock badge and dimming when locked. |
| Edge fade | carousel states | The screen edge fades out on the side the carousel continues on - and only on that side, so the first card is never dimmed for nothing. |
| Build line | main state | `v<version>` from game_config, in the bottom corner of the safe area. |

Tooltips are anchored **under the element** they describe (above it when there
is no room), never to the pointer: a tip that follows the cursor covers the
button next to the one being read, and on a touch screen there is no cursor to
follow at all.

Everything a player has to read or hit lives inside the safe area (`SAFE_X`,
`SAFE_TOP`, `SAFE_BOTTOM`): menus are also shown on TVs and on phones with
rounded corners. `pytest tests/test_menu_chrome.py` checks the corner chrome
against it, captions included.

Layout lives in reference space (1280x720) as constants at the top of
`engine/menu_system.py`; a theme overrides one by declaring the layout key named
next to it (`main_row_center_y`, `card_row_center_y`, `game_title_y`,
`game_title_font_size`, `primary_scale`, `icon_labels`, `icon_label_size`,
`icon_label_gap`). The shipped themes no longer carry `btn_y_start` or
`title_y_offset`: each had its own (a row centre of 200 on kids against 560 on
android_std), so switching theme moved the whole menu up and down the screen and
pushed the scene cards off the bottom edge.

The settings group headers need three keys in every language:
`settings_group_audio`, `settings_group_general`, `settings_group_display`.

Corner chrome (back, quit) sets `MenuButton.fixed`: it is excluded from the
carousel scroll, from its zoom and from the scroll extent. That flag used to be
inferred from the coordinates, and the corner quit button was extending
`max_scroll_x`, so the main menu drifted sideways.

Skins that render the title themselves must ask the core for the size and the
offset - `ms._state_title_size()`, `ms._state_title_y()` - instead of reading
`title_font_size` from the theme: the main state uses the larger wordmark size
and every other state the header size.

## Icon sets

Each theme ships the complete set under `engine/assets/themes/<id>/icons/`, plus
the universal fallback in `engine/assets/icons/system/`:

```
play  levels  settings  quit  back  new_game
audio  sfx  language  fullscreen  resolution  vibration  lock
```

`audio` is music and `sfx` is sound effects; `resolution` and `fullscreen` are
two different settings. They shared one icon each until the sets were completed,
because `get_icon` aliased both actions onto the same file.

The sets are **generated**, not authored:

```powershell
python tools/gen_theme_icons.py                 # every theme + the system set
python tools/gen_theme_icons.py --theme kids    # one theme
```

One geometry per icon, one style per theme (stroke, plate, glow, palette), drawn
with pygame on a supersampled canvas. Adding an icon means adding a geometry
function and a name in `ICON_NAMES` - never cutting a sprite sheet again: the
sets that were cut from one had the captions of the sheet baked into the PNGs
("Material Design", "CARTOON KIDS (Colorful ...)"), and the menu drew them as
ghost text over the buttons.

The tool also refreshes `games/<id>/ui_theme/icons/`, the per-game copy the
editor harvests, which overrides the theme set at runtime; without that step a
shipped game keeps the old sprites. `pytest tests/test_menu_chrome.py` checks
that every theme has the complete set and that the actions that mean different
things get different icons.

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
| `behind_button(ms, screen, b, draw_rect, is_locked)` | per button, behind it (**not** on the settings rows: there the core owns the row surface) | nothing |
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
  "colors":     { "row_bg": [255, 255, 255, 230] },
  "layout":     { "main_row_center_y": 424, "card_row_center_y": 396,
                  "game_title_y": 96, "game_title_font_size": 78,
                  "icon_labels": true, "icon_label_size": 22 },
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

`colors.row_bg` is the band behind a settings row. It has its own key because a
theme tunes `btn_normal` for a small chip - cyber_neon paints it fully saturated
magenta - and that colour is unusable across the full width of a row. Without
the key the engine falls back to `slider_bg`, the control surface every theme
already defines. `row_value_bg()` derives the value pill from it, so a light
theme sinks the pill and a dark one lifts it.

## Adding a skin

1. `engine/assets/themes/<id>/theme.json` with `"id": "<id>"` and the sections above.
   Add a style entry in `tools/gen_theme_icons.py::STYLES` and run it, so the
   theme starts with its complete icon set.
2. `engine/menu_skins/<id>_skin.py`: subclass `DefaultSkin` (or `MenuSkin` for a bare
   look), set `id = "<id>"`, override the hooks you need.
3. Register it in `engine/menu_skins/__init__.py` (`_REGISTRY`).
4. Add the id to `SKIN_THEMES` in `tests/test_menu_skins.py`: the suite then checks that
   it draws a full frame, survives reduced motion, a resize and a corrupt theme.

The editor applies a theme to a game from the dashboard (game settings): the theme folder
is copied into `games/<id>/ui_theme/` with a staged swap, so a failed copy leaves the
previous theme in place.
