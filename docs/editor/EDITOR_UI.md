# Editor UI — chrome layout rules

How the editor chrome (top bar, canvas toolbar, status bar, side panels) is laid
out, and the three rules that keep it from breaking. Verified by
`tests/test_editor_ui_layout.py`, `tests/test_editor_status_bar.py`,
`tests/test_editor_layers_panel.py`, `tests/test_editor_browser_header.py`,
`tests/test_editor_asset_studio.py`, `tests/test_editor_modal_geometry.py`,
`tests/test_catalog_tags.py`, `tests/test_string_encoding.py`,
`tests/test_string_glyphs.py` and `tests/test_source_hygiene.py`.

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
| Status bar text | `self._status_spans` (`msg` / `info` / `hint`), the three runs that share the line |
| Layers panel | `self._layers_hitboxes` (`rows` / `eye` / `lock`), placed by `_layers_columns()` |
| Browser column headers | `_gs_header_rects(column, ...)`, declared once in `_GS_HEADER_BUTTONS` |
| Asset studio sidebar | `_img_editor_metrics()` and the three `_img_editor_colN_rects()` built from it |
| Canvas toolbar | `self._get_toolbar_layout()` (shared by draw and hit test) |
| Catalog rows | `self._catalog_item_hitboxes` |
| Outline rows | `self._outline_hitboxes` |
| Project edit (dashboard) | `_gs_edit_dialog_rect()` for the box, `self._gs_modal_layout` for every section; `_gs_edit_column_fit()` compresses the column when the dialog is short |
| Asset studio | `_img_editor_get_modal_rect()`, called by the renderer as well as the click handler |
| Scene outline | `_outline_hitboxes`, `_outline_list_top()`, `_outline_row_h()` |
| Auto-scatter | `_scatter_hitboxes` |
| Scene / object / effect properties | `self._scene_props_hitboxes`, `self._obj_props_hitboxes`, `self._fx_props_hitboxes` |

`editor.mixins.input_handlers.EMPTY_RECT` stands in for a button the current
frame did not draw, so a lookup never has to branch first.

## Rule 3 — a pixel constant is a pixel constant at scale 1.0

Ctrl+Plus scales the fonts. It does not scale a number written into the source,
so every offset, row height and icon column has to be multiplied by
`_ui_scale()` or derived from the line height. Two helpers do it:
`_ps(value)` in `render_panels.py` for the side panels, and a local `sc(value)`
inside a geometry function for a surface that has its own.

What it looks like when this is missed, all of it found in a screenshot of the
German editor at scale 1.5:

- the asset studio drew its three columns at 10 / 165 / 320 px inside a 480 px
  sidebar, so every heading landed on the column to its left and the labels
  were cut to "AUTO-ZUSCH..."; the footer walked off the left edge of the modal;
- the layers panel put "VIS" and "LOCK" 82 and 52 px from the right edge, which
  is a measurement of the English words at scale 1.0, and drew 24 px icons under
  a font half again as large;
- the browser column headers were a strip of 26x24 rects at -32, -62, -92,
  -122, -152 and -182, so "DUP" became "D..." and the strip ran under the
  column title.

A surface that grows with the scale also has to fit the window it is in.
`_img_editor_scale()` takes the UI scale and reduces it until the studio fits
its modal; `_gs_edit_column_fit()` does the same for the project dialog. Both
have a floor: below it the text stops being readable and the answer is a
smaller window, not a smaller font.

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

The zoom level is a control, not a readout: the pill carries `-`, the
percentage, `+` and a fit button, published as `self._hud_hitboxes` and served
by `_hud_click()` before the canvas sees the click. Zooming used to be reachable
only through F, Z and +/-, which a mouse-only user had no way to discover.

Constants: `HUD_*` in `editor/constants.py`.

## Commands

`editor/commands.py` is the single description of what the editor can do: one
`Command` per feature, with its group, its label, the keys that trigger it and
how to run it (`("call", "_fit_canvas")`, `("menu", "file_auditor")`,
`("mode", "circle")`, or nothing for a binding that is only documentation, like
panning). `needs` says what it acts on (`"scene"`, `"selection"`), which is what
greys it out when there is nothing to act on.

It exists because the editor had 57 keyboard bindings, a File/Edit menu and no
relationship between the two: most features could only be reached by knowing a
letter, and the shortcut panel could only list the 9 that happened to be written
into two hint strings. One table now feeds three things:

- **the F1 panel** (`editor/mixins/shortcuts_overlay.py`) — every binding,
  grouped. `_shortcuts_geometry()` is its single geometry: the columns are the
  fewest that fit the height available (two when they do, more on a short
  window, never splitting a group), and their width follows the longest key and
  the longest label;
- **the command palette** (`editor/mixins/command_center.py`, Ctrl+P) — a
  search box over the localized labels; Enter runs, arrows move, Esc closes.
  It is a modal on the unified stack, so it is app modal like every dialog, and
  it scrolls with the selection instead of drawing a fixed first page;
- **`pytest tests/test_editor_commands.py`**, which refuses a command whose
  method does not exist, whose menu target has no branch in `_exec_menu_cmd`
  (that is how the dead "Save as..." entry was found), whose label is not
  translated in all five languages, or whose advertised shortcut no key handler
  looks at.

`InputHandlersMixin._on_key` stays the authority on what a key does; `keys` in
the table is the documentation of it. Every toggle it performs is a method
(`_toggle_grid`, `_cycle_grid_size`, `_toggle_fullscreen`, ...) so the keyboard,
the canvas toolbar and the palette drive the same code.

Adding a feature means adding a row to `COMMANDS` and its five translations: it
then appears in the panel and in the palette by itself.

The status bar shows the pointer to both (`tb_shortcuts_hint`), not a list.

## Catalog rows

`_catalog_row_metrics()` returns the height, the per-font line heights and the
thumbnail side of one row of the object catalog, all derived from the current UI
scale. A row stacks three lines (id, localized label, tags) next to the
thumbnail, and it is exactly as tall as they need. Raising the UI scale grows the
rows instead of making the lines overlap.

Above the list, `_r_catalog_recent()` draws the objects placed most recently in
this project (`_recent_objects()` / `_note_object_used()`, persisted per project
in `.editor_settings.json`). Placing is the repetitive action of the editor and
the catalog holds over a thousand entries: coming back to one just used meant
searching for it again. The strip publishes `self._catalog_recent_hitboxes`,
which the click handler treats exactly like a row of the list.

Constants: `CATALOG_ROW_*`, `CATALOG_THUMB_*`, `RECENT_*` in
`editor/constants.py`.

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
| Music playlist | `_music_geometry()` returns every rect, plus `row_h`, `visible_rows` and `max_scroll_px`; `_seek_bar_rect()` places the seek bar of a row |
| Translation editor (table) | `_lang_geometry()` returns every rect, plus `row_h`, `key_col`, `visible_rows` and `max_scroll`; `_lang_cell_rect()` places one cell |

Spacing follows from the same rule. A content area is measured from the chrome
around it, never from a constant: the playlist reserved `dy+130` at the top and
110 px at the bottom whatever the dialog was, so a clamped one kept a hundred
empty pixels under its list.

A dialog is also never larger than the window: `dialog_rect()` in
`editor/ui/draw.py` centres it and clamps it. The playlist and the video picker
asked for 1100x800 while the editor's own minimum window is 1280x720, so their
title bar and their footer buttons were off screen and unreachable.

What that replaced, in each of them, was the same defect: the renderer walked
the layout while the handler restated it as literals, and the two had already
drifted - the tag picker hit-tested its close button 4 px above where it was
drawn, the icon picker clamped its scroll with a hand-picked "3 rows are
probably visible", and the playlist put the seek hitbox 10 px left and above
the bar the user could see.

Dialog sizes follow the UI scale and are clamped to the window: the auditor also
stays between the top bar and the status bar, so its footer cannot end up
underneath the latter.

### Asset studio

`_img_editor_metrics(ex, ey, ew, eh)` is the single source of the studio
geometry, and `_img_editor_col1_rects` / `col2` / `col3` and
`_img_editor_footer_rects` are built from it. Renderer, click handler and drag
handler all call it. Three things it settles:

- a column is as wide as the widest label it must hold, so the German
  "HINTERGRUND ENTFERNEN" is what sets the width in German;
- the scale is `_img_editor_scale()`, the UI scale reduced until the content
  fits the modal, floored at `STUDIO_SCALE_MIN`;
- the sidebar gives width back before the canvas does: it never leaves the
  image less than `WORK_MIN_W`.

`_img_editor_icon_button()` draws the buttons that carry a PNG icon. The label
comes first: on a narrow button a translated word takes the room the icon would
have used, and the decision is taken for the whole row by
`_img_editor_icons_fit()`, so one button of a pair does not drop its icon while
its neighbour keeps one. The labels used to be centred strings padded with
leading spaces ("      AUTO TRIM"), which cannot be translated at all.

`pytest tests/test_editor_asset_studio.py` checks, in five languages at three
scales on three window sizes, that no two controls overlap, that all of them
stay inside the modal, and that the canvas keeps its minimum width.

### Translation editor

The table is the densest surface of the editor and the one whose job is finding
what is missing, so it carries a little more than geometry:

- each language column shows how much of the project it covers (`EN 97%`),
  coloured by how far along it is;
- a cell with no translation is drawn tinted and outlined, so an empty one
  cannot be mistaken for a short one;
- **Only incomplete** lists just the keys some language has nothing for, and
  combines with the search;
- a key created with **+ New key** is named on the spot instead of being left
  as `new_key_12` — the name is what the game refers to, so a key nobody can
  name is a key nobody can use. Only a key created in this session can be
  renamed: renaming an existing one would break whatever refers to it.

#### Machine translation

`editor/tools/translator.py` decides *what* to translate and a backend does the
translating; `editor/tools/translator_backends.py` finds the backends. The
split is what makes it testable without a model, and what lets the editor
prefer an engine the machine already has:

1. a **local service already running** - Ollama on 11434, LibreTranslate on
   5000, probed with a 0.4 s timeout so discovery cannot be what makes the
   dialog slow. Only the standard library is used, so a machine that has one
   needs no new dependency;
2. **Argos Translate**, a pip package with downloadable offline language
   packages, which the panel offers to fetch;
3. nothing, which the panel reports with the command to install one.

Nothing runs before a plan is shown: how many cells, from which language into
which, and whether a package must be downloaded. Only empty cells are ever
filled. The batch runs in a worker thread with progress and cancel, and its
results are applied in the render loop.

The safety that makes it usable at all: a UI string carries placeholders like
`{n}`, and a model that rewords one breaks `str.format` the first time the game
shows that string. The prompt tells the model to keep them, and
`keeps_placeholders()` refuses any result whose placeholders differ from the
source rather than writing it.

`editor/mixins/lang_translate.py` is the UI, reachable from the panel's
**Translate...** button and from the command palette.

Its layout used to be written three times (the wheel handler, the renderer, the
click handler) and the copies disagreed: the search box was drawn three pixels
below where it was hit-tested, and the rows were clipped two pixels away from
where clicks stopped being accepted. Verified by
`pytest tests/test_editor_lang_modal.py`.

## Localization

No literal user-visible text in the editor code. Tooltips are `tip_*` keys read
through `self._TR(...)`, like every other string (see
[../engine/I18N.md](../engine/I18N.md)). Every new key goes into all five files
under `engine/assets/strings/`, and `pytest tests/test_editor_i18n.py` enforces
it.

The project auditor reports through the same mechanism: every issue it raises
is a `aud_i_*` key with an English default, so the report follows the editor
language instead of always coming out in Italian.

### What the language files may contain

`pytest tests/test_string_encoding.py` refuses four things, each of which had
already happened:

- an accent spelled as an apostrophe. A folding pass turned the accented
  letters into ASCII and left an apostrophe behind, in 266 French strings, 27
  Italian and 19 Spanish: the French editor said "E'diter", "SCE'NE" and
  "PROJETS RE'CENTS", and a few came out worse than that ("Macinacaffa'\xa8"
  for "Macinacaffe" with a grave accent);
- a string read as cp1252 and written back as UTF-8, which is how "Coeur
  Humain" with the oe ligature became "C" followed by two mojibake characters;
- a decomposed string, which draws as the base letter with the accent floating
  next to it rather than on it;
- a key with an accent or an apostrophe in it: nothing can look it up, because
  every tag id is an ASCII slug from `slugify_tag()`.

Two completeness checks sit next to them. Every `label_key` a catalog points at
must exist in **English**, because English is the only fallback and a missing
English name has nothing behind it: 61 objects were named in Italian and
nowhere else, and 16 in no language at all, so the editor showed the raw key.
And every chrome key must exist in all five languages: an object name that
falls back to English still reads, a button that does not is a bug.

`pytest tests/test_source_hygiene.py` is the other half of that: it refuses a
sentence handed straight to `_draw_text`, `_draw_text_wrapped` or `_button` as
a literal. That is how the asset studio ended up drawing eight English buttons
under translated headings, the preset modal stayed Italian in all five
languages, and the game selector answered "ERRORE: Scena non trovata!" to a
French user.

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

### No emoji

`CLAUDE.md` says never emoji, and the font stack agrees: the platform dropdown
shipped with a laptop and a phone emoji, which the UI font has no glyph for, so
it drew an empty box next to "DESKTOP". The build systems used tick and cross
marks in their log lines for the same reason. `pytest
tests/test_editor_modal_geometry.py` walks `engine/`, `editor/` and `tools/`
and refuses a codepoint from the emoji planes; the dingbats used as icon keys
(the close button, the dropdown arrows) are not emoji and stay.

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
