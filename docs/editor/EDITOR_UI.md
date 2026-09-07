# Editor UI — chrome layout rules

How the editor chrome (top bar, canvas toolbar, status bar, side panels) is laid
out, and the two rules that keep it from breaking. Verified by
`pytest tests/test_editor_ui_layout.py` and `pytest tests/test_catalog_tags.py`.

The editor draws in immediate mode: every frame recomputes the whole layout. That
is cheap and simple, but it makes two classes of mistake easy, and both of them
had shipped:

- **geometry written twice** — the renderer draws a button at one size and the
  input handler hit-tests a constant next to it. They drift apart the moment a
  label, a translation or the UI scale changes.
- **geometry written once, in pixels** — a width chosen by eye for the English
  label at UI scale 1.0. German at scale 1.5 clips it and pushes whatever comes
  after it off the edge.

## Rule 1 — a widget is as wide as what it has to show

Never hardcode the width of something that contains text. Measure it:

```python
from editor.ui.draw import _button_w, _text_wh

width = _button_w(label, "sm", icon="save", min_w=STATUS_BTN_MIN_W)
```

`_button_w()` reproduces the padding `_button()` lays its content out with
(`BUTTON_PAD_X` on each side, `BUTTON_ICON_GAP` between icon and label) and
follows the current UI scale, because `_text_wh()` measures the font actually in
use. Use `min_w` when a row of buttons should not look ragged, never as the width
itself.

The same applies to heights that hold text: derive them from the line height
(`_text_wh("Ag", font)[1]`) plus padding, not from a constant.

## Rule 2 — the renderer publishes its hitboxes

Whoever draws an interactive area is the only one allowed to define it. The
renderer stores the rects on the editor and the input handler reads them back:

| Surface | Published as |
|---------|--------------|
| Status bar buttons | `self._status_hitboxes` (`back` / `save` / `play`) |
| Canvas toolbar | `self._get_toolbar_layout()` (shared by draw and hit test) |
| Catalog rows | `self._catalog_item_hitboxes` |
| Outline rows | `self._outline_hitboxes` |
| Scene / object / effect properties | `self._scene_props_hitboxes`, `self._obj_props_hitboxes`, `self._fx_props_hitboxes` |

`editor.mixins.input_handlers.EMPTY_RECT` stands in for a button the current
frame did not draw, so a lookup never has to branch first.

## Canvas toolbar

`RenderCanvasMixin._get_toolbar_layout()` is the single source of the toolbar
geometry: it measures every label, groups the tools and the view toggles
(`TOOLBAR_GROUP_GAP` between the two groups, `TOOLBAR_GAP` inside one) and
**wraps onto a second row** when the canvas is too narrow to hold them. Both
`_r_toolbar()` and `_toolbar_click()` iterate it, so a button can never be drawn
somewhere it cannot be clicked.

Tooltips follow the item id (`tip_mode_*`, `tip_toggle_*`); the one command that
is not a mode, auto-scatter, is mapped in `_TOOLBAR_TIP_KEYS`.

Constants: `TOOLBAR_*` in `editor/constants.py`.

## Canvas HUD

`_r_canvas_hud()` draws the zoom level and, when the pointer is over the canvas,
the scene coordinates under it. It is a translucent pill anchored to the
**bottom right** of the canvas, with its own background so it stays readable over
any scene image. It is deliberately at the opposite corner from the toolbar: the
two used to be drawn on top of each other at the top right.

Constants: `HUD_*` in `editor/constants.py`.

## Shortcuts panel (F1)

`editor/mixins/shortcuts_overlay.py`. F1 toggles it anywhere, Esc closes it, and
while it is open no other key reaches the scene.

Its rows are **parsed from the existing shortcut strings**, `tb_shortcuts` and
`canvas_hints`, written as `KEYS=description` runs separated by spaces. There is
no second list of shortcuts to keep in sync: adding one to those strings adds it
to the panel. A run without `=` is appended to the previous description, so a
translator may write `Del=delete object`.

The status bar shows only the pointer to it (`tb_shortcuts_hint`), not the whole
list.

## Catalog rows

`_catalog_row_metrics()` returns the height, the per-font line heights and the
thumbnail side of one row of the object catalog, all derived from the current UI
scale. A row stacks three lines (id, localized label, tags) next to the
thumbnail, and it is exactly as tall as they need. Raising the UI scale grows the
rows instead of making the lines overlap.

Constants: `CATALOG_ROW_*`, `CATALOG_THUMB_*` in `editor/constants.py`.

## Outline rows

Same rule as the catalog: `_outline_row_h()` is the line height of the row font
plus padding, with `OUTLINE_ROW_H` as the floor, and
`_outline_header_metrics()` sizes the search box, the filter chips and the
counter. `_outline_list_top()` sums those metrics and is the single source for
where the list starts, so the header the renderer draws and the origin the
scroll math assumes cannot drift apart.

Badges (goal, minigame) each keep their own column whether or not a row shows
them: packed from the right, the same badge landed at a different x on every
row and the list could not be scanned down a column.

## Modal dialogs

Every dialog follows the two rules above, and each one computes its layout in a
single place that the renderer, the click handler and the wheel handler all
read:

| Dialog | Single source |
|--------|---------------|
| New catalog object | `_r_newobj_modal()` publishes `self._newobj_hitboxes`; the label column comes from `_newobj_label_col()` and the row height from `_newobj_row_h()` |
| Tag picker | `_r_tag_modal()` publishes `self._tag_modal_hitboxes` |
| Translation editor | `_r_lang_modal()` publishes `self._lang_footer_hitboxes` |
| Icon picker | `_icon_grid_metrics()` returns every rect, plus `visible_rows` and `max_scroll` |
| Project auditor | `_auditor_layout()` returns every rect, plus `item_h`, `visible_rows` and `max_scroll` |
| Music playlist | `_seek_bar_rect()` for the seek bar of a row |

What that replaced, in each of them, was the same defect: the renderer walked
the layout while the handler restated it as literals, and the two had already
drifted - the tag picker hit-tested its close button 4 px above where it was
drawn, the icon picker clamped its scroll with a hand-picked "3 rows are
probably visible", and the playlist put the seek hitbox 10 px left and above
the bar the user could see.

Dialog sizes follow the UI scale and are clamped to the window: the auditor also
stays between the top bar and the status bar, so its footer cannot end up
underneath the latter.

## Localization

No literal user-visible text in the editor code. Tooltips are `tip_*` keys read
through `self._TR(...)`, like every other string (see
[../engine/I18N.md](../engine/I18N.md)). Every new key goes into all five files
under `engine/assets/strings/`, and `pytest tests/test_editor_i18n.py` enforces
it.

The project auditor reports through the same mechanism: every issue it raises
is a `aud_i_*` key with an English default, so the report follows the editor
language instead of always coming out in Italian.

### Catalog tags

A tag chip is drawn with `_TR(f"tag_{tag}", ...)`, a key built at runtime, so
the source-driven check in `test_editor_i18n.py` cannot see it.
`pytest tests/test_catalog_tags.py` covers it instead: every tag any catalog
uses is translated in all five languages, and a tag id is a plain lowercase
ASCII slug.

That second half matters. `TagManager` used to normalize an id with
`strip().lower().replace(" ", "_")`, which leaves accents in, and an older pass
stripped those bytes: "citta" and "casino" were left in the registry as `citt`
and `casin`, ids no `tag_<id>` lookup could ever match. `slugify_tag()` in
`editor/core/tags.py` is now the single normalizer (NFKD, ASCII, non
alphanumerics to underscores) and both harvest and `ensure_tag()` go through it.

### Characters the font can draw

A UI string may only use characters the font stack (Segoe UI, Arial,
DejaVu Sans) actually has. `aud_fix_btn` shipped as "checkmark FIX" and
`aud_rescan` with a circular arrow, and neither glyph exists in any of those
fonts, so the auditor drew an empty box in all five languages. Icons come from
`_draw_shape_icon`, never from a text glyph.
`pytest tests/test_string_glyphs.py` renders every character of every strings
file and fails on anything that comes out as the "missing glyph" box.

## Font lifetime

`editor/ui/draw.py` caches the fonts and everything rendered with them. A
`pygame.Font` that outlived a `pygame.quit()` is a dangling SDL_ttf handle:
using it takes the process down instead of raising, and a later `pygame.init()`
makes the font system report itself healthy while the handles stay dead. So:

- `_font()` rebuilds the set when it is empty or the font system is down, which
  means a layout can be measured before the first frame is ever drawn;
- anything that tears pygame down and brings it back up must call
  `reset_fonts()`. The test suite does it per module, in `tests/conftest.py`.
