"""
editor/constants.py

Costanti globali dell'editor: dimensioni, modalità, colori, layer.
Importato da tutti i moduli dell'editor.
"""

# ─────────────────────────────────────────────────────────────────────────────
# LOCALIZZAZIONE — unica fonte di verità per le lingue supportate
# ─────────────────────────────────────────────────────────────────────────────

LANGS: tuple[str, ...] = ("it", "en", "es", "fr", "de")

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
AUTOSAVE_SECS  = 60
UNDO_MAX       = 50
HANDLE_R       = 4

# ─────────────────────────────────────────────────────────────────────────────
# GRIGLIA / SNAP / NUDGE
# ─────────────────────────────────────────────────────────────────────────────

GRID_SIZES         = (8, 16, 32, 64, 128)   # dimensioni cicliche (Shift+G)
DEFAULT_GRID_SIZE  = 32
ZOOM_MIN           = 0.04
ZOOM_MAX           = 10.0
ZOOM_SEL_MARGIN    = 0.8   # margine attorno alla selezione in zoom-to-selection
NUDGE_STEP         = 1     # spostamento frecce in px scena
NUDGE_STEP_FAST    = 10    # spostamento frecce con Shift
NUDGE_UNDO_GAP_S   = 1.0   # pause > soglia = nuovo snapshot undo (coalescing)
OBJ_SNAP_PX        = 8     # soglia snap a oggetti in pixel schermo

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


# ─────────────────────────────────────────────────────────────────────────────
# TIPS AIUTO (Tooltip)
# ─────────────────────────────────────────────────────────────────────────────

UI_TIPS = {
    # Toolbar
    "mode_select": "Strumento Selezione (S): Seleziona, sposta e ridimensiona oggetti nel canvas.",
    "mode_circle": "Strumento Cerchio (1): Clicca e trascina per creare un'area di hit circolare.",
    "mode_rect": "Strumento Rettangolo (2): Clicca e trascina per creare un'area di hit rettangolare.",
    "mode_effect_place": "Strumento Effetti (3): Posiziona effetti visivi come bagliori o fumetti (Bubble Tips).",
    "mode_scatter": "Strumento Cluster (4): Piazza un gruppo di oggetti casuali. Usa Shift+Click per densità massima.",
    "toggle_overlay": "Mostra/Nascondi Overlay (O): Visualizza le aree di hit colorate sopra il background.",
    "toggle_grid": "Griglia (G): Attiva la griglia e lo snap. Shift+G cambia dimensione, Ctrl+G snap a oggetti.",
    "toggle_icons": "Icone (I): Mostra o nasconde le icone PNG degli oggetti nel canvas.",
    
    # Status Bar
    "btn_save": "Salva Scena (Ctrl+S): Scrive le modifiche nel file scene.json del livello.",
    "btn_play_scene": "Playtest: prova subito questa scena in gioco (salva prima le modifiche).",
    "btn_back": "Torna al Selettore: Esci dall'editor e torna alla schermata di selezione gioco/livello.",
    
    # Tabs
    "tab_tree": "Gerarchia: Elenco di tutti gli oggetti presenti nella scena divisi per layer.",
    "tab_layers": "Gestione Livelli: Organizza gli oggetti in profondità. I livelli superiori coprono quelli inferiori.",
    "layer_visible": "Visibilità (Occhio): Clicca per nascondere o mostrare tutti gli oggetti di questo livello.",
    "layer_locked": "Blocco (Lucchetto): Blocca il livello per evitare di selezionare o spostare oggetti per errore.",
    "layer_active": "Livello Attivo (Freccia): Determina in quale livello verranno creati i nuovi oggetti.",
    "tab_catalog": "Catalogo: Trascina o clicca gli oggetti del gioco per aggiungerli alla scena.",
    "tab_effects": "Effetti: Catalogo degli effetti visivi disponibili per la scena.",
    "tab_props": "Proprietà: Modifica i parametri tecnici dell'oggetto o dell'effetto selezionato.",

    # Proprietà Oggetti
    "prop_id": "ID Istanza: Nome unico dell'oggetto in questa scena.",
    "prop_layer": "Layer corrente: Determina lo Z-index (chi sta sopra chi).",
    "prop_rotation": "Rotazione: Ruota l'oggetto attorno al suo centro (R per ruotare di 90°).",
    "prop_alpha": "Opacità: Trasparenza dell'icona (0=invisibile, 255=pieno).",
    "prop_goal": "Oggetto Obiettivo: Se attivo, il giocatore deve trovare questo oggetto per vincere.",
    "prop_hint": "Ritardo Hint: Secondi prima che il gioco suggerisca questo oggetto automaticamente.",
    "prop_always": "Sempre Visibile: Se attivo, l'oggetto è visibile anche prima di essere trovato.",
    "prop_warp": "Warp: Trascina gli angoli tenendo premuto Shift per distorsione prospettica.",

    # Proprietà Effetti
    "fx_text": "Chiave Traduzione: Il testo (ID) del fumetto che verrà caricato da it.json.",
    "fx_trigger": "Trigger: Quando deve apparire l'effetto (es: start_scene, on_found).",
    "fx_intensity": "Intensità: Forza o luminosità dell'effetto visivo.",
}
