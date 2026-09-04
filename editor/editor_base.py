"""
editor/editor_base.py

HiddenEngine Level Editor — orchestratore principale.

Struttura moduli:
  editor/constants.py         — colori, costanti, layer
  editor/ui/draw.py           — font helpers, primitive UI
  editor/core/io.py           — JSON, discovery, factory oggetti
  editor/mixins/viewport.py   — zoom, pan, coordinate transforms
  editor/mixins/history.py    — undo/redo stack
  editor/mixins/io_ops.py     — load/save gioco/scena, image cache
  editor/mixins/lang_modal.py — editor traduzioni (logic + render)
  editor/mixins/newobj_modal.py — nuovo oggetto catalogo (logic + render)
  editor/mixins/object_ops.py — handles, hit-test, CRUD, context menu
  editor/mixins/input_handlers.py — eventi keyboard/mouse/wheel
  editor/mixins/game_select.py    — dashboard selezione progetto
  editor/mixins/render_canvas.py  — canvas, grid, overlays, toolbar
  editor/mixins/render_panels.py  — pannelli tree/catalog/layers/props
  editor/mixins/render_topbar.py  — top bar, status bar

Uso:
    python -m editor.editor_base
    python -m editor.editor_base --game villa_segreta
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import pygame

# SetProcessDpiAwareness: 2 = per-monitor DPI aware (Windows 8.1+)
_DPI_PER_MONITOR_AWARE = 2


def _enable_dpi_awareness() -> None:
    """Dichiara il processo DPI-aware su Windows.

    Senza questa chiamata, con scaling display >100% l'OS stira la bitmap
    della finestra e il testo risulta sfocato.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(_DPI_PER_MONITOR_AWARE)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        logging.getLogger(__name__).debug("DPI awareness non impostata", exc_info=True)

# ── Costanti e UI primitives ─────────────────────────────────────────────────
from editor.constants import (
    VERSION, LANGS, DEFAULT_LANG,
    STATE_GAME_SELECT, STATE_MAIN,
    MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT, WIN_W, WIN_H,
    TAB_TREE, TAB_CATALOG, TAB_EFFECTS, TAB_LAYERS, TAB_PROPS,
    MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_EFFECT_PLACE,
    DEFAULT_LAYERS, DEFAULT_GRID_SIZE,
    UI_SCALE_DEFAULT, UI_SCALE_MIN, UI_SCALE_MAX, UI_SCALE_STEP,
    BG, TXT_DIM, TXT_HI, ACCENT,
    AUTOSAVE_SECS, SND_CLICK,
)
from editor.ui.draw import _init_fonts, _draw_tooltip, _rect, _draw_text, _draw_shape_icon
from editor.core.io import _discover_games
from engine.utils import setup_logging
from engine.language_manager import LanguageManager, set_active_manager
from editor.core.tags import TagManager

# ── Mixin ────────────────────────────────────────────────────────────────────
from editor.mixins.viewport       import ViewportMixin
from editor.mixins.history        import HistoryMixin
from editor.mixins.io_ops         import IoOpsMixin
from editor.mixins.lang_modal     import LangModalMixin
from editor.mixins.newobj_modal   import NewObjModalMixin
from editor.mixins.object_ops     import ObjectOpsMixin
from editor.mixins.input_handlers import InputHandlersMixin
from editor.mixins.game_select    import GameSelectMixin
from editor.mixins.render_canvas  import RenderCanvasMixin
from editor.mixins.render_panels  import RenderPanelsMixin
from editor.mixins.render_topbar  import RenderTopbarMixin
from editor.mixins.img_editor     import ImgEditorMixin
from editor.mixins.music_modal    import MusicModalMixin
from editor.mixins.minigame_modal import MinigameModalMixin
from editor.mixins.background_modal import BackgroundModalMixin
from editor.mixins.video_modal import VideoModalMixin
from editor.mixins.tag_modal import TagModalMixin
from editor.mixins.icon_modal import IconModalMixin
from editor.mixins.auditor    import AuditorMixin
from editor.mixins.scatter_modal import ScatterModalMixin
from editor.mixins.scene_stats import SceneStatsMixin
from editor.mixins.presets import PresetsMixin
from editor.mixins.batch_import import BatchImportMixin


# ─────────────────────────────────────────────────────────────────────────────
# EDITOR
# ─────────────────────────────────────────────────────────────────────────────

class LevelEditor(
    ViewportMixin,
    HistoryMixin,
    IoOpsMixin,
    LangModalMixin,
    NewObjModalMixin,
    ObjectOpsMixin,
    InputHandlersMixin,
    GameSelectMixin,
    RenderCanvasMixin,
    RenderPanelsMixin,
    RenderTopbarMixin,
    ImgEditorMixin,
    MusicModalMixin,
    MinigameModalMixin,
    BackgroundModalMixin,
    VideoModalMixin,
    TagModalMixin,
    IconModalMixin,
    AuditorMixin,
    ScatterModalMixin,
    SceneStatsMixin,
    PresetsMixin,
    BatchImportMixin,
):
    """
    Editor di livelli HiddenEngine.
    Tutti i metodi funzionali vivono nei mixin; questa classe
    gestisce lo stato condiviso e il ciclo principale.
    """

    def __init__(self, base_path: Path, initial_game: str = None):
        self.base_path = base_path
        # Impostazioni persistite, lette una volta sola all'avvio
        self._boot_settings = self._load_editor_settings()

        _enable_dpi_awareness()
        pygame.init()
        pygame.key.set_repeat(300, 50)
        pygame.display.set_caption(f"HiddenEngine Level Editor  [{VERSION}]")
        self.fullscreen = False
        
        # Inizializzazione con dimensioni di default, rispettando i minimi
        start_w = max(WIN_W, MIN_EDITOR_WIDTH)
        start_h = max(WIN_H, MIN_EDITOR_HEIGHT)
        self.screen = pygame.display.set_mode((start_w, start_h), pygame.RESIZABLE)
        
        try:
            import ctypes
            hwnd = pygame.display.get_wm_info().get('window')
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # 3 = SW_MAXIMIZE
        except Exception:
            pass
        self.screen_size = self.screen.get_size()
        self.clock = pygame.time.Clock()
        ui_scale = float(self._boot_settings.get("ui_scale", UI_SCALE_DEFAULT))
        _init_fonts(max(UI_SCALE_MIN, min(UI_SCALE_MAX, ui_scale)))

        # ── Audio ────────────────────────────────────────────────────────────
        try:
            pygame.mixer.init()
            sp = base_path / SND_CLICK
            self._snd_click = pygame.mixer.Sound(str(sp)) if sp.exists() else None
        except Exception:
            self._snd_click = None

        # ── App state ────────────────────────────────────────────────────────
        self.state   = STATE_GAME_SELECT
        self.running = True

        # ── Game data ────────────────────────────────────────────────────────
        self.game_name: str  = None
        self.game_path: Path = None
        self.catalog:   list = []
        self.levels:    list = []
        self.effects_catalog: list = []   # catalogo effetti visivi

        # ── Localizzazione e Tag ─────────────────────────────────────────────
        self.lang_manager = LanguageManager()
        self.tag_manager = TagManager(self.base_path)
        self.tag_manager.harvest_from_all_catalogs()
        
        from engine.menu_theme import ThemeManager
        self.theme_manager = ThemeManager()
        
        self.LANGS = list(LANGS)   # da constants.LANGS — unica fonte di verità
        
        # Carica lingua dalle impostazioni o usa il default EN
        settings = self._load_editor_settings()
        self.current_lang = settings.get("language", DEFAULT_LANG)

        # Fallback a EN se la lingua salvata non e' tra quelle supportate
        if self.current_lang not in self.LANGS:
            self.current_lang = DEFAULT_LANG

        self.lang_manager.load_for_game("engine", self.current_lang)
        set_active_manager(self.lang_manager)

        # ── Scene data ───────────────────────────────────────────────────────
        self.scene_path:  Path           = None
        self.scene_data:  dict           = {}
        self.scene_dirty: bool           = False
        self.bg_surf:     pygame.Surface = None

        # ── Canvas transform ─────────────────────────────────────────────────
        self.zoom:     float = 1.0
        self.origin_x: float = 0.0
        self.origin_y: float = 0.0

        # ── Pan state ────────────────────────────────────────────────────────
        self._panning       = False
        self._pan_start_mx  = 0
        self._pan_start_my  = 0
        self._pan_start_ox  = 0.0
        self._pan_start_oy  = 0.0
        self._pan_speed     = 20
        self._pan_moved     = False

        # ── Object interaction ───────────────────────────────────────────────
        self.selected_idx: int  = None
        self.selected_indices: list = []  # Supporto selezione multipla
        self._drag_active       = False
        self._drag_start_mx     = 0
        self._drag_start_my     = 0
        self._drag_start_x      = 0
        self._drag_start_y      = 0
        self._drag_group_starts = {}      # Offset iniziali per trascinamento di gruppo
        self._handle_id: str    = None
        self._handle_snap       = None
        self._rect_placing      = False
        self._rect_ref_start    = (0.0, 0.0)
        self._rect_ref_cur      = (0.0, 0.0)
        self._tab_cycle_hits    = []
        self._tab_cycle_pos     = 0
        self._circle_placing    = False
        self._circle_ref_center = (0.0, 0.0)
        self._circle_ref_radius = 5.0
        
        # ── Selection Box (Marquee) ──────────────────────────────────────────
        self._sel_box_active    = False
        self._sel_box_start     = (0.0, 0.0)
        self._sel_box_cur       = (0.0, 0.0)
        self.clipboard: list    = []      # Appunti per copia/incolla oggetti

        # ── Panels ───────────────────────────────────────────────────────────
        self.l_tab          = TAB_TREE
        self.r_tab          = TAB_LAYERS
        self.catalog_sel    = None
        self.catalog_scroll = 0
        self.tree_scroll    = 0
        self.prop_scroll    = 0
        # Effects tab state
        self.effects_catalog_sel:    str  = None   # id effetto selezionato nel catalogo
        self.effects_catalog_scroll: int  = 0
        self.sel_effect_idx:         int  = None   # indice effetto selezionato in scena
        self._fx_editor_time:        float = 0.0   # tempo per animazione preview editor
        self.tree_expanded: dict = {}
        self.panel_l_w      = 300
        self.panel_r_w      = 300
        self.panels_visible = True

        # ── Catalog search ───────────────────────────────────────────────────
        self.catalog_search    = ""
        self.catalog_searching = False
        self.catalog_tag_search = ""
        self.catalog_tag_searching = False
        self.catalog_tag_filters = set()
        self.catalog_tags_scroll = 0
        self.catalog_style_filter = "real"

        # ── Numeric Editing ──────────────────────────────────────────────────
        self._editing_prop = None  # (owner_type, id, key) -> owner_type: 'object' or 'effect'
        self._prop_buf     = ""
        self._dragging_slider = None # (owner, id, key, min, max, start_x, width)

        # ── Layers ───────────────────────────────────────────────────────────
        self.layer_vis:    dict = {
            "objects_low":  False,
            "objects_mid":  True,
            "objects_high": False,
            "overlay":      True,
            "effects":      False
        }
        self.layer_locked: dict = {l["id"]: False for l in DEFAULT_LAYERS}
        self.layer_locked["effects"] = False
        self.active_layer       = "objects_mid"
        self._resizing_l        = False
        self._resizing_r        = False

        # ── View toggles ─────────────────────────────────────────────────────
        _view_settings = self._boot_settings
        self.show_overlay = False
        self.show_grid    = False
        self.grid_size    = int(_view_settings.get("grid_size", DEFAULT_GRID_SIZE))
        self.grid_snap    = True
        self.obj_snap     = bool(_view_settings.get("obj_snap", True))
        self.show_icons   = True
        # Guide di snap a oggetti attive durante il drag: lista di ("v"|"h", coord scena)
        self._snap_guides: list = []
        # Timestamp ultimo nudge da tastiera (coalescing undo)
        self._last_nudge_ts = 0.0

        # ── Tool mode ────────────────────────────────────────────────────────
        self.mode = MODE_SELECT

        # ── Undo/Redo ────────────────────────────────────────────────────────
        self.undo_stack: list = []
        self.redo_stack: list = []

        # ── Anteprima come-in-gioco ──────────────────────────────────────────
        self._preview_mode = False
        self._preview_saved: dict = {}

        # ── Stack modale unificato ───────────────────────────────────────────
        # Oggetti con handle_event(editor, ev) -> bool e render(editor).
        # Il top dello stack cattura tutto l'input utente (vedi _handle_events).
        self.modal_stack: list = []

        # ── Status bar ───────────────────────────────────────────────────────
        self.status_msg   = "Seleziona un gioco per iniziare"
        self.status_col   = TXT_DIM
        self.status_until = 0.0

        # ── Autosave ─────────────────────────────────────────────────────────
        self.last_autosave = time.time()

        # ── Game selector state ──────────────────────────────────────────────
        self.gs_games:       list  = _discover_games(base_path)
        self.gs_sel_game:    int   = None
        self.gs_sel_level:   int   = None
        self.gs_sel_scene:   int   = None
        self.gs_cur_levels:  list  = []
        self.gs_cur_scenes:  list  = []
        self._gs_new_mode:   str   = None
        self._gs_new_buf:    str   = ""
        self._gs_edit_mode:       str   = None   # "level" | "scene" | "game"
        self._gs_edit_buf:        str   = ""
        self._gs_edit_lang_bufs:  dict  = {}     # {lang: str} per level/scene
        self._gs_edit_active_field: str = "it"   # campo lingua attivo nel dialog
        self._gs_edit_bg_path: str = ""
        self._gs_edit_vid_path: str = ""
        self._gs_new_vid_path: str = ""
        self._gs_edit_music_paths: list = []
        self._gs_new_music_paths:  list = []
        self.gs_edit_mu_scroll      = 0
        self._gs_last_click: float = 0.0
        self._gs_last_col:   int   = -1
        self.gs_scroll_game         = 0
        self.gs_scroll_lvl          = 0
        self.gs_scroll_scn          = 0
        self._gs_del_mode:  str     = None   # "level" | "scene"
        self._gs_del_path           = None   # Path da eliminare
        self._gs_del_name:  str     = ""     # nome da mostrare nel dialog

        # Migrazione categorie (Desktop/Android)
        self._gs_migrate_categories()

        # ── Image cache ──────────────────────────────────────────────────────
        from collections import OrderedDict
        self._img_cache = OrderedDict()  # LRU con cap IMG_CACHE_MAX (evict graduale)
        self._bg_cache_surf: Optional[pygame.Surface] = None
        self._bg_cache_zoom: float = 0.0
        self._obj_draw_cache = OrderedDict()  # Cache per icone trasformate (LRU)
        self._filter_cache   = OrderedDict()  # Cache per icone filtrate (BN/Colore)
        self.active_tooltip: Optional[str] = None

        # ── Hitbox Registry (Editor Interaction) ─────────────────────────────
        self._scene_props_hitboxes = {}
        self._obj_props_hitboxes   = {}
        self._fx_props_hitboxes    = {}
        self._catalog_item_hitboxes = []
        self._effects_item_hitboxes = []
        self._catalog_chip_rects    = []
        
        # ── Dirty Canvas Cache ────────────────────────────────────────────────
        self._canvas_cache_surf: Optional[pygame.Surface] = None
        self._canvas_cache_dirty: bool = True
        self._last_canvas_rect = pygame.Rect(0,0,0,0)

        # ── Menu State ───────────────────────────────────────────────────────
        self._active_menu: Optional[str] = None  # Nome del menu aperto (es. "File")
        self._menu_bounds: dict = {}             # pos dei pulsanti menu per hit-test
        
        self._lang_modal    = False
        self._lang_sel          = None
        
        # Cache per aspect ratio originali (cat_id -> ratio)
        self._asset_ratios_cache: dict = {}
        
        # ── UI State ─────────────────────────────────────────────────────────
        self._loading: bool = False
        
        # Inizializza dati extra (recent_scenes, modals, etc)
        self._build_processes: list = []
        self._img_editor_init_state()
        self._init_extra_data(initial_game)
        self._icon_modal_init()
        self._scatter_modal_init()
        # Pre-carica il modello IA in background (se l'utente lo ha scelto e disponibile)
        self._scatter_preload_async()
        self._load_bubble_presets()
        self._tag_modal_active = False
        self._confirm_leave_modal = False
        self._auditor_init()
        self._confirm_clear = False
        self._pending_action = None  # Comando o funzione da eseguire dopo la conferma

        # Il caricamento del gioco iniziale (--game) va per ULTIMO: _load_game ->
        # _load_scene -> _scatter_reset usa stato creato da _scatter_modal_init e
        # dagli altri init dei mixin qui sopra. Prima stava in fondo a
        # _init_extra_data e crashava con AttributeError su _scatter_cancel_event.
        if initial_game:
            self._load_game(initial_game)

    def _TR(self, key: str, *args) -> str:
        """Helper rapido per la localizzazione (engine strings)."""
        return self.lang_manager.get(key, *args)

    def _mark_dirty(self):
        """Invalida la cache del canvas per forzare un ridisegno completo."""
        self._canvas_cache_dirty = True

    def _modal_push(self, modal) -> None:
        """Apre un modale nello stack unificato (il top cattura l'input)."""
        self.modal_stack.append(modal)

    def _modal_pop(self, modal=None) -> None:
        """Chiude il modale indicato (o il top dello stack)."""
        if modal is None:
            if self.modal_stack:
                self.modal_stack.pop()
        elif modal in self.modal_stack:
            self.modal_stack.remove(modal)

    def _set_ui_scale(self, delta: float):
        """Cambia la scala dei font/icone della UI (Ctrl+Piu'/Meno) e la persiste."""
        from editor.ui.draw import _ui_scale
        new_scale = round(
            max(UI_SCALE_MIN, min(UI_SCALE_MAX, _ui_scale() + delta)), 2)
        _init_fonts(new_scale)
        self._save_editor_setting("ui_scale", new_scale)
        self._mark_dirty()
        self._status(self._TR("ed_ui_scale", "UI scale: {n}%").format(
            n=int(new_scale * 100)), ACCENT, 2)

    def _get_asset_ratio(self, cat_id: str) -> float:
        """Restituisce l'aspect ratio (w/h) di un asset, usando la cache di sessione."""
        if cat_id in self._asset_ratios_cache:
            return self._asset_ratios_cache[cat_id]
        
        # 1. Cerca nel catalogo caricato
        cat_item = next((c for c in getattr(self, "catalog", []) if c["id"] == cat_id), None)
        if not cat_item: 
            return 1.0
        
        # 2. Verifica se il ratio è già presente nei metadati (ottimizzazione futura)
        if "aspect_ratio" in cat_item:
            self._asset_ratios_cache[cat_id] = cat_item["aspect_ratio"]
            return cat_item["aspect_ratio"]

        # 3. Caricamento fisico (solo se necessario)
        img_rel = cat_item.get("icon", cat_item.get("image", ""))
        if not img_rel: return 1.0
        
        # Risoluzione path (gioco -> motore)
        ip = self.game_path / img_rel if getattr(self, "game_path", None) else Path()
        if not ip.exists():
            master_p = self.base_path / "engine" / "assets" / img_rel
            if master_p.exists():
                ip = master_p
            else:
                return 1.0
        
        try:
            # Carica solo l'header dell'immagine se possibile, o usa la cache immagini
            # Se l'immagine è già nella cache di io_ops, la usiamo
            # Usiamo una dimensione fittizia piccola per _load_img per minimizzare l'impatto
            cached_img = self._load_img(ip, (100, 100))
            if cached_img:
                # Nota: _load_img restituisce una superficie scalata, 
                # ma l'immagine ORIGINALE ha lo stesso ratio.
                # Tuttavia, per sicurezza carichiamo l'originale una volta.
                surf = pygame.image.load(str(ip))
                w, h = surf.get_size()
                ratio = w / h if h != 0 else 1.0
                self._asset_ratios_cache[cat_id] = ratio
                return ratio
        except Exception as e:
            import logging
            logging.warning(f"[EDITOR] Errore calcolo ratio per {cat_id}: {e}")
        
        return 1.0

    def _init_extra_data(self, initial_game=None):
        # Chiamata alla fine di __init__ per pulizia
        self.recent_scenes: list = []
        self._lang_data:  dict = {}
        self._lang_buf:   str  = ""
        self._lang_scroll: int = 0
        self._lang_dirty: bool = False

        # ── Music modal ──────────────────────────────────────────────────────
        self._music_modal  = False
        self._music_files  = []
        self._music_scroll = 0
        self._music_playing = None

        # ── Background modal ─────────────────────────────────────────────────
        self._bg_modal = False
        self._vid_modal = False

        # ── Context menu ─────────────────────────────────────────────────────
        self._ctx_menu = None

        # ── New object dialog ────────────────────────────────────────────────
        self._newobj_modal: bool = False
        self._newobj: dict = {
            "id": "", "icon_path": "", "detection": "circle",
            "radius": 30, "width": 60, "height": 60, "hint": 30,
        }
        self._newobj_field: str = "id"
        self._newobj_buf:   str = ""
        # ── Hint delay editing ───────────────────────────────────────────────
        self._editing_hint = False
        self._hint_buf: str = ""

        # ── Recent scenes ────────────────────────────────────────────────────
        self.recent_scenes = self._load_recent_config()

        # ── Presets per Bubble Tips ──────────────────────────────────────────
        self.bubble_presets: dict = {}
        self._preset_dropdown_open: bool = False
        self._editing_preset_name: bool = False
        self._preset_name_buf: str = ""
        self._preset_selected: str = ""

        # ── Minigame modal ───────────────────────────────────────────────────
        self._minigame_modal = False
        self._available_minigames = []

    def _play_click(self):
        if self._snd_click:
            self._snd_click.play()

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        try:
            while self.running:
                self.clock.tick(60)
                phase = "events"
                try:
                    self._handle_events()
                    phase = "update"
                    self._update()
                    phase = "render"
                    self._render()
                    phase = "flip"
                    pygame.display.flip()
                except Exception:
                    import logging
                    logging.getLogger("crash").critical(
                        "Crash nel main loop (fase=%s)", phase, exc_info=True
                    )
                    raise
        finally:
            # Chiusura pulita: termina i processi di build pendenti e libera pygame.
            # Questo e' l'UNICO punto in cui pygame.quit() deve essere chiamato.
            self._cleanup_processes()
            pygame.quit()

    def _with_loading(self, action, *args, **kwargs):
        """
        Esegue un'azione (funzione o callable) mostrando l'overlay di caricamento.
        Gestisce automaticamente il rendering preventivo e il reset del flag.
        """
        if not callable(action):
            return
            
        self._loading = True
        # Forza il rendering dell'overlay prima di iniziare l'operazione bloccante
        self._render()
        pygame.display.flip()
        pygame.event.pump()
        # Piccolo delay per permettere all'OS di aggiornare la finestra su Windows
        pygame.time.delay(20)
        
        try:
            return action(*args, **kwargs)
        except Exception as e:
            import logging
            logging.error(f"Errore durante operazione con caricamento: {e}")
            self._status(self._TR("io_error", "Error: {e}").format(e=e), (200, 50, 50), 5)
        finally:
            self._loading = False
            # Render finale per pulire l'overlay
            self._render()
            pygame.display.flip()
            pygame.event.pump()

    def _cleanup_processes(self):
        """Chiude forzatamente eventuali dialog o processi di build aperti."""
        for proc in self._build_processes:
            if proc.poll() is None:  # Se è ancora in esecuzione
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._build_processes.clear()

    def _update(self):
        self._fx_editor_time += 1 / 60.0   # avanza preview animazioni effetti
        if self.scene_dirty and self.scene_path:
            if time.time() - self.last_autosave > AUTOSAVE_SECS:
                self._autosave()
        if self.status_until and time.time() > self.status_until:
            self.status_until = 0
            self.status_msg   = ""
            self.status_col   = TXT_DIM

    def _render(self):
        self.screen.fill(BG)
        self.active_tooltip = None
        if self.state == STATE_GAME_SELECT:
            self._r_game_select()
        else:
            self._r_main()
            
        w, h = self.screen.get_size()
        # La Top Bar va disegnata DOPO il contenuto principale (Canvas/Dashboard)
        # per garantire che i menu dropdown siano sopra tutto.
        self._r_top_bar(w)
        
        # Modali specifici dell'editor
        if self._lang_modal:
            self._r_lang_modal(w, h)
        if self._newobj_modal:
            self._r_newobj_modal(w, h)
        if self._ctx_menu:
            self._r_ctx_menu(w, h)
        if self._img_editor_active:
            self._r_img_editor_modal(w, h)
        if self._tag_modal_active:
            self._r_tag_modal(w, h)
        # Modali globali (funzionano sia in dashboard che in editor)
        if getattr(self, "_music_modal", False):
            self._r_music_modal(w, h)
        if getattr(self, "_minigame_modal", False):
            self._r_minigame_modal(w, h)
        if getattr(self, "_bg_modal", False):
            self._r_background_modal(w, h)
        if getattr(self, "_vid_modal", False):
            self._r_video_modal(w, h)
        if getattr(self, "_icon_modal", False):
            self._r_icon_modal(w, h)
        # Auditor modale (funziona sia in dashboard che in editor)
        if getattr(self, "_auditor_active", False):
            self._r_auditor_modal(w, h)
        # Scatter modal
        if getattr(self, "_scatter_modal_open", False):
            self._r_scatter_modal(w, h)
        # Statistiche scena
        if getattr(self, "_stats_modal", False):
            self._r_stats_modal(w, h)
        # Ripristino autosave (crash recovery): sopra le modali normali
        if getattr(self, "_recovery_modal", False):
            self._r_recovery_modal(w, h)
        # Conferma uscita/salvataggio: sempre sopra TUTTE le altre modali
        if self._confirm_leave_modal:
            self._r_confirm_leave_modal(w, h)

        # Stack modale unificato (nuovi modali non-flag): sopra i modali legacy
        for modal in self.modal_stack:
            modal.render(self)

        # Status Bar (Globale, disegnata sopra tutto)
        self._r_status(w, h)

        # Overlay di caricamento (MASSIMA priorità, disegnato SOPRA lo status)
        if self._loading:
            self._r_loading_overlay(w, h)

        # Tooltip finale (Sopra ogni cosa, incluso l'overlay se attivo, per feedback mouse)
        if self.active_tooltip:
            _draw_tooltip(self.screen, self.active_tooltip, pygame.mouse.get_pos())

    def _r_main(self):
        w, h = self.screen.get_size()
        self._update_layout()
        
        # 1. Canvas (Sotto tutto)
        self._r_canvas(w, h)
        
        # 2. Pannelli laterali (Sopra il canvas)
        if self.panels_visible:
            self._r_left(h)
            self._r_right(w, h)

        # 3. HUD simulato dell'anteprima come-in-gioco
        if self._preview_mode:
            self._r_preview_hud(w)

    def _r_loading_overlay(self, w: int, h: int):
        """Disegna un overlay premium per il caricamento."""
        # Utilizzo di una Surface di cache per l'overlay per evitare re-allocazioni costose
        if not hasattr(self, "_loading_surf") or self._loading_surf.get_size() != (w, h):
            self._loading_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._loading_surf.fill((15, 15, 20, 200))
        
        self.screen.blit(self._loading_surf, (0, 0))
        
        # Box centrale
        bw, bh = 360, 140
        bx, by = (w - bw) // 2, (h - bh) // 2
        
        # Ombra box (usando colore solido scuro per compatibilità draw.rect su display surface)
        _rect(self.screen, (10, 10, 15), (bx + 4, by + 4, bw, bh), radius=12)
        # Background box
        _rect(self.screen, (40, 42, 54), (bx, by, bw, bh), radius=12)
        # Bordo accentato
        _rect(self.screen, ACCENT, (bx, by, bw, bh), 2, radius=12)
        
        # Icona animata (pulsazione semplice basata sul tempo)
        import math
        t = time.time()
        pulse = (math.sin(t * 10) + 1) / 2 # 0 to 1
        icon_size = 44 + int(pulse * 12)
        ix, iy = bx + 35, by + (bh - icon_size) // 2
        
        # Disegna icona FX (scintilla) come caricamento
        _draw_shape_icon(self.screen, (ix, iy, icon_size, icon_size), "fx", ACCENT)
        
        # Testo tradotto
        msg = self._TR("msg_loading")
        _draw_text(self.screen, msg, "lg", TXT_HI, bx + 105, by + bh // 2 - 15)
        _draw_text(self.screen, "Please wait...", "xs", (120, 120, 140), bx + 105, by + bh // 2 + 16)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    from engine.utils import install_crash_handlers
    install_crash_handlers()
    parser = argparse.ArgumentParser(description="HiddenEngine Level Editor")
    parser.add_argument("--game", default=None, help="Nome del gioco da aprire subito")
    parser.add_argument("--play-game", default=None, help="Esegue il gioco standalone (usato da subprocess EXE)")
    parser.add_argument("--minigame", default=None, help="Esegue in test minigioco (usato da subprocess EXE)")
    parser.add_argument("--lang", default="en", help="Lingua")
    parser.add_argument("--fullscreen", action="store_true", help="Forza fullscreen per EngineCore")
    parser.add_argument("--build-ui", nargs=4, metavar=('GAME', 'VER', 'DIR', 'STAT'), help="Avvia UI di build")
    parser.add_argument("--build-manager", nargs=4, metavar=('GAME', 'VER', 'DIR', 'STAT'), help="Avvia il build manager vero e proprio")
    parser.add_argument("--android-build-ui", nargs=4, metavar=('GAME', 'VER', 'DIR', 'STAT'), help="Avvia UI di build APK Android")
    parser.add_argument("--android-build-manager", nargs=4, metavar=('GAME', 'VER', 'DIR', 'STAT'), help="Avvia il build manager APK Android")
    parser.add_argument("--no-zip", action="store_true", help="Salta la creazione dello ZIP in build_manager")
    parser.add_argument("--release", action="store_true", help="Build APK release firmata (usato da --android-build-manager)")
    args = parser.parse_args()

    # Routing dei processi secondari (essenziale per l'EXE PyInstaller)
    if args.minigame or args.play_game:
        import configparser
        from engine.core import EngineCore
        config = configparser.ConfigParser()
        config.add_section("engine")
        
        target_game = args.play_game if args.play_game else args.game
        config.set("engine", "default_game", target_game or "")
        
        engine = EngineCore(game_id=target_game, config=config, cli_args=args)
        engine.run()
        return

    if args.build_ui:
        from editor.build_ui import show_build_progress
        show_build_progress(*args.build_ui)
        return

    if args.build_manager:
        import sys as _sys
        from editor.build_manager import run_build
        # Assicura PYTHONPATH per PyInstaller sub-proc
        exit_code = run_build(
            args.build_manager[0], args.build_manager[1],
            args.build_manager[2], args.build_manager[3],
            create_zip=not args.no_zip
        )
        _sys.exit(exit_code)

    if args.android_build_ui:
        from editor.android_build_ui import show_android_build_progress
        show_android_build_progress(*args.android_build_ui)
        return

    if args.android_build_manager:
        import sys as _sys
        from editor.android_build_manager import run_apk_build
        exit_code = run_apk_build(
            args.android_build_manager[0], args.android_build_manager[1],
            args.android_build_manager[2], args.android_build_manager[3],
            release=args.release,
        )
        _sys.exit(exit_code)

    from engine.utils import get_base_path
    base = get_base_path()
    editor = LevelEditor(base_path=base, initial_game=args.game)
    editor.run()


if __name__ == "__main__":
    main()
