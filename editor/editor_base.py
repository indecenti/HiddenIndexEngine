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
import time
from pathlib import Path
from typing import Optional

import pygame
import math

# ── Costanti e UI primitives ─────────────────────────────────────────────────
from editor.constants import (
    VERSION,
    STATE_GAME_SELECT, STATE_MAIN,
    TAB_TREE, TAB_CATALOG, TAB_EFFECTS, TAB_LAYERS, TAB_PROPS,
    MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_EFFECT_PLACE,
    DEFAULT_LAYERS,
    BG, TXT_DIM, TXT_HI, ACCENT,
    AUTOSAVE_SECS, SND_CLICK,
)
from editor.ui.draw import _init_fonts, _draw_tooltip, _rect, _draw_text, _draw_shape_icon
from editor.core.io import _discover_games
from engine.utils import setup_logging
from engine.language_manager import LanguageManager

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
):
    """
    Editor di livelli HiddenEngine.
    Tutti i metodi funzionali vivono nei mixin; questa classe
    gestisce lo stato condiviso e il ciclo principale.
    """

    def __init__(self, base_path: Path, initial_game: str = None):
        self.base_path = base_path

        pygame.init()
        pygame.display.set_caption(f"HiddenEngine Level Editor  [{VERSION}]")
        self.fullscreen = False
        self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        try:
            import ctypes
            hwnd = pygame.display.get_wm_info().get('window')
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # 3 = SW_MAXIMIZE
        except Exception:
            pass
        self.screen_size = self.screen.get_size()
        self.clock = pygame.time.Clock()
        _init_fonts()

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

        # ── Localizzazione ───────────────────────────────────────────────────
        self.lang_manager = LanguageManager()
        self.LANGS = ["it", "en", "es", "fr", "de"]
        
        # Carica lingua dalle impostazioni o usa default 'it'
        settings = self._load_editor_settings()
        self.current_lang = settings.get("language", "it")
        
        # Fallback a 'it' se la lingua salvata non è tra quelle supportate
        if self.current_lang not in self.LANGS:
            self.current_lang = "it"
            
        self.lang_manager.load_for_game("engine", self.current_lang)

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
        self.catalog_tags_scroll = 0

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
        self.show_overlay = False
        self.show_grid    = False
        self.grid_size    = 32
        self.grid_snap    = True
        self.show_icons   = True

        # ── Tool mode ────────────────────────────────────────────────────────
        self.mode = MODE_SELECT

        # ── Undo/Redo ────────────────────────────────────────────────────────
        self.undo_stack: list = []
        self.redo_stack: list = []

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

        # ── Image cache ──────────────────────────────────────────────────────
        self._img_cache: dict = {}
        self._bg_cache_surf: Optional[pygame.Surface] = None
        self._bg_cache_zoom: float = 0.0
        self._obj_draw_cache: dict = {}  # Cache per icone trasformate
        self.active_tooltip: Optional[str] = None

        # ── Hitbox Registry (Editor Interaction) ─────────────────────────────
        self._scene_props_hitboxes = {}
        self._obj_props_hitboxes   = {}
        self._fx_props_hitboxes    = {}
        self._catalog_item_hitboxes = []
        self._effects_item_hitboxes = []
        self._catalog_chip_rects    = []

        # ── Language editor ──────────────────────────────────────────────────
        self.LANGS          = ["it", "en", "es", "fr", "de"]
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
        self._build_processes: list[subprocess.Popen] = []
        self._img_editor_init_state()
        self._init_extra_data(initial_game)
        self._load_bubble_presets()

    def _TR(self, key: str, *args) -> str:
        """Helper rapido per la localizzazione (engine strings)."""
        return self.lang_manager.get(key, *args)

    def _get_asset_ratio(self, cat_id: str) -> float:
        if cat_id in self._asset_ratios_cache:
            return self._asset_ratios_cache[cat_id]
        
        # Cerca nel catalogo
        cat_item = next((c for c in self.catalog if c["id"] == cat_id), None)
        if not cat_item: return 1.0
        
        img_rel = cat_item.get("icon", cat_item.get("image", ""))
        if not img_rel: return 1.0
        
        ip = self.game_path / img_rel
        if not ip.exists():
            # Fallback master engine
            master_p = self.base_path / "engine" / "assets" / "objects" / Path(img_rel).name
            if master_p.exists():
                ip = master_p
            else:
                return 1.0
        
        try:
            # Carica info immagine (pygame.image.load è OK per il dump del ratio)
            surf = pygame.image.load(str(ip))
            w, h = surf.get_size()
            ratio = w / h if h != 0 else 1.0
            self._asset_ratios_cache[cat_id] = ratio
            return ratio
        except Exception:
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

        if initial_game:
            self._load_game(initial_game)

    def _play_click(self):
        if self._snd_click:
            self._snd_click.play()

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            self.clock.tick(60)
            self._handle_events()
            self._update()
            self._render()
            pygame.display.flip()
        
        # Cleanup processi pendenti
        self._cleanup_processes()
        pygame.quit()

    def _cleanup_processes(self):
        """Chiude forzatamente eventuali dialog o processi di build aperti."""
        import subprocess
        for proc in self._build_processes:
            if proc.poll() is None:  # Se è ancora in esecuzione
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except:
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
        
        if self.state != STATE_GAME_SELECT:
            if self._lang_modal:
                self._r_lang_modal(w, h)
            if self._newobj_modal:
                self._r_newobj_modal(w, h)
            if self._ctx_menu:
                self._r_ctx_menu(w, h)
            if self._img_editor_active:
                self._r_img_editor_modal(w, h)
        # Modali globali (funzionano sia in dashboard che in editor)
        if getattr(self, "_music_modal", False):
            self._music_modal_modal_active = True # Segnaposto se serve
            self._r_music_modal(w, h)
        if getattr(self, "_minigame_modal", False):
            self._r_minigame_modal(w, h)
        if getattr(self, "_bg_modal", False):
            self._r_background_modal(w, h)
        if getattr(self, "_vid_modal", False):
            self._r_video_modal(w, h)
        
        # Overlay di caricamento (massima priorità)
        if self._loading:
            self._r_loading_overlay(w, h)

        # Status Bar (Globale, disegnata sopra tutto tranne tooltip)
        self._r_status(w, h)

        # Tooltip finale
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

    def _r_loading_overlay(self, w: int, h: int):
        """Disegna un overlay premium per il caricamento."""
        # Overlay semi-trasparente scuro
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((15, 15, 20, 200)) # Leggermente più opaco per immediatezza
        self.screen.blit(overlay, (0, 0))
        
        # Box centrale
        bw, bh = 340, 120
        bx, by = (w - bw) // 2, (h - bh) // 2
        
        # Ombra box
        _rect(self.screen, (10, 10, 15, 100), (bx + 4, by + 4, bw, bh), radius=12)
        # Background box
        _rect(self.screen, (40, 42, 54), (bx, by, bw, bh), radius=12)
        # Bordo accentato
        _rect(self.screen, ACCENT, (bx, by, bw, bh), 2, radius=12)
        
        # Icona animata (pulsazione semplice basata sul tempo)
        import math
        pulse = (math.sin(time.time() * 10) + 1) / 2 # 0 to 1
        icon_size = 40 + int(pulse * 10)
        ix, iy = bx + 30, by + (bh - icon_size) // 2
        
        # Disegna icona FX (scintilla) come caricamento
        _draw_shape_icon(self.screen, (ix, iy, icon_size, icon_size), "fx", ACCENT)
        
        # Testo tradotto
        msg = self._TR("msg_loading")
        _draw_text(self.screen, msg, "lg", TXT_HI, bx + 95, by + bh // 2 - 12)
        _draw_text(self.screen, "Please wait...", "xs", (120, 120, 140), bx + 95, by + bh // 2 + 14)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="HiddenEngine Level Editor")
    parser.add_argument("--game", default=None, help="Nome del gioco da aprire subito")
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1]
    editor = LevelEditor(base_path=base, initial_game=args.game)
    editor.run()


if __name__ == "__main__":
    main()
