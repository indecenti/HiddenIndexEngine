"""
editor/constants.py

Costanti globali dell'editor: dimensioni, modalità, colori, layer.
Importato da tutti i moduli dell'editor.
"""

# ─────────────────────────────────────────────────────────────────────────────
# LOCALIZZAZIONE — unica fonte di verità per le lingue supportate
# ─────────────────────────────────────────────────────────────────────────────

LANGS: tuple[str, ...] = ("en", "it", "es", "fr", "de")

# Lingua di default dell'editor e fallback unico (vedi
# engine.language_manager.DEFAULT_LANG / FALLBACK_LANG).
DEFAULT_LANG: str = "en"

# ─────────────────────────────────────────────────────────────────────────────
# VERSIONE / DIMENSIONI
# ─────────────────────────────────────────────────────────────────────────────

VERSION        = "1.0-base"
REF_W, REF_H   = 1280, 720
WIN_W, WIN_H   = 1280, 720
MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT = 1280, 720
TOP_BAR_H      = 30
MENU_W         = 180      # Larghezza standard dropdown menu
PANEL_MIN_W    = 150
PANEL_MAX_W    = 600
STATUS_H       = 40
# Minimum width of a status bar action button; longer labels grow the button
# instead of being clipped (see editor.ui.draw._button_w).
STATUS_BTN_MIN_W = 110
# Gap between two status bar buttons.
STATUS_BTN_GAP = 10
AUTOSAVE_SECS  = 60
# Main loop: consecutive frames that may crash before giving up. A single bad
# frame (a modal with stale state, a missing asset) must not throw away the
# unsaved scene; a loop that crashes every frame must not spin forever.
MAIN_LOOP_MAX_CRASHES = 5
# Minimum gap between two emergency saves: a crash/clean alternation must not
# rewrite the scene on every other frame.
CRASH_SAVE_MIN_GAP_S = 1.0
# Back-off after a failed autosave (locked file, full disk): without it the
# retry would run on every frame of the main loop.
AUTOSAVE_RETRY_SECS = 15
UNDO_MAX       = 50
HANDLE_R       = 4
# Scene outline: row height and the window a second click still counts as a
# double click (same feel as the dashboard).
OUTLINE_ROW_H  = 26
DOUBLE_CLICK_S = 0.4
# Cache immagini scalate dell'editor: cap LRU (evict graduale del piu' vecchio)
IMG_CACHE_MAX  = 512
# Backup rotativi di scene.json a ogni salvataggio (in .editor_backups/)
SCENE_BACKUPS_KEEP = 5
# Veil drawn over a recent-project thumbnail while the card is hovered, so the
# "open scene" call to action is readable whatever the background shows.
RECENT_CARD_SCRIM = (0, 0, 0, 150)

# Rendered text surfaces kept by editor/ui/draw.py (LRU, evicted oldest first).
# The UI redraws in immediate mode, so the same labels are rendered every frame.
TEXT_CACHE_MAX = 2048
# Filtered catalog views kept by the catalog panel (LRU). One entry per
# combination of style filter, active tags, search query and language.
CATALOG_VIEW_CACHE_MAX = 12
# Forced redraw while the editor is idle. Bounds how long a state change made
# by a worker thread can stay invisible on screen.
IDLE_HEARTBEAT_S = 0.4

# ─────────────────────────────────────────────────────────────────────────────
# GRIGLIA / SNAP / NUDGE
# ─────────────────────────────────────────────────────────────────────────────

GRID_SIZES         = (8, 16, 32, 64, 128)   # dimensioni cicliche (Shift+G)
DEFAULT_GRID_SIZE  = 32
ZOOM_MIN           = 0.04
ZOOM_MAX           = 10.0
ZOOM_SEL_MARGIN    = 0.8   # margine attorno alla selezione in zoom-to-selection

# ─────────────────────────────────────────────────────────────────────────────
# SCALA UI (font e icone della chrome editor)
# ─────────────────────────────────────────────────────────────────────────────

UI_SCALE_DEFAULT   = 1.0
UI_SCALE_MIN       = 0.75
UI_SCALE_MAX       = 1.5
UI_SCALE_STEP      = 0.1   # incremento con Ctrl+Piu'/Meno
NUDGE_STEP         = 1     # spostamento frecce in px scena
NUDGE_STEP_FAST    = 10    # spostamento frecce con Shift
NUDGE_UNDO_GAP_S   = 1.0   # pause > soglia = nuovo snapshot undo (coalescing)
UNDO_COALESCE_GAP_S = 1.0  # finestra coalescing snapshot con stessa coalesce_key
OBJ_SNAP_PX        = 8     # soglia snap a oggetti in pixel schermo

# ─────────────────────────────────────────────────────────────────────────────
# LISTA CATALOGO (pannello sinistro)
# ─────────────────────────────────────────────────────────────────────────────

# A catalog row shows three stacked lines (id, localized label, tags) next to a
# thumbnail. Its height used to be the constant 74 whatever the UI scale was,
# so above 1.0 the three lines ran into each other and into the next row.
# The height is derived from the rendered line heights instead; these are the
# paddings that go around them.
CATALOG_ROW_PAD      = 9    # padding above the first line and below the last
CATALOG_ROW_LINE_GAP = 3    # gap between two lines of the same row
CATALOG_ROW_GAP      = 4    # gap between two rows
CATALOG_THUMB_BASE   = 48   # thumbnail side at UI scale 1.0
CATALOG_THUMB_GAP    = 16   # gap between the thumbnail and the text column

# Objects placed recently, offered as a strip above the catalog list. Placing
# is the repetitive action of the editor and the catalog holds over a thousand
# entries: coming back to one just used meant searching for it again.
RECENT_OBJECTS_MAX   = 10   # how many are remembered, per project
RECENT_STRIP_BASE    = 40   # thumbnail side at UI scale 1.0
RECENT_STRIP_GAP     = 6

# ─────────────────────────────────────────────────────────────────────────────
# TOOLBAR CANVAS / HUD
# ─────────────────────────────────────────────────────────────────────────────

# Toolbar button geometry. The widths follow the rendered label instead of a
# per-button constant: a longer translation or a UI scale above 1.0 used to
# clip the text and push the row past the right edge of the canvas.
TOOLBAR_BTN_PAD_X   = 14   # horizontal padding around a toolbar label
TOOLBAR_BTN_PAD_Y   = 5    # vertical padding, so the height follows the font
TOOLBAR_BTN_MIN_W   = 52
TOOLBAR_GAP         = 6    # gap between two buttons of the same group
TOOLBAR_GROUP_GAP   = 18   # gap between the tool group and the toggle group
TOOLBAR_MARGIN      = 8    # margin from the canvas edges
TOOLBAR_ROW_GAP     = 4    # vertical gap between two wrapped toolbar rows

# Canvas HUD (zoom level and cursor coordinates): a pill anchored to the
# bottom right of the canvas, clear of the toolbar row at the top.
HUD_PAD_X     = 10
HUD_PAD_Y     = 6
HUD_MARGIN    = 10
HUD_LINE_GAP  = 2
HUD_BTN_PAD   = 10   # padding that turns a label into a HUD button
HUD_GAP       = 4    # gap between two HUD controls
HUD_BG        = (18, 18, 24, 200)

# ─────────────────────────────────────────────────────────────────────────────
# OVERLAY SCORCIATOIE (F1)
# ─────────────────────────────────────────────────────────────────────────────

SHORTCUTS_PANEL_W   = 760
SHORTCUTS_ROW_H     = 24
SHORTCUTS_PAD       = 22
SHORTCUTS_KEY_COL_W = 92    # width of the key chip column
SHORTCUTS_COL_GAP   = 12    # gap between the chip and its label
SHORTCUTS_SCRIM     = (10, 10, 15, 170)

# ─────────────────────────────────────────────────────────────────────────────
# COMMAND PALETTE (Ctrl+P)
# ─────────────────────────────────────────────────────────────────────────────

PALETTE_W        = 620
PALETTE_MAX_ROWS = 12
PALETTE_PAD      = 14
PALETTE_TOP      = 120      # distance from the top of the window
PALETTE_SCRIM    = (10, 10, 15, 150)

# ─────────────────────────────────────────────────────────────────────────────
# TRADUZIONE AUTOMATICA (pannello di conferma / avanzamento)
# ─────────────────────────────────────────────────────────────────────────────

TR_PANEL_W = 620
TR_PAD     = 20
TR_SCRIM   = (8, 8, 12, 190)

SND_CLICK      = "engine/assets/sounds/click_Low.wav"
CACHE_OBJ_MAX  = 400
CACHE_FILTER_MAX = 100


# ─────────────────────────────────────────────────────────────────────────────
# MODALITÀ TOOL
# ─────────────────────────────────────────────────────────────────────────────

MODE_SELECT       = "select"
MODE_CIRCLE       = "circle"
MODE_RECT         = "rect"
MODE_EFFECT_PLACE = "effect_place"
MODE_SCATTER      = "scatter"
MODE_SURFACES     = "surfaces"   # placement surfaces of tools/place_on_surfaces.py

# ─────────────────────────────────────────────────────────────────────────────
# PLACEMENT SURFACES (surfaces mode + "Place on surfaces")
# ─────────────────────────────────────────────────────────────────────────────

SURF_LINE_C      = (255, 0, 255)     # resting lines (same colours as the tool preview)
SURF_AREA_C      = (0, 255, 120)     # areas seen from above
SURF_GIZMO_C     = (0, 255, 255)     # size tick: height of a 20 cm object
SURF_HUD_C       = (230, 60, 60, 70) # forbidden band under the game HUD
SURF_MARGIN_C    = (230, 60, 60, 45) # frame margin kept empty
SURF_SUPPORT_C   = (0, 255, 120, 80) # support map overlay
SURF_LINE_W      = 2
SURF_SEL_LINE_W  = 3
SURF_GIZMO_W     = 2
SURF_HIT_PX      = 7                 # pick distance on screen
SURF_NUDGE_FAST  = 10
SURF_H_STEP      = 1
SURF_H_STEP_FAST = 10
SURF_HMUL_STEP   = 0.05
SURF_LABEL_PAD   = 3
SURF_HUD_LABEL_C = (255, 170, 170)
SURF_HANDLE_RIM_C = (0, 0, 0)
PLACE_DIALOG_W   = 620
PLACE_DIALOG_H   = 640
PLACE_ROW_GAP    = 8
PLACE_PAD        = 16
PLACE_SCRIM      = (0, 0, 0, 150)
PLACE_APPLY_BG   = (30, 90, 45)      # the button that writes into the scene
PLACE_FIELD_BG   = (30, 32, 38)
PLACE_PROGRESS_BG = (25, 40, 55)
PLACE_PROGRESS_FILL = (35, 90, 130)
PLACE_ROW_PAD_Y  = 12                # dialog row = line height + this
PLACE_LINE_GAP   = 4
PLACE_NUM_PAD    = 24                # number box = widest seed + this
PLACE_NUM_MIN_W  = 90
PLACE_TAG_MIN_W  = 60
PLACE_RUN_MIN_W  = 110
PLACE_TEXT_INSET = 8
PLACE_BAR_MIN    = 6                 # smallest visible progress fill
PLACE_STEP_FAST  = 10                # +/- with Shift in the dialog
PLACE_GHOST_ALPHA = 235
PLACE_ROLE_C     = {"clue": (255, 200, 60), "collectible": (255, 120, 200),
                    "minigame": (210, 65, 65), "pool": (80, 200, 255)}
PLACE_SEED_MAX   = 999999
PLACE_COUNT_MAX  = 300
PLACE_ALT_MAX    = 4
AUDIT_MARGIN     = 40
AUDIT_SCROLL_STEP = 80

# ─────────────────────────────────────────────────────────────────────────────
# STATI APPLICAZIONE
# ─────────────────────────────────────────────────────────────────────────────

STATE_GAME_SELECT = "game_select"
STATE_MAIN        = "main"

# ─────────────────────────────────────────────────────────────────────────────
# TAB PANNELLI
# ─────────────────────────────────────────────────────────────────────────────

TAB_TREE    = "tree"
TAB_CATALOG = "catalog"
TAB_EFFECTS = "effects"
TAB_OUTLINE = "outline"
TAB_LAYERS  = "layers"
TAB_PROPS   = "props"

# ─────────────────────────────────────────────────────────────────────────────
# COLORI
# ─────────────────────────────────────────────────────────────────────────────

BG      = (28,  28,  34)
PANEL   = (38,  38,  46)
BORDER  = (55,  55,  68)
CANVAS  = (18,  18,  22)
STATUS  = (22,  22,  28)
TXT     = (210, 210, 222)
TXT_DIM = (160, 160, 180)
TXT_HI  = (255, 255, 255)
ACCENT  = (70,  140, 220)
BTN     = (50,  50,  62)
BTN_HO  = (68,  68,  86)
BTN_AC  = (60,  120, 200)
GRID_C  = (46,  46,  58)
SEL_C   = (255, 220,  50)
ERR_C   = (210,  65,  65)
WARN_C  = (220, 165,  50)
OK_C    = ( 75, 195,  95)
ALWAYS_C= (100, 200, 255)   # Azzurro per obiettivi fissi
FX_C    = (220, 185,  55)   # colore effetti nel canvas

# ─────────────────────────────────────────────────────────────────────────────
# LAYER
# ─────────────────────────────────────────────────────────────────────────────

LAYER_COLORS = {
    "objects_low":  (100, 150, 255),
    "objects_mid":  ( 75, 215, 115),
    "objects_high": (255, 195,  50),
    "overlay":      (155, 155, 165),
}

DEFAULT_LAYERS = [
    {"id": "objects_low",  "z": 10, "label": "Oggetti Basso",  "clickable": True},
    {"id": "objects_mid",  "z": 20, "label": "Oggetti Medio",  "clickable": True},
    {"id": "objects_high", "z": 30, "label": "Oggetti Alto",   "clickable": True},
    {"id": "overlay",      "z": 40, "label": "Overlay",       "clickable": False},
]


def layer_color(layer_id: str) -> tuple:
    return LAYER_COLORS.get(layer_id, (75, 215, 115))


def layer_z(layer_id: str) -> int:
    for lyr in DEFAULT_LAYERS:
        if lyr["id"] == layer_id:
            return lyr["z"]
    return 20
