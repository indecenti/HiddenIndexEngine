# Menu UI/UX plan

Status: proposed (2026-09-25). Scope: every menu page of the game runtime, for all six
themes (`default`, `horror`, `kids`, `cyber_neon`, `mystery`, `android_std`), in Python
(`engine/menu_system.py`, `engine/menu_skins/`, `engine/results_screen.py`) and in the web
runtime (`editor/web_template/runtime/skins/*.js`, see `docs/web/WEB_EXPORT_SYNC.md`).

The previous passes (chrome, detail, colours - see `MENU_SKINS.md`) fixed structure and
contrast of the colours themselves. This one is about what a player can actually read and
use, on the screens the game ships to: a 20:9 phone first, a desktop monitor second.

## How the audit was done

`tools/menu_audit.py` boots the real `EngineCore` for a game and walks every page
(main, confirm dialog, levels, scenes of every level with the carousel at start and end,
settings at top and scrolled, pause, results win and fail) for every theme and size,
writing one PNG per page and a contact sheet per theme:

```powershell
python tools/menu_audit.py --game Malonno_Survivors --out scratch/menu_audit
python tools/menu_audit.py --themes mystery --sizes 2400x1080 --lang de
```

Audited: Malonno_Survivors, 6 themes x {1280x720, 2400x1080, 1024x768, 2560x1440}, EN.

## Findings

Sizes are in reference pixels (the 1280x720 layout space; the ScalingManager multiplies
them by `min(w/1280, h/720)`). On a 6.5" 2400x1080 phone one reference pixel is about
0.1 mm, so a 12 px caption is 1.2 mm tall - unreadable at arm's length.

### A. Broken behaviour

| # | Page | Finding |
|---|------|---------|
| A1 | Results | Raw keys on screen: `MISSION_COMPLETE`, `TOTAL_SCORE`, `PERFECT_SCORE`, `TIME_ELAPSED`, `OBJECTS_FOUND`. `results_screen.py` asks for upper-case keys that exist in no language file (only `mission_complete` exists, in the game strings). |
| A2 | Main | With a save, `default` and every game that inherits its `views.main` (Malonno, whose theme is `mystery`) show only PLAY and SETTINGS: no New Game, no Continue. The view has no `requires_save` buttons, and a declared view replaces the built-in has-save logic entirely. The player cannot restart. |
| A3 | Settings | Scrolled, the rows slide under the state title and the group headers (AUDIO, GENERAL) draw on top of the rows. There is no clipped viewport below the header. |
| A4 | Results | The stats rows overlap the CONTINUE button (`OBJECTS_FOUND 12/12` is half under it). |
| A5 | All, non-16:9 | A video menu background is scaled to the fixed 1280x720 reference: black bars on 20:9 (phones) and 4:3. The still-image path already does cover-fill; the video path does not. |
| A6 | All | The Malonno menu video carries a visible `Veo` watermark bottom right on every page. Asset issue, not code: re-export or crop. |

### B. Legibility

| # | Page | Finding |
|---|------|---------|
| B1 | Levels, Scenes | Card captions render at about 11-12 px: `get_auto_font` shrinks the name to fit and there is no floor. They also use a system bold sans, not the theme's typography. |
| B2 | Settings | Group headers are 17 px letter-spaced caps in the accent colour straight on the photo: in `mystery`, `cyber_neon` and `android_std` they disappear. |
| B3 | Dialog | Button labels are about 13 px; the primary button in `default` and `android_std` is a stock blue unrelated to the theme. |
| B4 | Main, footer | Version line (17 px, alpha 130) and icon captions on busy photo areas (the road in `default`, the corridor in `mystery`) have no local plate. |
| B5 | Scenes | Breadcrumb subtitle (level name under the title) is thin letter-spaced text on the photo, often below 3:1. |
| B6 | Results | Georgia / Arial hard-coded, 20 px italic labels at 30% alpha, panel about 260 px wide at 720p and just 15% of the width at 1440p. `PERFECT_SCORE` is dark green on near-black. |

### C. Layout and spacing

| # | Page | Finding |
|---|------|---------|
| C1 | Main | The Quit button floats alone in the bottom-right corner; the row of actions sits on the busiest part of the background; the gap between title and actions changes per theme. |
| C2 | Levels | A game with one level shows one very wide card off the vertical centre, with a large empty page. No level progress (scenes done, stars). |
| C3 | Scenes | Cards are cut at both edges; the focused card is taller so the row is ragged; locked cards give no hint of how to unlock; no stars or best score per scene. |
| C4 | Pause | Three icons in a large empty dark page: no scene name, no progress (found / total), no hint count. |
| C5 | Settings | The panel is centred at desktop width, but at 20:9 it leaves two large empty bands; value pills are tiny; the slider thumb is a small target. |
| C6 | All | Back button about 36 px: below the 48 dp minimum touch target on Android. |
| C7 | Results | No themed look at all (not a skin page), no background, large empty band in the middle of the card, no "next scene" / "retry" / "menu" choice - only Continue. |
| C8 | Dialog | The destructive action (erase progress) is styled as the primary action. |

## Principles (the rules the fixes must respect)

1. **Type scale in the core, fonts in the theme.** One scale for every page, in reference
   pixels, with hard floors. Themes pick the font per role and may tweak the scale by a
   factor, never go below the floor.

   | Role | Size | Use |
   |------|------|-----|
   | display | 78 | game wordmark on main |
   | title | 44 | state title |
   | heading | 30 | dialog / results headline, card name on the focused card |
   | body | 24 | row labels, dialog text, button labels |
   | caption | 20 | icon captions, card names, stats labels |
   | micro | 17 | version, breadcrumb, group headers - never for anything the player must read to act |

   Floor for anything actionable: 20. Floor for any text at all: 17. Android multiplies the
   whole scale by a mobile factor (proposed 1.15) because the reference pixel is physically
   smaller on phones.
2. **Text never sits on the raw photo.** Every text run gets either a surface (row, card,
   plate) or the header scrim. Contrast is measured against the pixels actually behind it,
   not against the theme colour.
3. **The layout fills the screen, not the 16:9 box.** Backgrounds cover-fill at any aspect;
   carousels and settings use the full safe width; content columns are centred with a max
   width.
4. **48 dp touch targets** for every interactive element on Android (back, pills, slider
   thumb), with the hit box larger than the drawing when the look wants it small.
5. **Every page answers "where am I, what can I do, what is next"**: title + context line,
   one primary action, progress where progress exists.
6. **Identity lives in the skin, legibility in the core.** Skins keep their typography,
   decoration, motion and background; they do not own sizes, floors, plates or spacing.

## Plan

Each phase ends with the audit re-run on all themes and sizes, the tests green, and a
before/after contact sheet.

### Phase 0 - Tooling (this change)
- `tools/menu_audit.py` (done).
- `tests/test_menu_legibility.py`: headless checks per theme x size - rendered text height
  of every text run >= floor, contrast of each run against the pixels behind it >= 4.5:1
  (body) / 3:1 (large), no two text boxes overlapping, every interactive rect >= 48 dp on
  the Android profile. The core records each text run it draws (rect + role) in a
  debug list so the test does not need OCR.

### Phase 1 - Broken behaviour (A1-A5) - DONE (Python), 2026-09-26

Done: results keys in 5 languages and the panel following the menu scale with the stats
above the button; `views.main` save-aware in `default` (every game inherits it through
`load_theme_for_game`); settings list clipped under the header, hidden rows not
clickable; video background cover-filled and darkened with the same scrim as the still
image (it had none); letterbox offset restored on titles, rule, breadcrumb, icon
captions and settings group headers (`MenuSystem.ref_y_to_screen`, used by the skins
too) - on 4:3 the captions were drawn inside the icons. Regressions in
`tests/test_menu_ux.py`. The web runtime already used the right keys and has no
save-aware main menu, so nothing to port for this phase.

Original scope:
- Results: real keys (`results_mission_complete`, `results_mission_failed`,
  `results_total_score`, `results_perfect`, `results_time`, `results_objects`,
  `btn_continue`) in all 5 languages; stats laid out above the button.
- `views.main`: add `requires_save` variants (Continue + New Game with save, Play
  without) to `default` and to the game copies that inherit it.
- Settings: clipped scroll viewport under the header; group headers scroll with their rows.
- Video background: cover-fill like the still image.
- Web: same keys and the same main-view rule in `skins/base.js`; `test_web_sync.py`.

### Status 2026-09-26 (end of session)

Done on top of phase 1:
- Layout probe in the core (`MenuSystem.layout_probe` / `probe()`, also called by the
  skins' titles and the default chip) and the rules in `tools/menu_layout_check.py`
  (cut, icon out of its button, text over text / over controls, controls over each
  other, text below the floor). `tools/menu_audit.py --check` writes
  `layout_report.txt`; `tests/test_menu_layout.py` holds main, pause, dialog and
  settings clean on all six themes at 1280x720 and 1024x768.
- Real type sizes: themes without a font file used pygame's `Font(None)`, which draws
  at 0.6875 of the size asked (a "24" was 16 px). `menu_theme._default_font` loads the
  same face by path. `get_auto_font` never goes below `MIN_READABLE_REF` (18) and
  `fit_text` ellipsizes what still does not fit (card names, value pills).
- Icon rows (main, pause): slots sized on the wider of plate and caption
  (`_space_icon_row`), no carousel zoom on them (`CAROUSEL_STATES`). A theme with a
  declared `views` entry no longer skips spacing, `arrange()` and the scroll range.
- Campaign groundwork: `engine/campaign.py` (order, unlocks, resume target, next step,
  what a lost scene records; `tests/test_campaign.py`). `level_manager` uses its scene
  order and wires `timer_behavior: "fail"`; the web honours the same mode and no longer
  unlocks the next scene on a time-out (WEB_EXPORT_SYNC.md section L).
- Audit at 1280x720, all themes: 81 violations -> only the scene carousel is left.

Pass 2026-09-26 (margins, sizes, padding per theme):
- Levels and scenes are pages of whole cards (`_layout_cards`): a grid of up to two
  rows between two 64 px arrows, one page per screen width (on 20:9 the neighbour
  pages no longer peek into the side bands), page dots, wheel and arrow clicks turn
  pages. The free carousel, its zoom and its edge fade are gone. Card area starts
  under the real header (`_content_top`); `_grid_fit` shrinks cards down to 0.65 when
  that buys a second row (cyber_neon 4 per page instead of 2, android_std 4 instead
  of 1). Previews are cover-cropped, never stretched; a missing preview is a themed
  plate. One caption size per page (`_uniform_captions`). Cards carry stars (best),
  level progress and stars, and "Complete <scene>" on locked ones, all from `Campaign`;
  the scene list now checks that the level is unlocked.
- Dialog: both buttons as wide as the longer label, card grows with them; destructive
  action in a danger fill, Cancel neutral; message at body size.
- Settings: the back button is chrome again (it was drawn as a list row, no plate).
- Results: panel as tall as its content, theme fonts and colours, gold stars where the
  accent does not read, scene name under the title, VHS noise removed.
- Strings: Malonno de/es/fr carried Italian UI strings and an old "Mission Complete"
  placeholder; fixed, and `_audit_translations` now re-aligns such values with the
  engine on every save (`tests/test_harvest_system_strings.py`). Engine: "löscht",
  "Paramètres", two object names.
- Audit: 0 violations on six themes x 1280x720 / 2400x1080 / 1024x768, EN and DE.

Still open in the game data (content, not layout): about 95 object names per language
in Malonno are the Italian text, and the level name has no translation.

Next, in this order:
1. (done: paged cards)
2. Core on `Campaign`: Continue resumes `resume_target()` instead of opening the level
   list, results Next / Retry / Menu, no double `_switch_to_menu` at the end of a
   level, dead `_results_timer` and `_resume_from_save` removed, level order from
   `game_config` in the menu and in the web export.
3. Results as a themed page (theme fonts and colours, no VHS noise).
4. Editor: menu theme picker with a live preview of the real MenuSystem, and the same
   layout rules on the editor's own panels.

### Phase 2 - Type scale and plates (B1-B6, principle 1-2)
- `MenuTheme.type_size(role)` + `TYPE_SCALE` / `TYPE_FLOOR` in the core; every
  `get_font*` call in `menu_system.py` goes through a role. `get_auto_font` never shrinks
  below the role floor: it wraps to two lines, then ellipsizes.
- Card captions in the theme's body font, 20+ px, on a caption band of fixed height.
- Local plates (theme `row_bg`, rounded) behind icon captions, group headers, breadcrumb,
  footer. Adaptive: the plate alpha rises with the luminance variance of the pixels under it.
- Dialog buttons at body size; primary colour from `theme.accent()`; destructive action
  styled as danger, Cancel as primary.

### Phase 3 - Page layouts (C1-C8)
- Main: actions grouped with Quit as the last, smaller item of the same row (desktop) or
  in the corner with a real 48 dp target (Android); fixed rhythm title -> actions.
- Levels: 1-3 levels as a centred grid of large cards, more as the carousel; each card
  shows scenes done / total and stars.
- Scenes: uniform card size (focus by outline and lift, not height), carousel padded so the
  first and last card can reach the centre, stars / best score on done scenes, "Complete
  <previous scene> to unlock" on locked ones.
- Pause: context panel (scene name, found / total, hints left, time) + the three actions.
- Settings: panel width follows the screen (max 880 reference px), 48 dp pills and thumb.
- Results: a real skin page - themed background, title font, stars animation kept,
  stats as rows, actions Next / Retry / Menu (Retry and Menu new), no empty band.

### Phase 4 - Per-theme polish
Walk each theme's sheets and fix what is specific to it (horror red on black small text,
cyber_neon pink headers, kids light plates on sky, mystery sepia on sepia, android_std
system font sizes). Skins get a `results` hook for their own decoration.

### Phase 5 - Web parity
Port phases 1-4 to the DOM/CSS skins: same type scale as CSS custom properties generated
from `editor/web_rules.py::engine_rules()`, same page content and actions, same i18n keys.
Layout may differ where the DOM does better; content and rules may not.

### Phase 6 - Verification
Audit on 6 themes x 4 sizes x 5 languages (DE for length), Android emulator pass on the
APK, web export in the browser at 375 px and desktop. Legibility tests part of `pytest`.

## Decisions (2026-09-25)

- Mobile factor for the type scale: **1.15** on Android, 48 dp targets; desktop unchanged.
- Results actions: **Next / Retry / Menu**.
- Web parity: **in the same change as each phase** (phase 5 becomes a final parity sweep).
