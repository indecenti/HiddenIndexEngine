"""
editor/mixins/game_select.py

GameSelectMixin — schermata di selezione gioco/livello/scena:
                  logica, eventi, rendering dashboard.
"""

import os
import sys
import time
import json
import subprocess
import logging
import threading
import pygame
import re
from collections import deque
from pathlib import Path

from editor.constants import (
    TOP_BAR_H, STATE_MAIN,
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, PANEL,
    TXT, TXT_DIM, TXT_HI, OK_C, WARN_C, ERR_C,
    VERSION,
)
from editor.core.io import (
    _discover_games, _discover_levels, _load_json, _save_json, _load_scene_data,
)
from editor.build_system import next_build_version
from editor.ui.draw import (
    _txt, _draw_text, _text_wh, _rect, _button, _in_rect, _draw_shape_icon, _scrollbar, _input_box
)
from editor.ui.widgets import Button, WidgetGroup
from engine.utils import get_base_path, get_logger

logger = get_logger("game_select")


class GameSelectMixin:
    """Dashboard selezione progetto (3 colonne) + dialogo creazione."""

    # Geometria dialogo "Sposta scena" (sincronizzata tra _r_gs_move_dialog e _gs_click)
    _GS_MV_DIALOG_W: int = 480
    _GS_MV_ROW_H: int = 40
    _GS_MV_LIST_Y: int = 96
    _GS_MV_MAX_ROWS: int = 10
    _GS_MV_FOOTER_H: int = 64
    # Suffissi per le copie: cartella su disco e nome leggibile multilingua
    _GS_COPY_SUFFIX: str = "_copy"
    _GS_COPY_LABEL_SUFFIX: str = " (copia)"

    def _gs_migrate_categories(self):
        """Assicura che tutti i giochi abbiano la categoria 'desktop' se mancante."""
        modified = False
        for gname in self.gs_games:
            p = self.base_path / "games" / gname / "game_config.json"
            if p.exists():
                cfg = _load_json(p)
                if "category" not in cfg:
                    cfg["category"] = "desktop"
                    _save_json(p, cfg)
                    logger.info(f"Migrazione: Categoria 'desktop' aggiunta a '{gname}'")
                    modified = True
        return modified

    # ─────────────────────────────────────────────────────────────────────────
    # DRAG & DROP DASHBOARD
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_mmove(self, mx, my_raw):
        """Gestisce il trascinamento degli elementi per il riordino."""
        if not hasattr(self, "gs_dragging_idx") or self.gs_dragging_idx is None:
            return
        
        col = self.gs_dragging_col
        idx = self.gs_dragging_idx
        
        ITEM_H = 64 if col == 2 else (50 if col == 1 else 34)
        
        # Sincronizzazione precisa con _r_game_select
        header_y = TOP_BAR_H
        header_h = 80
        y_rec = header_y + header_h + 30
        y_browser = y_rec + 200
        iy = y_browser + 60
        
        scroll = [self.gs_scroll_game, self.gs_scroll_lvl, self.gs_scroll_scn][col]
        
        # Calcolo indice target
        new_idx = (my_raw - iy + scroll * ITEM_H) // ITEM_H
        
        if new_idx != idx:
            count = [len(self.gs_games), len(self.gs_cur_levels), len(self.gs_cur_scenes)][col]
            if 0 <= new_idx < count:
                delta = 1 if new_idx > idx else -1
                if col == 0: self._gs_move_game(idx, delta)
                elif col == 1: self._gs_move_level(idx, delta)
                elif col == 2: self._gs_move_scene(idx, delta)
                self.gs_dragging_idx = new_idx

    def _gs_mup(self, mx, my_raw):
        """Rilascia l'elemento e pulisce lo stato di dragging."""
        self.gs_dragging_idx = None
        self.gs_dragging_col = None

    # ─────────────────────────────────────────────────────────────────────────
    # COMPILAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_compile_game(self, idx: int):
        """Avvia la compilazione e il packaging di un gioco."""
        if idx is None or idx >= len(self.gs_games):
            self._status(self._TR("gs_invalid_game", "Error: invalid game"), ERR_C, 2)
            return

        game_id = self.gs_games[idx]
        game_path = self.base_path / "games" / game_id
        game_config_path = game_path / "game_config.json"

        if not game_config_path.exists():
            self._status(self._TR("gs_no_game_config", "Error: game_config.json not found for '{0}'").format(game_id), ERR_C, 3)
            return

        # Calcola la prossima versione (auto-increment)
        version = next_build_version(game_id)

        # Crea cartella di output
        output_dir = self.base_path / "build" / game_id / version
        output_dir.mkdir(parents=True, exist_ok=True)

        # File di stato per comunicazione tra subprocess e UI
        status_file = output_dir / "build_status.json"

        # Crea file di stato iniziale
        initial_status = {
            "progress": 0,
            "step": "Inizializzazione...",
            "log": [],
            "success": None,
            "error_msg": None,
            "zip_path": None,
        }
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(initial_status, f)

        self._status(self._TR("gs_build_start", "Starting build: {0} v{1}...").format(game_id, version), WARN_C, 2)

        try:
            # Lancia SOLO la finestra progress UI (Tkinter).
            # È la UI stessa a lanciare build_manager con le opzioni scelte
            # (incluso il flag --no-zip), evitando build duplicati.
            if getattr(sys, 'frozen', False):
                cmd = [
                    sys.executable,
                    "--build-ui",
                    game_id,
                    version,
                    str(output_dir),
                    str(status_file),
                ]
            else:
                ui_script = self.base_path / "editor" / "build_ui.py"
                cmd = [
                    sys.executable,
                    str(ui_script),
                    game_id,
                    version,
                    str(output_dir),
                    str(status_file),
                ]
            
            p2 = subprocess.Popen(
                cmd,
                cwd=str(self.base_path),
            )
            self._build_processes.append(p2)

            logger.info(f"Finestra build aperta per {game_id} v{version}")
            self._status(self._TR("gs_build_window", "Build window opened: {0} v{1}").format(game_id, version), OK_C, 3)

        except Exception as e:
            logger.exception(f"Errore lancio subprocess: {e}")
            self._status(self._TR("io_error", "Error: {0}").format(str(e)), ERR_C, 4)

    def _gs_compile_apk(self, idx: int):
        """Avvia la compilazione di un APK Android del gioco (parallelo a _gs_compile_game).

        Stessa filosofia del builder EXE: lancia android_build_ui.py come subprocess
        Tkinter, che a sua volta lancia android_build_manager.py.
        Comunicazione via build_status.json nel build_dir.
        """
        if idx is None or idx >= len(self.gs_games):
            self._status(self._TR("gs_invalid_game", "Error: invalid game"), ERR_C, 2)
            return

        game_id = self.gs_games[idx]
        game_path = self.base_path / "games" / game_id
        game_config_path = game_path / "game_config.json"

        if not game_config_path.exists():
            self._status(self._TR("gs_no_game_config", "Error: game_config.json not found for '{0}'").format(game_id), ERR_C, 3)
            return

        version = next_build_version(game_id)

        # Output: build/<game_id>/<version>/android/
        output_dir = self.base_path / "build" / game_id / version / "android"
        output_dir.mkdir(parents=True, exist_ok=True)

        status_file = output_dir / "build_status.json"
        initial_status = {
            "progress": 0,
            "step": "Inizializzazione build APK...",
            "log": [],
            "success": None,
            "error_msg": None,
            "apk_path": None,
            "apk_size_mb": None,
        }
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(initial_status, f)

        self._status(self._TR("gs_build_apk_start", "Starting APK build: {0} v{1}...").format(game_id, version), WARN_C, 2)

        try:
            if getattr(sys, "frozen", False):
                cmd = [
                    sys.executable,
                    "--android-build-ui",
                    game_id,
                    version,
                    str(output_dir),
                    str(status_file),
                ]
            else:
                ui_script = self.base_path / "editor" / "android_build_ui.py"
                cmd = [
                    sys.executable,
                    str(ui_script),
                    game_id,
                    version,
                    str(output_dir),
                    str(status_file),
                ]

            p2 = subprocess.Popen(cmd, cwd=str(self.base_path))
            self._build_processes.append(p2)

            logger.info(f"Finestra build APK aperta per {game_id} v{version}")
            self._status(self._TR("gs_build_apk_window", "APK build window opened: {0} v{1}").format(game_id, version), OK_C, 3)

        except Exception as e:
            logger.exception(f"Errore lancio subprocess APK: {e}")
            self._status(self._TR("io_error", "Error: {0}").format(str(e)), ERR_C, 4)

    def _gs_export_html(self, idx: int):
        """Esporta il gioco selezionato come sito statico HTML/JS tramite web_exporter.

        L'export gira in un thread daemon; il progresso e' mostrato da un
        modale NON bloccante (_WebExportProgressModal) nello stack unificato.
        """
        if idx is None or idx >= len(self.gs_games):
            self._status(self._TR("gs_invalid_game", "Error: invalid game"), ERR_C, 2)
            return

        game_id = self.gs_games[idx]
        game_path = self.base_path / "games" / game_id
        if not (game_path / "game_config.json").exists():
            self._status(self._TR("gs_no_game_config", "Error: game_config.json not found for '{0}'").format(game_id), ERR_C, 3)
            return

        output_dir = self.base_path / "build_web" / game_id
        self._status(self._TR("gs_export_html_start", "HTML export: {0}...").format(game_id), WARN_C, 2)
        self._modal_push(_WebExportProgressModal(self, game_id, output_dir))

    def _gs_run_game(self, idx: int):
        """Avvia il gioco in modalità standalone."""
        if idx is None or idx >= len(self.gs_games):
            self._status(self._TR("gs_invalid_game", "Error: invalid game"), ERR_C, 2)
            return

        game_id = self.gs_games[idx]
        try:
            # Avvia l'engine con il gioco selezionato tramite subprocess
            # Usiamo sys.executable per garantire che venga usato lo stesso interprete
            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, "--play-game", game_id]
            else:
                cmd = [sys.executable, "main.py", "--game", game_id]
                
            subprocess.Popen(
                cmd,
                cwd=str(self.base_path)
            )
            self._status(self._TR("gs_standalone_start", "Starting standalone: {0}").format(game_id), OK_C, 2)
            logger.info(f"Gioco standalone avviato: {game_id}")
        except Exception as e:
            logger.exception(f"Errore avvio gioco Standalone: {e}")
            self._status(self._TR("io_error", "Error: {0}").format(str(e)), ERR_C, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # SELEZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_select_game(self, idx: int):
        self.gs_sel_game   = idx
        self.gs_sel_level  = None
        self.gs_sel_scene  = None
        self.gs_cur_scenes = []
        # Reset scroll colonne dipendenti
        self.gs_scroll_lvl = 0
        self.gs_scroll_scn = 0
        
        gname = self.gs_games[idx]
        self.game_path = self.base_path / "games" / gname
        self._load_strings() 
        self.gs_cur_levels = _discover_levels(self.game_path)
        self._gs_refresh_cache(1)
        self._status(self._TR("gs_game_selected", "Game: {0}").format(gname), OK_C, 2)

    def _gs_select_level(self, idx: int):
        self.gs_sel_level  = idx
        self.gs_sel_scene  = None
        # Reset scroll colonna scene
        self.gs_scroll_scn = 0
        
        lvl = self.gs_cur_levels[idx]
        self.gs_cur_scenes = lvl["scenes"]
        self._gs_refresh_cache(2)

    def _gs_select_scene(self, idx: int):
        self.gs_sel_scene = idx

    def _gs_open(self):
        if self.gs_sel_game is None:
            self._status(self._TR("gs_select_game_first", "Select a game first"), WARN_C, 3); return

        # Cattura la selezione ADESSO: il worker non deve rileggere lo stato
        # della dashboard (che nel frattempo potrebbe cambiare).
        gname = self.gs_games[self.gs_sel_game]
        scenes = list(self.gs_cur_scenes)
        sel_scene = self.gs_sel_scene

        def _perform_open():
            self._load_game(gname)
            if sel_scene is not None:
                self._load_scene(scenes[sel_scene])
            elif scenes:
                self._load_scene(scenes[0])

        # SINCRONO sotto overlay, come ogni altra navigazione (_request_nav).
        # La versione in worker thread (_with_loading_async) mutava scene_data,
        # bg_surf, zoom e cache mentre il main thread renderizzava: lost update
        # su _canvas_cache_dirty (canvas che mostrava lo sfondo della scena
        # precedente) e scudo input che restava bloccato. Il caricamento dura
        # decimi di secondo: l'overlay bloccante e' sufficiente.
        self._with_loading(_perform_open)

    # ─────────────────────────────────────────────────────────────────────────
    # CREAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_new_game(self):
        self._gs_new_mode = "game"
        self._gs_new_buf  = "nuovo_gioco"
        self._gs_new_cursor = len("nuovo_gioco")
        self._gs_new_all_selected = False
        self._gs_new_active_field = "id"
        self._gs_new_bg_path = ""
        self._gs_new_vid_path = ""
        self._gs_new_bg_preview_surf = None
        self._gs_new_vid_preview_surf = None
        self._gs_new_music_paths = []
        self._gs_new_category = "desktop"
        self._gs_new_cat_dropdown = False

    def _gs_new_level(self):
        if self.gs_sel_game is None: return
        self._gs_new_mode = "level"
        self._gs_new_buf  = "level_nuovo"
        self._gs_new_cursor = len("level_nuovo")
        self._gs_new_all_selected = False
        self._gs_new_active_field = "id"
        self._gs_new_lang_bufs    = {l: "" for l in self.LANGS}
        self._gs_new_lang_cursors = {l: 0  for l in self.LANGS}

    def _gs_new_scene(self):
        if self.gs_sel_level is None: return
        self._gs_new_mode = "scene"
        self._gs_new_buf  = "scene_nuova"
        self._gs_new_cursor = len("scene_nuova")
        self._gs_new_all_selected = False
        self._gs_new_active_field = "id"
        self._gs_new_bg_path = ""
        self._gs_new_vid_path = ""
        self._gs_new_bg_preview_surf = None
        self._gs_new_vid_preview_surf = None

    # ─────────────────────────────────────────────────────────────────────────
    # EDITING
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_refresh_cache(self, col_idx=None):
        """Rigenera la cache dei nomi umani per le colonne specificate (o tutte)."""
        if not hasattr(self, "_gs_labels_cache"):
            self._gs_labels_cache = [[], [], []]
            
        cols = [col_idx] if col_idx is not None else [0, 1, 2]
        for c in cols:
            items = []
            if c == 0:
                for i in range(len(self.gs_games)):
                    items.append(self._gs_get_human_name("game", i))
            elif c == 1:
                for i in range(len(self.gs_cur_levels)):
                    items.append(self._gs_get_human_name("level", i))
            elif c == 2:
                for i in range(len(self.gs_cur_scenes)):
                    items.append(self._gs_get_human_name("scene", i))
            self._gs_labels_cache[c] = items
        
        # Meta cache per i giochi (Tema, Categoria, etc.)
        if not hasattr(self, "_gs_meta_cache"): self._gs_meta_cache = {}
        for i in range(len(self.gs_games)):
            gname = self.gs_games[i]
            p = self.base_path / "games" / gname / "game_config.json"
            if p.exists():
                cfg = _load_json(p)
                self._gs_meta_cache[i] = {
                    "theme": cfg.get("ui_theme", "default"),
                    "category": cfg.get("category", "desktop")
                }
            else:
                self._gs_meta_cache[i] = {"theme": "default", "category": "desktop"}

    def _gs_get_human_name(self, mode, idx):
        """Recupera il nome tradotto per un elemento della dashboard con caricamento on-the-fly."""
        lang = getattr(self, "current_lang", "en")
        try:
            if mode == "game":
                gname = self.gs_games[idx]
                p = self.base_path / "games" / gname / "game_config.json"
                if p.exists():
                    cfg = _load_json(p)
                    key = cfg.get("title_key", "game_title")
                    
                    # Cerca la traduzione nel gioco specifico
                    lang_p = self.base_path / "games" / gname / "strings" / f"{lang}.json"
                    if not lang_p.exists():
                        # Fallback su it o en se la lingua scelta non esiste per quel gioco
                        lang_p = self.base_path / "games" / gname / "strings" / "it.json"
                        if not lang_p.exists():
                            lang_p = self.base_path / "games" / gname / "strings" / "en.json"
                    
                    if lang_p.exists():
                        lang_data = _load_json(lang_p)
                        return lang_data.get(key, gname)
                    return gname
            elif mode == "level":
                lvl = self.gs_cur_levels[idx]
                key = lvl.get("cfg", {}).get("name_key")
                # Usa lang_data se caricato (gioco corrente), altrimenti fallback logico
                return self.lang_manager.get(key, lvl["id"])
            elif mode == "scene":
                scn_path = self.gs_cur_scenes[idx]
                from editor.core.io import _load_scene_data
                sd = _load_scene_data(scn_path)
                key = sd.get("name_key")
                return self.lang_manager.get(key, scn_path.name)
        except Exception as e:
            logging.debug(f"[GS] Errore recupero human name ({mode}, {idx}): {e}")
        return "?"

    def _gs_get_string_for_lang(self, game_id: str, lang: str, key: str, fallback: str) -> str:
        """Recupera una stringa per lingua con cache in memoria (invalidata su scrittura)."""
        cache_key = (game_id, lang)
        cache = getattr(self, "_strings_file_cache", None)
        if cache is None:
            self._strings_file_cache = {}
            cache = self._strings_file_cache
        if cache_key not in cache:
            p = self.base_path / "games" / game_id / "strings" / f"{lang}.json"
            cache[cache_key] = _load_json(p) if p.exists() else {}
        return cache[cache_key].get(key, fallback)

    def _gs_edit_game(self, idx: int):
        self._gs_edit_mode = "game"
        self.gs_sel_game   = idx
        
        gname = self.gs_games[idx]
        p = self.base_path / "games" / gname / "game_config.json"
        t_key = "game_title"
        if p.exists():
            cfg = _load_json(p)
            t_key = cfg.get("title_key", "game_title")
            
        self._gs_edit_lang_bufs = {l: self._gs_get_string_for_lang(gname, l, t_key, gname) for l in self.LANGS}
        self._gs_edit_cursors = {l: len(buf) for l, buf in self._gs_edit_lang_bufs.items()}
        self._gs_edit_active_field = self.LANGS[0]
        self._gs_edit_all_selected = False # Per Ctrl+A
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
        self._gs_edit_del_stage = 0
        
        self._gs_edit_bg_path = ""
        self._gs_edit_vid_path = ""
        self._gs_edit_bg_preview_surf = None
        self._gs_edit_vid_preview_surf = None
        self._gs_edit_music_paths = []
        self._gs_edit_theme_id = "default"
        self._gs_edit_magnifier = False
        self._gs_edit_category = "desktop"

        # Carica musica, background e tema esistente se presenti
        if p.exists():
            cfg = _load_json(p)
            bg = cfg.get("menu", {}).get("background", "")
            if bg:
                full_p = str(self.base_path / "games" / gname / bg)
                if bg.lower().endswith((".mp4", ".mov", ".mkv")):
                    self._gs_edit_vid_path = full_p
                else:
                    self._gs_edit_bg_path = full_p

            music = cfg.get("menu", {}).get("music", [])
            if isinstance(music, str): music = [music]
            self._gs_edit_music_paths = music
            self._gs_edit_theme_id = cfg.get("ui_theme", "default")
            self._gs_edit_category = cfg.get("category", "desktop")
            # Carica impostazioni extra dal tema locale
            theme_p = self.base_path / "games" / gname / "ui_theme" / "theme.json"
            if theme_p.exists():
                try:
                    import json
                    with open(theme_p, "r", encoding="utf-8") as tf:
                        t_data = json.load(tf)
                        self._gs_edit_magnifier = t_data.get("effects", {}).get("magnifier_fx", False)
                except Exception: pass
            self._gs_update_previews("edit")

    def _gs_edit_level(self, idx: int):
        if self.gs_sel_game is None: return
        self._gs_edit_mode = "level"
        self.gs_sel_level  = idx
        
        gname = self.gs_games[self.gs_sel_game]
        lvl = self.gs_cur_levels[idx]
        cfg = lvl.get("cfg", {})
        nk = cfg.get("name_key", f"{lvl['id']}_name")
        
        self._gs_edit_lang_bufs = {l: self._gs_get_string_for_lang(gname, l, nk, lvl["id"]) for l in self.LANGS}
        self._gs_edit_cursors = {l: len(buf) for l, buf in self._gs_edit_lang_bufs.items()}
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_all_selected = False
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
        self._gs_edit_del_stage = 0

        self._gs_edit_bg_path = ""
        self._gs_edit_vid_path = ""
        self._gs_edit_bg_preview_surf = None
        self._gs_edit_vid_preview_surf = None

    def _gs_edit_scene(self, idx: int):
        if self.gs_sel_level is None: return
        self._gs_edit_mode = "scene"
        self.gs_sel_scene  = idx
        
        scn_path = self.gs_cur_scenes[idx]
        sd = _load_scene_data(scn_path)
        nk = sd.get("name_key", f"{scn_path.name}_name")
        gname = self.gs_games[self.gs_sel_game]

        self._gs_edit_lang_bufs = {l: self._gs_get_string_for_lang(gname, l, nk, scn_path.name) for l in self.LANGS}
        self._gs_edit_cursors = {l: len(buf) for l, buf in self._gs_edit_lang_bufs.items()}
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_all_selected = False
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
        self._gs_edit_del_stage = 0
        
        bg = sd.get("background", "")
        self._gs_edit_bg_path = ""
        self._gs_edit_vid_path = ""
        if bg:
            full_p = str(scn_path / bg)
            if bg.lower().endswith((".mp4", ".mov", ".mkv")):
                self._gs_edit_vid_path = full_p
            else:
                self._gs_edit_bg_path = full_p
        self._gs_update_previews("edit")

    def _gs_confirm_edit(self):
        def _perform():
            # ... esistente logica ... (contenuto originale del metodo spostato qui)
            self._gs_confirm_edit_logic()
        self._with_loading(_perform)

    def _gs_confirm_edit_logic(self):
        """Conferma e persiste le modifiche dal dialog di editing (ID, Titolo, Assets)."""
        import shutil, tempfile, gc, configparser
        from pathlib import Path
        
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception: pass
        
        raw_name = self._gs_edit_buf.strip()
        if not raw_name:
            self._gs_edit_mode = None; return

        clean_id = re.sub(r'[^\w\-]', '_', raw_name.replace(" ", "_"))

        try:
            # Sincronizzazione Path Editor
            def sync_editor_state(old_p: Path, new_p: Path):
                if getattr(self, "game_path", None) and (self.game_path == old_p or old_p in self.game_path.parents):
                    rel = self.game_path.relative_to(old_p)
                    self.game_path = new_p / rel
                    self.game_name = self.game_path.name
                if getattr(self, "scene_path", None) and (self.scene_path == old_p or old_p in self.scene_path.parents):
                    rel = self.scene_path.relative_to(old_p)
                    self.scene_path = new_p / rel
                    if self.scene_path.exists():
                        self.scene_data["id"] = self.scene_path.name

            # --- BLOCCO GIOCO ---
            if self._gs_edit_mode == "game":
                old_id = self.gs_games[self.gs_sel_game]
                old_p  = self.base_path / "games" / old_id
                new_p  = self.base_path / "games" / clean_id

                if old_id != clean_id:
                    if new_p.exists():
                        err_msg = self.lang_manager.get("gs_error_game_exists", f"Errore: '{clean_id}' gia' in uso")
                        self._status(err_msg, ERR_C, 4); return
                    try:
                        self._img_cache.clear()
                        gc.collect()
                        old_p.rename(new_p)
                    except OSError as e:
                        # Rename atomic fallito (es. cross-device, lock): fallback
                        # copia + rimozione sorgente. La rimozione passa per
                        # safe_delete (cestino), così se la copia ha avuto
                        # problemi il vecchio resta recuperabile.
                        logger.warning(f"Rename fallito ({e}), fallback copytree+delete")
                        shutil.copytree(old_p, new_p, dirs_exist_ok=True)
                        from engine.utils import safe_delete
                        safe_delete(old_p, reason="game_rename_fallback")
                    
                    self.gs_games[self.gs_sel_game] = clean_id
                    sync_editor_state(old_p, new_p)
                    self.gs_cur_levels = _discover_levels(new_p)
                    self.gs_sel_level = self.gs_sel_scene = None
                    self.gs_cur_scenes = []
                    self._gs_refresh_cache()

                c_ini_p = self.base_path / "config.ini"
                if c_ini_p.exists():
                    c_ini = configparser.ConfigParser()
                    c_ini.read(c_ini_p, encoding="utf-8")
                    if c_ini.get("engine", "default_game", fallback="") == old_id:
                        c_ini.set("engine", "default_game", clean_id)
                        with open(c_ini_p, "w", encoding="utf-8") as f: c_ini.write(f)

                cfg_p = new_p / "game_config.json"
                cfg = _load_json(cfg_p)
                cfg["id"] = cfg["game_id"] = clean_id
                cfg["category"] = getattr(self, "_gs_edit_category", "desktop")
                t_key = cfg.setdefault("title_key", "game_title")

                # Background
                bg_path = getattr(self, "_gs_edit_bg_path", "")
                vid_path = getattr(self, "_gs_edit_vid_path", "")
                sel_bg = vid_path if vid_path else bg_path
                
                old_bg = cfg.get("menu", {}).get("background", "")
                if sel_bg:
                    if Path(sel_bg).is_absolute():
                        p = Path(sel_bg); t_name = p.name
                        dst = new_p / "assets" / t_name
                        (new_p / "assets").mkdir(parents=True, exist_ok=True)
                        
                        # Pulizia vecchio background fisico se diverso (IMG <-> VID)
                        if old_bg and old_bg.startswith("assets/"):
                            old_path = (new_p / old_bg).resolve()
                            new_path = dst.resolve()
                            
                            if old_path.exists() and old_path != new_path:
                                try:
                                    logger.info(f"Pulizia asset obsoleto: {old_path}")
                                    old_path.unlink(missing_ok=True)
                                except Exception as e:
                                    logger.error(f"Errore rimozione asset {old_path.name}: {e}")

                        if not dst.exists() or p.resolve() != dst.resolve():
                            shutil.copy2(str(p), str(dst))
                        cfg["menu"]["background"] = f"assets/{t_name}"
                    else: cfg["menu"]["background"] = sel_bg
                else: 
                    # Pulizia se rimosso
                    if old_bg and old_bg.startswith("assets/"):
                        old_p_del = (new_p / old_bg).resolve()
                        if old_p_del.exists():
                            try:
                                logger.info(f"Rimozione asset background rimosso: {old_p_del}")
                                old_p_del.unlink(missing_ok=True)
                            except Exception: pass
                    cfg["menu"]["background"] = ""

                # Musica
                mu_paths = getattr(self, "_gs_edit_music_paths", [])
                music_list = []
                if mu_paths:
                    target_dir = new_p / "audio" / "music"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copiamo in cartella temp per evitare conflitti
                    temp_d = Path(tempfile.mkdtemp())
                    staged = []
                    for i, m_p in enumerate(mu_paths):
                        p = Path(m_p)
                        src = p if p.is_absolute() else (new_p / p)
                        if not src.exists(): continue

                        t_name = p.name
                        
                        # Se già presente in audio/music, non sovrascrivere
                        final_dst = target_dir / t_name
                        if final_dst.exists():
                            music_list.append(f"audio/music/{t_name}")
                            continue
                        
                        final_name = t_name
                        c = 1
                        while (temp_d / final_name).exists():
                            final_name = f"{p.stem}_{c}{p.suffix}"; c += 1
                        
                        try:
                            shutil.copy2(str(src), str(temp_d / final_name))
                            staged.append((temp_d / final_name, final_name))
                        except Exception as e:
                            logger.error(f"Errore copia {src} in temp: {e}")

                    # Spostiamo i nuovi file nella cartella audio/music final
                    for st, fname in staged:
                        dst = target_dir / fname
                        try:
                            if not dst.exists():
                                shutil.move(str(st), str(dst))
                            music_list.append(f"audio/music/{fname}")
                        except Exception as e:
                            logger.error(f"Errore spostamento {fname} in audio/music: {e}")
                    
                    try: shutil.rmtree(temp_d)
                    except Exception: pass
                cfg["menu"]["music"] = music_list
                cfg["ui_theme"] = getattr(self, "_gs_edit_theme_id", "default")
                _save_json(cfg_p, cfg)
                # Harvesting tema: copia asset dal pool engine al gioco
                self._gs_harvest_theme(clean_id, cfg["ui_theme"])
                # Aggiorna impostazioni extra nel tema harvestato
                theme_p = new_p / "ui_theme" / "theme.json"
                if theme_p.exists():
                    try:
                        import json
                        with open(theme_p, "r", encoding="utf-8") as tf:
                            t_data = json.load(tf)
                        if "effects" not in t_data: t_data["effects"] = {}
                        t_data["effects"]["magnifier_fx"] = getattr(self, "_gs_edit_magnifier", False)
                        with open(theme_p, "w", encoding="utf-8") as tf:
                            json.dump(t_data, tf, indent=4)
                        logger.info(f"[THEME] Salvato magnifier_fx={t_data['effects']['magnifier_fx']}")
                    except Exception as e:
                        logger.error(f"Errore salvataggio extra theme: {e}")

                # --- PULIZIA AUTOMATICA FILE MUSICA NON USATI (Richiesta User) ---
                used_in_scenes = self._gs_get_used_music(new_p)
                menu_music = {Path(m).name for m in music_list}
                all_active_music = used_in_scenes.union(menu_music)
                
                audio_dir = new_p / "audio" / "music"
                if audio_dir.exists():
                    from engine.utils import safe_delete
                    for f in audio_dir.glob("*.mp3"):
                        if f.name not in all_active_music:
                            logger.info(f"Pulizia musica inutilizzata: {f.name}")
                            if not safe_delete(f, reason="game_save_unused_music"):
                                logger.error(f"Errore eliminazione file inutilizzato {f.name}")
                for l, val in getattr(self, "_gs_edit_lang_bufs", {}).items():
                    self._gs_update_strings(clean_id, {t_key: val}, lang=l)
                
                for it in self.recent_scenes:
                    if it.get("game") == old_id:
                        it["game"] = clean_id
                        it["path"] = it["path"].replace(str(old_p), str(new_p))
                self._save_editor_setting("recent_scenes", self.recent_scenes)

            # --- BLOCCO LIVELLO ---
            elif self._gs_edit_mode == "level":
                gname = self.gs_games[self.gs_sel_game]
                lvl   = self.gs_cur_levels[self.gs_sel_level]
                cfg_p = lvl["path"] / "level_config.json"
                cfg = _load_json(cfg_p)
                nk = cfg.setdefault("name_key", f"{lvl['id']}_name")
                _save_json(cfg_p, cfg)
                for l, val in getattr(self, "_gs_edit_lang_bufs", {}).items():
                    self._gs_update_strings(gname, {nk: val}, lang=l)

            # --- BLOCCO SCENA ---
            elif self._gs_edit_mode == "scene":
                gname = self.gs_games[self.gs_sel_game]
                scn_p = self.gs_cur_scenes[self.gs_sel_scene]
                sd = _load_scene_data(scn_p)
                nk = sd.setdefault("name_key", f"{scn_p.name}_name")
                
                bg_p = getattr(self, "_gs_edit_bg_path", "")
                vid_p = getattr(self, "_gs_edit_vid_path", "")
                sel_s = vid_p if vid_p else bg_p
                
                old_s = sd.get("background", "")
                if sel_s:
                    if Path(sel_s).is_absolute():
                        p = Path(sel_s); dst = scn_p / p.name
                        
                        # Pulizia vecchia risorsa scena (IMG <-> VID).
                        # Soft-delete: il vecchio background va nel cestino, recuperabile.
                        if old_s and old_s != p.name:
                            old_p_del = (scn_p / old_s).resolve()
                            new_p_check = dst.resolve()

                            if old_p_del.exists() and old_p_del != new_p_check:
                                from engine.utils import safe_delete
                                logger.info(f"Pulizia asset scena: {old_p_del}")
                                safe_delete(old_p_del, reason="scene_bg_replaced")

                        if not dst.exists() or p.resolve() != dst.resolve():
                            shutil.copy2(str(p), str(dst))
                        sd["background"] = p.name
                    else: sd["background"] = Path(sel_s).name
                else: 
                    if old_s:
                        old_p_del = (scn_p / old_s).resolve()
                        if old_p_del.exists():
                            try:
                                logger.info(f"Rimozione asset scena rimosso: {old_p_del}")
                                old_p_del.unlink(missing_ok=True)
                            except Exception: pass
                    sd["background"] = ""
                
                _save_json(scn_p / "scene.json", sd)
                for l, val in getattr(self, "_gs_edit_lang_bufs", {}).items():
                    self._gs_update_strings(gname, {nk: val}, lang=l)

            self._load_strings()
            self._gs_refresh_cache()
            self._status(self._TR("gs_saved_ok", "'{0}' saved").format(raw_name), OK_C, 2)
        except Exception as e:
            logger.exception("Errore aggiornamento")
            self._status(self._TR("gs_save_info_error", "Error saving info"), ERR_C, 4)
        self._gs_edit_mode = None

        self._gs_edit_buf  = ""
        self._gs_edit_bg_path = ""
        self._gs_edit_vid_path = ""


    def _gs_get_used_music(self, game_path: Path) -> set:
        """Scansiona tutti i file scene.json nel progetto per trovare brani musicali in uso."""
        used = set()
        l_dir = game_path / "levels"
        if not l_dir.exists(): return used
        for lvl_p in l_dir.iterdir():
            if not lvl_p.is_dir(): continue
            for scn_p in lvl_p.iterdir():
                if not scn_p.is_dir(): continue
                s_json = scn_p / "scene.json"
                if s_json.exists():
                    try:
                        with open(s_json, "r", encoding="utf-8") as f:
                            sd = json.load(f); m = sd.get("music", [])
                            if isinstance(m, str): used.add(m)
                            elif isinstance(m, list): used.update(m)
                    except Exception: pass
        return used

    def _gs_harvest_theme(self, game_id: str, theme_id: str) -> bool:
        """Harvest a theme: copy engine/assets/themes/<theme_id>/ into
        games/<game_id>/ui_theme/. Returns True when the game ends up with the
        requested theme.

        STAGED swap. The previous version deleted ui_theme/ FIRST and only then
        looked for the source, so a missing theme - or a copy that failed on a
        locked file or a full disk - left the game with NO theme at all and only
        a line in the log. Here the source is validated and copied to a sibling
        staging folder before the old theme is touched, and any failure rolls
        the previous theme back and tells the user.
        """
        import json as _json
        import shutil as _shutil
        from engine.utils import get_resource_path

        # 1. Validate the source BEFORE touching anything in the game.
        src_dir = get_resource_path("engine", "assets", "themes", theme_id)
        src_file = src_dir / "theme.json"
        if not src_dir.is_dir() or not src_file.is_file():
            logger.warning("[THEME] Theme '%s' not found in engine/assets/themes/.", theme_id)
            self._status(self._TR("gs_theme_missing",
                                  "Theme '{0}' not found: the game keeps the current one"
                                  ).format(theme_id), ERR_C, 4)
            return False
        try:
            _json.loads(src_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.error("[THEME] Theme '%s' unreadable: %s", theme_id, e)
            self._status(self._TR("gs_theme_invalid",
                                  "Theme '{0}' is not valid: the game keeps the current one"
                                  ).format(theme_id), ERR_C, 4)
            return False

        game_theme_dir = self.base_path / "games" / game_id / "ui_theme"
        staging = game_theme_dir.with_name("ui_theme.__new__")
        backup = game_theme_dir.with_name("ui_theme.__old__")
        for leftover in (staging, backup):
            if leftover.exists():
                _shutil.rmtree(leftover, ignore_errors=True)

        # 2. Copy into staging, then swap. Only the swap touches the game.
        try:
            game_theme_dir.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copytree(str(src_dir), str(staging))
            if game_theme_dir.exists():
                game_theme_dir.rename(backup)
            staging.rename(game_theme_dir)
        except Exception as e:
            logger.error("[THEME] Harvest of theme '%s' failed: %s", theme_id, e)
            _shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not game_theme_dir.exists():
                try:
                    backup.rename(game_theme_dir)   # rollback: keep the old theme
                except OSError as re:
                    logger.error("[THEME] Rollback of the previous theme failed: %s", re)
            self._status(self._TR("gs_theme_failed",
                                  "Theme '{0}' not applied: {1}"
                                  ).format(theme_id, e), ERR_C, 5)
            return False
        finally:
            _shutil.rmtree(backup, ignore_errors=True)

        logger.info("[THEME] Theme '%s' harvested into '%s/ui_theme/'", theme_id, game_id)
        self._status(self._TR("gs_theme_applied", "Theme '{0}' applied to the game").format(theme_id), OK_C, 2)
        return True

    def _gs_update_strings(self, game_id: str, new_data: dict, remove_keys: list = None, lang: str = None):
        """Aggiorna traduzioni, invalida la cache in memoria e sincronizza il lang_manager."""
        s_dir = self.base_path / "games" / game_id / "strings"
        if not s_dir.exists():
            s_dir.mkdir(parents=True, exist_ok=True)

        if lang:
            target_files = [s_dir / f"{lang}.json"]
        else:
            target_files = list(s_dir.glob("*.json"))
            if not target_files:
                target_files = [s_dir / f"{l}.json" for l in self.LANGS]

        cache = getattr(self, "_strings_file_cache", {})
        for sf in target_files:
            data = _load_json(sf) if sf.exists() else {}
            if remove_keys:
                for k in remove_keys:
                    if k and k in data: del data[k]
            data.update(new_data)
            _save_json(sf, data)
            # Invalida la cache per questo file così la prossima lettura è fresca
            cache.pop((game_id, sf.stem), None)
        self._strings_file_cache = cache

        # Se il gioco aggiornato è quello correntemente aperto, ricarica subito
        # il lang_manager in memoria — i chiamanti non devono farlo manualmente
        cur_game = getattr(self, "game_path", None)
        if cur_game and cur_game.name == game_id and hasattr(self, "_load_strings"):
            try:
                self._load_strings()
            except Exception:
                pass


    def _gs_update_previews(self, mode="edit"):
        """Carica le superfici di anteprima per gli asset selezionati."""
        p_prefix = "_gs_edit_" if mode == "edit" else "_gs_new_"
        
        # BG Image Preview
        bg_path = getattr(self, f"{p_prefix}bg_path", "")
        setattr(self, f"{p_prefix}bg_preview_surf", None)
        if bg_path:
            try:
                s = pygame.image.load(bg_path).convert()
                s = pygame.transform.smoothscale(s, (200, 112))
                setattr(self, f"{p_prefix}bg_preview_surf", s)
            except Exception: pass
            
        # Video Preview (carica thumbnail .jpg se esiste)
        vid_path = getattr(self, f"{p_prefix}vid_path", "")
        setattr(self, f"{p_prefix}vid_preview_surf", None)
        if vid_path:
            p = Path(vid_path)
            # Cerca immagine associata per thumbnail
            found = False
            for ext in (".jpg", ".png", ".jpeg"):
                thumb_p = p.with_suffix(ext)
                if thumb_p.exists():
                    try:
                        s = pygame.image.load(str(thumb_p)).convert()
                        s = pygame.transform.smoothscale(s, (200, 112))
                        setattr(self, f"{p_prefix}vid_preview_surf", s)
                        found = True
                        break
                    except Exception: pass
            
            # Fallback: OpenCV frame capture
            if not found and p.exists():
                try:
                    import cv2
                    import numpy as np
                    cap = cv2.VideoCapture(str(p))
                    ret, frame = cap.read()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame = np.transpose(frame, (1, 0, 2))
                        surf = pygame.surfarray.make_surface(frame)
                        s = pygame.transform.smoothscale(surf, (200, 112))
                        setattr(self, f"{p_prefix}vid_preview_surf", s)
                    cap.release()
                except Exception: pass

    def _gs_confirm_new(self):
        def _perform():
            self._gs_confirm_new_logic()
        self._with_loading(_perform)

    def _gs_confirm_new_logic(self):
        # Rilascia audio per evitare WinError 32 su Windows
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception: pass
        
        name = re.sub(r'[^\w\-]', '_', self._gs_new_buf.strip().replace(" ", "_"))
        if not name:
            self._gs_new_mode = None; return

        if self._gs_new_mode == "game":
            gpath = self.base_path / "games" / name
            if gpath.exists():
                err_msg = self.lang_manager.get("gs_error_game_exists", "Errore: Un progetto con questo nome esiste gia'!")
                self._status(err_msg, ERR_C, 4); return
            gpath.mkdir(parents=True, exist_ok=False)
            (gpath / "objects").mkdir(exist_ok=True)
            (gpath / "strings").mkdir(exist_ok=True)
            (gpath / "audio").mkdir(exist_ok=True)
            (gpath / "levels").mkdir(exist_ok=True)
            (gpath / "assets").mkdir(exist_ok=True)

            # --- GESTIONE BACKGROUND SCELTO ---
            import shutil
            bg_path = getattr(self, "_gs_new_bg_path", "")
            vid_path = getattr(self, "_gs_new_vid_path", "")
            final_bg_path = ""

            if vid_path and Path(vid_path).exists():
                p = Path(vid_path)
                target_name = p.name
                target_path = gpath / "assets" / target_name
                try:
                    shutil.copy2(vid_path, target_path)
                    final_bg_path = f"assets/{target_name}"
                except Exception as e:
                    self._status(self._TR("gs_copy_video_error", "Video copy error: {0}").format(e), ERR_C)
            elif bg_path and Path(bg_path).exists():
                p = Path(bg_path)
                target_name = f"menu_bg{p.suffix}"
                target_path = gpath / "assets" / target_name
                try:
                    shutil.copy2(bg_path, target_path)
                    final_bg_path = f"assets/{target_name}"
                except Exception as e:
                    self._status(self._TR("gs_copy_asset_error", "Asset copy error: {0}").format(e), ERR_C)
            
            # --- GESTIONE PLAYLIST MUSICA ---
            music_list = []
            if hasattr(self, "_gs_new_music_paths") and self._gs_new_music_paths:
                target_dir = gpath / "audio" / "music"
                target_dir.mkdir(parents=True, exist_ok=True)
                for i, m_path in enumerate(self._gs_new_music_paths):
                    p = Path(m_path)
                    t_name = p.name
                    target_path = target_dir / t_name
                    
                    # Se esiste già, non sovrascrivere
                    if target_path.exists():
                        music_list.append(f"audio/music/{t_name}")
                        continue
                    
                    # Collision handling
                    c = 1
                    while target_path.exists():
                        t_name = f"{p.stem}_{c}{p.suffix}"
                        target_path = target_dir / t_name
                        c += 1
                        
                    try:
                        logger.info(f"Copia nuovo brano menu: {m_path} -> {target_path}")
                        shutil.copy2(str(m_path), str(target_path))
                        music_list.append(f"audio/music/{t_name}")
                    except Exception as e:
                        logger.error(f"Errore copia brano {m_path}: {e}")

            # --- PULIZIA AUTOMATICA FILE MUSICA NON USATI (Nuovo Progetto) ---
            used_in_scenes = self._gs_get_used_music(gpath)
            menu_music = {Path(m).name for m in music_list}
            all_active_music = used_in_scenes.union(menu_music)
            audio_dir = gpath / "audio" / "music"
            if audio_dir.exists():
                for f in audio_dir.glob("*.mp3"):
                    if f.name not in all_active_music:
                        try: f.unlink()
                        except Exception: pass

            _save_json(gpath / "game_config.json",
                       {
                           "id": name,
                           "game_id": name, # Compatibilità
                           "title_key": "game_title",
                           "version": "1.0",
                           "ui_theme": "default",
                           "category": getattr(self, "_gs_new_category", "desktop"),
                           "levels": [],
                           "menu": {
                               "background": final_bg_path,
                               "music": music_list
                           }
                       })
            # Harvesting tema default al nuovo progetto
            self._gs_harvest_theme(name, "default")
            
            _save_json(gpath / "objects_catalog.json", {"objects": []})
            
            # --- SEEDING INIZIALE TRADUZIONI (Harvesting di Sistema) ---
            from engine.utils import get_resource_path
            
            # Chiavi HUD/SISTEMA minime necessarie per distribuire il gioco
            sys_keys = {
                "btn_back", "btn_resume", "btn_settings", "btn_quit_to_main", "btn_play", "btn_ok", "btn_cancel",
                "hud_time", "hud_score", "hud_found", "hud_hint_seek", "hud_remaining_status",
                "label_language", "label_resolution", "label_fullscreen", "mode_window",
                "label_music_volume", "label_sfx_volume", "label_master_volume",
                "mg_title", "mg_description", "pause_title", "mission_complete"
            }
            
            # Rileviamo lingue disponibili nell'engine
            engine_strings_dir = get_resource_path("engine", "assets", "strings")
            langs = [f.stem for f in engine_strings_dir.glob("*.json")] if engine_strings_dir.exists() else ["en", "it"]
            
            for lang in langs:
                # Carica traduzioni globali dall'engine
                eng_p = engine_strings_dir / f"{lang}.json"
                eng_data = {}
                if eng_p.exists():
                    try:
                        with open(eng_p, "r", encoding="utf-8-sig") as f:
                            eng_data = json.load(f)
                    except Exception: pass
                
                # Crea il pool locale del gioco per questa lingua
                local_data = {"game_title": name.replace("_", " ")}
                
                # Harvesting: inserisce le chiavi di sistema ufficiali
                for sk in sys_keys:
                    if sk in eng_data:
                        local_data[sk] = eng_data[sk]
                    else:
                        # Fallback se manca nell'engine (molto raro)
                        local_data[sk] = sk.replace("btn_", "").replace("hud_", "").replace("label_", "").replace("_", " ").title()
                
                # Salva il file i18n del gioco
                _save_json(gpath / "strings" / f"{lang}.json", local_data)
            
            logger.info(f"[PROJECT] Creati file i18n per {len(langs)} lingue con seed di sistema.")
            
            # --- CREAZIONE ENTRY POINT DINAMICO (main.py specifico per gioco) ---
            main_py_content = f"""import sys
import importlib.util
from pathlib import Path

# Trova la root del motore (2 livelli sopra)
root = Path(__file__).resolve().parents[2]
engine_main_p = root / "main.py"

if __name__ == "__main__":
    if not engine_main_p.exists():
        print(f"ERRORE: Motore non trovato in {{engine_main_p}}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("engine_entry", engine_main_p)
    engine_module = importlib.util.module_from_spec(spec)
    
    # IMPORTANTE: Aggiunge la root al path per le dipendenze del motore (es. engine.utils)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
        
    spec.loader.exec_module(engine_module)

    # Forza il gioco da caricare basandosi sul nome di questa cartella
    game_id = Path(__file__).parent.name
    print(f"[LAUNCHER] Avvio progetto: {{game_id}}")
    
    # Override degli argomenti CLI
    sys.argv = [sys.argv[0], "--game", game_id]
    
    # Avvia l'engine
    engine_module.main()
"""
            with open(gpath / "main.py", "w", encoding="utf-8") as f:
                f.write(main_py_content)
            
            # Batch per comodità su Windows
            with open(gpath / "run.bat", "w", encoding="utf-8") as f:
                f.write(f"@echo off\ncd /d \"%~dp0\"\npython main.py\npause")

            self.gs_games = _discover_games(self.base_path)
            idx = next((i for i, g in enumerate(self.gs_games) if g == name), 0)
            self._gs_select_game(idx)

        elif self._gs_new_mode == "level":
            gname = self.gs_games[self.gs_sel_game]
            lpath = self.base_path / "games" / gname / "levels" / name
            if lpath.exists():
                self._status(self._TR("gs_level_exists", "Error: level '{0}' already exists").format(name), ERR_C, 4); return
            lpath.mkdir(parents=True, exist_ok=False)
            _save_json(lpath / "level_config.json",
                       {"id": name, "name_key": f"{name}_name",
                        "difficulty": "normal", "timer_behavior": "complete",
                        "scenes": []})

            # Registra il nuovo livello in game_config.json (sempre in coda)
            g_cfg_p = self.base_path / "games" / gname / "game_config.json"
            g_cfg = _load_json(g_cfg_p)
            levels_list = g_cfg.get("levels", [])
            # Prima registra eventuali directory orfane (non nel config) così
            # il nuovo livello risulta sempre l'ultimo in assoluto
            ldir = self.base_path / "games" / gname / "levels"
            if ldir.exists():
                orphan_ids = sorted(
                    d.name for d in ldir.iterdir()
                    if d.is_dir() and d.name not in levels_list and d.name != name
                )
                for oid in orphan_ids:
                    levels_list.append(oid)
                    logger.info(f"Livello orfano '{oid}' registrato in game_config.json prima del nuovo livello")
            # Rimuovi se esiste già (per evitare duplicati)
            if name in levels_list:
                levels_list.remove(name)
            # Aggiungi in coda (sempre alla fine)
            levels_list.append(name)
            g_cfg["levels"] = levels_list
            _save_json(g_cfg_p, g_cfg)
            logger.info(f"Nuovo livello '{name}' registrato in game_config.json (posizione: {len(levels_list)})")

            # Salva le traduzioni del nome livello nei file strings/{lang}.json
            _name_key  = f"{name}_name"
            _lang_bufs = getattr(self, "_gs_new_lang_bufs", {})
            for _l in self.LANGS:
                _val = (_lang_bufs.get(_l) or "").strip() or name
                self._gs_update_strings(gname, {_name_key: _val}, lang=_l)

            self._gs_select_game(self.gs_sel_game)
            idx = next((i for i, l in enumerate(self.gs_cur_levels) if l["id"] == name), len(self.gs_cur_levels) - 1)
            self._gs_select_level(idx)

        elif self._gs_new_mode == "scene":
            gname = self.gs_games[self.gs_sel_game]
            lvl   = self.gs_cur_levels[self.gs_sel_level]
            spath = lvl["path"] / name
            if spath.exists():
                self._status(self._TR("gs_scene_exists", "Error: scene '{0}' already exists").format(name), ERR_C, 4); return
            spath.mkdir(parents=True, exist_ok=False)
            
            import shutil
            bg_p = getattr(self, "_gs_new_bg_path", "")
            vid_p = getattr(self, "_gs_new_vid_path", "")
            sel_p = vid_p if vid_p else bg_p
            
            bg_name = "background.jpg"
            if sel_p and Path(sel_p).exists():
                p = Path(sel_p)
                bg_name = p.name
                try:
                    shutil.copy2(sel_p, spath / bg_name)
                except Exception as e:
                    self._status(self._TR("gs_copy_scene_asset_error", "Scene asset copy error: {0}").format(e), ERR_C)

            _save_json(spath / "scene.json",
                       {"id": name, "background": bg_name,
                        "background_scale": 1.0, "objects": []})
            
            # --- AGGIORNAMENTO level_config.json (Critico per la visibilità nel motore) ---
            l_cfg_p = lvl["path"] / "level_config.json"
            if l_cfg_p.exists():
                l_cfg = _load_json(l_cfg_p)
                scenes_list = l_cfg.get("scenes", [])
                # Aggiungiamo solo se non esiste già
                if not any(s.get("id") == name for s in scenes_list):
                    scenes_list.append({
                        "id": name,
                        "order": len(scenes_list) + 1,
                        "time_limit": 120,
                        "transition_out": "fade"
                    })
                    l_cfg["scenes"] = scenes_list
                    _save_json(l_cfg_p, l_cfg)
                    logger.info(f"Registrata nuova scena '{name}' in level_config.json")

            # Refresh della cache dei livelli per includere la nuova cartella scena
            self.gs_cur_levels = _discover_levels(self.game_path)
            self._gs_select_level(self.gs_sel_level)
            
            # Trova l'indice della nuova scena nella lista aggiornata
            idx = 0
            for i, s_p in enumerate(self.gs_cur_scenes):
                if s_p.name == name:
                    idx = i; break
            self._gs_select_scene(idx)

        self._gs_new_mode = None
        self._gs_new_buf  = ""

    # ─────────────────────────────────────────────────────────────────────────
    # ELIMINAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_del_game(self, idx: int):
        """Prepara il dialog di conferma eliminazione gioco."""
        if idx is None or idx >= len(self.gs_games):
            return
        gname = self.gs_games[idx]
        self._gs_del_mode = "game"
        self._gs_del_path = self.base_path / "games" / gname
        self._gs_del_name = gname
        self.gs_sel_game = idx
        self._gs_del_stage = 0

    def _gs_del_level(self, idx: int):
        """Prepara il dialog di conferma eliminazione livello."""
        if self.gs_sel_game is None or idx >= len(self.gs_cur_levels):
            return
        lvl = self.gs_cur_levels[idx]
        self._gs_del_mode = "level"
        self._gs_del_path = lvl["path"]
        self._gs_del_name = lvl["id"]
        self.gs_sel_level = idx

    def _gs_del_scene(self, idx: int):
        """Prepara il dialog di conferma eliminazione scena."""
        if self.gs_sel_level is None or idx >= len(self.gs_cur_scenes):
            return
        self._gs_del_mode = "scene"
        self._gs_del_path = self.gs_cur_scenes[idx]
        self._gs_del_name = self.gs_cur_scenes[idx].name
        self.gs_sel_scene = idx

    def _gs_confirm_delete(self):
        """Esegue l'eliminazione dopo la conferma dell'utente."""
        if not self._gs_del_path:
            self._gs_del_mode = None
            return
        
        # TRIPLA conferma per i GIOCHI
        if self._gs_del_mode == "game":
            stage = getattr(self, "_gs_del_stage", 0)
            if stage < 2:
                self._gs_del_stage = stage + 1
                return
        
        try:
            p = Path(self._gs_del_path)

            # Leggi la name_key PRIMA di rimuovere la directory, per poter
            # ripulire le chiavi orfane nei file strings/*.json
            _del_name_key = None
            _del_gname    = None
            if self._gs_del_mode in ("level", "scene") and self.gs_sel_game is not None:
                _del_gname = self.gs_games[self.gs_sel_game]
                cfg_file   = "level_config.json" if self._gs_del_mode == "level" else "scene.json"
                p_cfg      = p / cfg_file
                if p_cfg.exists():
                    _del_name_key = _load_json(p_cfg).get("name_key")

            if p.is_dir():
                # Soft-delete: sposta l'INTERA cartella (gioco/livello/scena)
                # in .editor_trash/<sessione>/. Pienamente recuperabile.
                # Tracciato in .editor_audit.log con tag esplicito sull'oggetto eliminato.
                from engine.utils import safe_delete
                if not safe_delete(p, reason=f"user_delete_{self._gs_del_mode}={self._gs_del_name}"):
                    self._status(self._TR("gs_delete_error", "Delete error: {0}").format(self._gs_del_name), ERR_C, 4)
                    return
            self._status(self._TR("gs_deleted_trash", "Deleted: {0} (recoverable from the trash)").format(self._gs_del_name), WARN_C, 4)

            # Rimuovi le chiavi traduzione orfane da tutti i file strings/
            if _del_gname and _del_name_key:
                self._gs_update_strings(_del_gname, {}, remove_keys=[_del_name_key])
                logger.info(f"Chiave traduzione '{_del_name_key}' rimossa dai file strings/ di '{_del_gname}'.")

            if self._gs_del_mode == "level":
                # Pulisce i progetti recenti che contengono questo livello
                lp = str(self._gs_del_path)
                self.recent_scenes = [r for r in self.recent_scenes if lp not in r.get("path", "")]
                self._save_editor_setting("recent_scenes", self.recent_scenes)

                # RIMOZIONE LOGICA DA game_config.json
                if self.gs_sel_game is not None:
                    gname = self.gs_games[self.gs_sel_game]
                    g_cfg_p = self.base_path / "games" / gname / "game_config.json"
                    if g_cfg_p.exists():
                        try:
                            g_cfg = _load_json(g_cfg_p)
                            levels_list = g_cfg.get("levels", [])
                            if self._gs_del_name in levels_list:
                                levels_list.remove(self._gs_del_name)
                                g_cfg["levels"] = levels_list
                                _save_json(g_cfg_p, g_cfg)
                                logger.info(f"Sincronizzazione game_config: Livello '{self._gs_del_name}' rimosso.")
                        except Exception as e:
                            logger.error(f"Errore sincronizzazione game_config: {e}")

                self._gs_select_game(self.gs_sel_game)
                self.gs_sel_level  = None
                self.gs_cur_scenes = []
                self.gs_sel_scene  = None
            elif self._gs_del_mode == "scene":
                # 1. Pulisce questa specifica scena dai recenti
                sp = str(self._gs_del_path)
                self.recent_scenes = [r for r in self.recent_scenes if r.get("path") != sp]
                self._save_editor_setting("recent_scenes", self.recent_scenes)

                # 2. RIMOZIONE LOGICA DA level_config.json (Fix Critico)
                if self.gs_sel_level is not None:
                    lvl_path = self.gs_cur_levels[self.gs_sel_level]["path"]
                    l_cfg_p = lvl_path / "level_config.json"
                    
                    if l_cfg_p.exists():
                        try:
                            l_cfg = _load_json(l_cfg_p)
                            old_scenes = l_cfg.get("scenes", [])
                            # Filtra via la scena eliminata
                            new_scenes = [s for s in old_scenes if s.get("id") != self._gs_del_name]
                            
                            # Riordina le scene rimanenti
                            for i, s in enumerate(new_scenes):
                                s["order"] = i + 1
                            
                            l_cfg["scenes"] = new_scenes
                            _save_json(l_cfg_p, l_cfg)
                            logger.info(f"Sincronizzazione level_config: Scena '{self._gs_del_name}' rimossa.")
                        except Exception as e:
                            logger.error(f"Errore sincronizzazione level_config: {e}")

                    # Refresh dei livelli per aggiornare la lista scene contenuta in essi
                    old_sel_lvl = self.gs_sel_level
                    self._gs_select_game(self.gs_sel_game)
                    self._gs_select_level(old_sel_lvl)
                self.gs_sel_scene = None
            elif self._gs_del_mode == "game":
                # Pulisce i progetti recenti prima di ricaricare tutto
                self.recent_scenes = [r for r in self.recent_scenes if r.get("game") != self._gs_del_name]
                self._save_editor_setting("recent_scenes", self.recent_scenes)

                # Pulisce default_game in config.ini se rimosso
                c_ini_p = self.base_path / "config.ini"
                if c_ini_p.exists():
                    import configparser
                    c_ini = configparser.ConfigParser()
                    c_ini.read(c_ini_p, encoding="utf-8")
                    if c_ini.get("engine", "default_game", fallback="") == self._gs_del_name:
                        c_ini.set("engine", "default_game", "")
                        with open(c_ini_p, "w", encoding="utf-8") as f: c_ini.write(f)

                self.gs_games = _discover_games(self.base_path)
                self.gs_sel_game   = None
                self.gs_cur_levels = []
                self.gs_sel_level  = None
                self.gs_cur_scenes = []
                self.gs_sel_scene  = None
                self._gs_refresh_cache(None)
        except Exception as exc:
            self._status(self._TR("io_error", "Error: {0}").format(exc), ERR_C, 4)
        finally:
            self._gs_del_mode = None
            self._gs_del_path = None
            self._gs_del_name = ""
            self._gs_del_stage = 0

    def _gs_move_level(self, idx: int, delta: int):
        """Sposta un livello su o giù nell'ordine del progetto, aggiornando game_config.json."""
        if self.gs_sel_game is None: return
        
        gname = self.gs_games[self.gs_sel_game]
        g_cfg_p = self.base_path / "games" / gname / "game_config.json"
        g_cfg = _load_json(g_cfg_p)
        
        current_ids = [l["id"] for l in self.gs_cur_levels]
        
        if 0 <= idx + delta < len(current_ids):
            # Swappa i nomi per il salvataggio nel config
            current_ids[idx], current_ids[idx+delta] = current_ids[idx+delta], current_ids[idx]
            
            g_cfg["levels"] = current_ids
            if _save_json(g_cfg_p, g_cfg):
                logger.info(f"Ordine livelli aggiornato per {gname}: {current_ids}")
            
            # Aggiornamento locale degli oggetti senza ricaricare tutto
            self.gs_cur_levels[idx], self.gs_cur_levels[idx+delta] = self.gs_cur_levels[idx+delta], self.gs_cur_levels[idx]
            self._gs_select_level(idx + delta)
            self._gs_refresh_cache(1)

    def _gs_move_scene(self, idx: int, delta: int):
        """Sposta una scena su o giù nell'ordine del livello, aggiornando level_config.json."""
        if self.gs_sel_level is None: return
        lvl = self.gs_cur_levels[self.gs_sel_level]
        l_cfg_p = lvl["path"] / "level_config.json"
        l_cfg = _load_json(l_cfg_p)
        scenes_cfg = l_cfg.get("scenes", [])
        
        # Sincronizziamo la lista config con la lista reale delle cartelle
        current_names = [s.name for s in self.gs_cur_scenes]
        
        if 0 <= idx + delta < len(current_names):
            # Dizionario dati esistenti per ID
            data_map = {s["id"]: s for s in scenes_cfg}
            
            # Swappa i nomi nell'ordine visuale
            name1 = current_names[idx]
            name2 = current_names[idx + delta]
            current_names[idx], current_names[idx+delta] = current_names[idx+delta], current_names[idx]
            
            # Rigenera scenes_cfg
            new_scenes_cfg = []
            for i, name in enumerate(current_names):
                if name in data_map:
                    item = data_map[name]
                    item["order"] = i + 1
                    new_scenes_cfg.append(item)
                else:
                    new_scenes_cfg.append({
                        "id": name, "order": i + 1,
                        "time_limit": 120, "transition_out": "fade"
                    })
            
            l_cfg["scenes"] = new_scenes_cfg
            if _save_json(l_cfg_p, l_cfg):
                logger.info(f"Ordine scene aggiornato per {lvl['id']}: {current_names}")
            
            # Aggiornamento locale senza ricaricare tutto
            self.gs_cur_scenes[idx], self.gs_cur_scenes[idx+delta] = self.gs_cur_scenes[idx+delta], self.gs_cur_scenes[idx]
            self.gs_sel_scene = idx + delta
            self._gs_refresh_cache(2)

    def _gs_move_game(self, idx: int, delta: int):
        """Sposta un gioco su o giu' nell'ordine globale (persistito in .editor_settings.json)."""
        if not (0 <= idx < len(self.gs_games)) or not (0 <= idx + delta < len(self.gs_games)):
            return
        self.gs_games[idx], self.gs_games[idx + delta] = \
            self.gs_games[idx + delta], self.gs_games[idx]
        self._save_editor_setting("games_order", list(self.gs_games))
        # La selezione segue l'elemento spostato senza ricaricare livelli/scene
        if self.gs_sel_game == idx:
            self.gs_sel_game = idx + delta
        elif self.gs_sel_game == idx + delta:
            self.gs_sel_game = idx
        self._gs_refresh_cache(0)
        logger.info(f"Ordine giochi aggiornato: {self.gs_games}")

    # ─────────────────────────────────────────────────────────────────────────
    # DUPLICAZIONE E SPOSTAMENTO
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_unique_copy_name(self, parent: Path, base_name: str) -> str:
        """Genera un nome '<base>_copy' (poi _copy2, _copy3...) libero dentro parent."""
        candidate = f"{base_name}{self._GS_COPY_SUFFIX}"
        n = 2
        while (parent / candidate).exists():
            candidate = f"{base_name}{self._GS_COPY_SUFFIX}{n}"
            n += 1
        return candidate

    def _gs_duplicate_scene(self, idx: int):
        """Duplica la scena selezionata (cartella completa + registrazione config)."""
        if self.gs_sel_level is None or idx is None or idx >= len(self.gs_cur_scenes):
            self._status(self._TR("gs_select_scene_first", "Select a scene first"), WARN_C, 2)
            return
        self._with_loading(self._gs_duplicate_scene_logic, idx)

    def _gs_duplicate_scene_logic(self, idx: int):
        """Copia la cartella scena e la registra in level_config.json dopo l'originale."""
        import shutil
        lvl = self.gs_cur_levels[self.gs_sel_level]
        src = self.gs_cur_scenes[idx]
        new_name = self._gs_unique_copy_name(lvl["path"], src.name)
        dst = lvl["path"] / new_name
        try:
            shutil.copytree(src, dst)
        except Exception as exc:
            self._status(self._TR("gs_dup_scene_error", "Scene duplication error: {0}").format(exc), ERR_C, 4)
            return
        # L'autosave copiato appartiene all'originale: non va ereditato
        autosave = dst / "scene.json.autosave"
        if autosave.exists():
            try:
                autosave.unlink()
            except OSError as exc:
                logger.debug(f"Rimozione autosave copia fallita: {exc}")
        # Aggiorna l'id nello scene.json della copia
        sd = _load_json(dst / "scene.json")
        if sd:
            sd["id"] = new_name
            _save_json(dst / "scene.json", sd)
        # Registrazione in level_config.json subito dopo l'originale.
        # Se l'originale e' orfano (non registrato) lo registriamo prima,
        # cosi' la coppia resta adiacente anche nel config.
        l_cfg_p = lvl["path"] / "level_config.json"
        if l_cfg_p.exists():
            l_cfg = _load_json(l_cfg_p)
            scenes_cfg = l_cfg.get("scenes", [])
            src_entry = next((s for s in scenes_cfg if s.get("id") == src.name), None)
            if src_entry is None:
                src_entry = {"id": src.name, "time_limit": 120, "transition_out": "fade"}
                scenes_cfg.append(src_entry)
                logger.info(f"Scena orfana '{src.name}' registrata in level_config.json")
            new_entry = dict(src_entry)
            new_entry["id"] = new_name
            scenes_cfg.insert(scenes_cfg.index(src_entry) + 1, new_entry)
            for i, s in enumerate(scenes_cfg):
                s["order"] = i + 1
            l_cfg["scenes"] = scenes_cfg
            _save_json(l_cfg_p, l_cfg)
            logger.info(f"Scena duplicata: '{src.name}' -> '{new_name}' (registrata in config)")
        # Refresh liste e selezione sulla copia
        old_sel_lvl = self.gs_sel_level
        self.gs_cur_levels = _discover_levels(self.game_path)
        self._gs_select_level(old_sel_lvl)
        for i, s_p in enumerate(self.gs_cur_scenes):
            if s_p.name == new_name:
                self._gs_select_scene(i)
                break
        self._status(self._TR("gs_scene_duplicated", "Scene duplicated: {0}").format(new_name), OK_C, 3)

    def _gs_duplicate_level(self, idx: int):
        """Duplica il livello selezionato (tutte le scene incluse + registrazione config)."""
        if self.gs_sel_game is None or idx is None or idx >= len(self.gs_cur_levels):
            self._status(self._TR("gs_select_level_first", "Select a level first"), WARN_C, 2)
            return
        self._with_loading(self._gs_duplicate_level_logic, idx)

    def _gs_duplicate_level_logic(self, idx: int):
        """Copia ricorsiva della cartella livello + registrazione in game_config.json."""
        import shutil
        gname = self.gs_games[self.gs_sel_game]
        lvl = self.gs_cur_levels[idx]
        src = lvl["path"]
        new_name = self._gs_unique_copy_name(src.parent, src.name)
        dst = src.parent / new_name
        try:
            shutil.copytree(src, dst)
        except Exception as exc:
            self._status(self._TR("gs_dup_level_error", "Level duplication error: {0}").format(exc), ERR_C, 4)
            return
        # Aggiorna id e name_key nel level_config.json della copia
        l_cfg = _load_json(dst / "level_config.json")
        old_nk = l_cfg.get("name_key", f"{src.name}_name")
        new_nk = f"{new_name}_name"
        l_cfg["id"] = new_name
        l_cfg["name_key"] = new_nk
        _save_json(dst / "level_config.json", l_cfg)
        # Clona i nomi multilingua con suffisso " (copia)"
        for _l in self.LANGS:
            base_val = self._gs_get_string_for_lang(gname, _l, old_nk, src.name)
            self._gs_update_strings(
                gname, {new_nk: f"{base_val}{self._GS_COPY_LABEL_SUFFIX}"}, lang=_l)
        # Registra in game_config.json subito dopo l'originale
        g_cfg_p = self.base_path / "games" / gname / "game_config.json"
        g_cfg = _load_json(g_cfg_p)
        levels_list = g_cfg.get("levels", [])
        if src.name in levels_list:
            levels_list.insert(levels_list.index(src.name) + 1, new_name)
        else:
            # Livello orfano: registriamo prima l'originale, poi la copia
            levels_list.append(src.name)
            levels_list.append(new_name)
            logger.info(f"Livello orfano '{src.name}' registrato in game_config.json")
        g_cfg["levels"] = levels_list
        _save_json(g_cfg_p, g_cfg)
        logger.info(f"Livello duplicato: '{src.name}' -> '{new_name}' (registrato in config)")
        # Refresh liste e selezione sulla copia
        self._gs_select_game(self.gs_sel_game)
        for i, l in enumerate(self.gs_cur_levels):
            if l["id"] == new_name:
                self._gs_select_level(i)
                break
        self._status(self._TR("gs_level_duplicated", "Level duplicated: {0}").format(new_name), OK_C, 3)

    def _gs_mv_dest_indices(self) -> list:
        """Indici dei livelli destinazione validi (tutti tranne quello corrente)."""
        return [i for i in range(len(self.gs_cur_levels)) if i != self.gs_sel_level]

    def _gs_move_scene_dialog(self, idx: int):
        """Apre il dialogo di scelta del livello destinazione per la scena selezionata."""
        if self.gs_sel_level is None or idx is None or idx >= len(self.gs_cur_scenes):
            self._status(self._TR("gs_select_scene_first", "Select a scene first"), WARN_C, 2)
            return
        if len(self.gs_cur_levels) < 2:
            self._status(self._TR("gs_no_other_level", "No other level available as destination"), WARN_C, 3)
            return
        self._gs_mv_mode = True
        self._gs_mv_scene_idx = idx
        self._gs_mv_scroll = 0

    def _gs_do_move_scene(self, scene_idx: int, dest_lvl_idx: int):
        """Valida e avvia lo spostamento della scena nel livello destinazione."""
        if (self.gs_sel_level is None or scene_idx is None
                or scene_idx >= len(self.gs_cur_scenes)
                or dest_lvl_idx is None or dest_lvl_idx >= len(self.gs_cur_levels)
                or dest_lvl_idx == self.gs_sel_level):
            return
        self._with_loading(self._gs_do_move_scene_logic, scene_idx, dest_lvl_idx)

    def _gs_do_move_scene_logic(self, scene_idx: int, dest_lvl_idx: int):
        """Sposta la cartella scena nel livello destinazione e aggiorna i config."""
        import shutil
        src_lvl = self.gs_cur_levels[self.gs_sel_level]
        dest_lvl = self.gs_cur_levels[dest_lvl_idx]
        scn = self.gs_cur_scenes[scene_idx]
        scn_name = scn.name
        # Collisione nome nella destinazione: suffisso _copy come per la duplicazione
        new_name = scn_name
        if (dest_lvl["path"] / new_name).exists():
            new_name = self._gs_unique_copy_name(dest_lvl["path"], scn_name)
        dst = dest_lvl["path"] / new_name
        try:
            shutil.move(str(scn), str(dst))
        except Exception as exc:
            self._status(self._TR("gs_move_scene_error", "Scene move error: {0}").format(exc), ERR_C, 4)
            return
        if new_name != scn_name:
            sd = _load_json(dst / "scene.json")
            if sd:
                sd["id"] = new_name
                _save_json(dst / "scene.json", sd)
        # Config origine: rimozione entry (preservandola per la destinazione)
        src_cfg_p = src_lvl["path"] / "level_config.json"
        src_cfg = _load_json(src_cfg_p)
        src_entry = next(
            (s for s in src_cfg.get("scenes", []) if s.get("id") == scn_name), None)
        if src_cfg_p.exists() and src_entry is not None:
            remaining = [s for s in src_cfg.get("scenes", []) if s.get("id") != scn_name]
            for i, s in enumerate(remaining):
                s["order"] = i + 1
            src_cfg["scenes"] = remaining
            _save_json(src_cfg_p, src_cfg)
        # Config destinazione: registrazione in coda (creato minimale se assente)
        dest_cfg_p = dest_lvl["path"] / "level_config.json"
        dest_cfg = _load_json(dest_cfg_p)
        if not dest_cfg:
            dest_cfg = {"id": dest_lvl["id"], "name_key": f"{dest_lvl['id']}_name",
                        "difficulty": "normal", "timer_behavior": "complete",
                        "scenes": []}
        dest_scenes = [s for s in dest_cfg.get("scenes", []) if s.get("id") != new_name]
        entry = dict(src_entry) if src_entry else \
            {"id": scn_name, "time_limit": 120, "transition_out": "fade"}
        entry["id"] = new_name
        dest_scenes.append(entry)
        for i, s in enumerate(dest_scenes):
            s["order"] = i + 1
        dest_cfg["scenes"] = dest_scenes
        _save_json(dest_cfg_p, dest_cfg)
        logger.info(
            f"Scena '{scn_name}' spostata: {src_lvl['id']} -> {dest_lvl['id']} (id: {new_name})")
        # Aggiorna i progetti recenti che puntavano al vecchio percorso
        old_p = str(scn)
        changed = False
        for r in self.recent_scenes:
            if r.get("path") == old_p:
                r["path"] = str(dst)
                changed = True
        if changed:
            self._save_editor_setting("recent_scenes", self.recent_scenes)
        # Refresh liste (il livello sorgente resta selezionato)
        old_sel_lvl = self.gs_sel_level
        self.gs_cur_levels = _discover_levels(self.game_path)
        self._gs_select_level(old_sel_lvl)
        self.gs_sel_scene = None
        self._status(self._TR("gs_scene_moved", "Scene moved to '{0}': {1}").format(dest_lvl['id'], new_name), OK_C, 3)

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_click(self, mx, my_raw):
        w, h = self.screen.get_size()

        # 0. PRIORITÀ: Click dentro dialog "Sposta scena" (se aperto)
        if getattr(self, "_gs_mv_mode", False):
            dest = self._gs_mv_dest_indices()
            vis = min(len(dest), self._GS_MV_MAX_ROWS)
            dw = self._GS_MV_DIALOG_W
            dh = self._GS_MV_LIST_Y + vis * self._GS_MV_ROW_H + self._GS_MV_FOOTER_H
            dx, dy = (w - dw) // 2, (h - dh) // 2
            scroll = getattr(self, "_gs_mv_scroll", 0)
            for row in range(vis):
                if row + scroll >= len(dest):
                    break
                di = dest[row + scroll]
                row_r = (dx + 20, dy + self._GS_MV_LIST_Y + row * self._GS_MV_ROW_H,
                         dw - 40, self._GS_MV_ROW_H - 6)
                if _in_rect((mx, my_raw), row_r):
                    scene_idx = getattr(self, "_gs_mv_scene_idx", None)
                    self._gs_mv_mode = False
                    self._gs_do_move_scene(scene_idx, di)
                    return
            # Bottone Annulla (centrato in basso, stessa taglia del dialog eliminazione)
            if _in_rect((mx, my_raw), (dx + (dw - 210) // 2, dy + dh - 48, 210, 32)):
                self._gs_mv_mode = False
                return
            return

        # 0. PRIORITÀ: Click dentro dialog "Eliminazione" (se aperto)
        if hasattr(self, '_gs_del_mode') and self._gs_del_mode:
            stage = getattr(self, "_gs_del_stage", 0)
            # Dimensioni sincronizzate con _r_gs_del_dialog
            dw, dh = 480, 200 if stage == 0 else (240 if stage == 1 else 300)
            dx, dy = (w-dw)//2, (h-dh)//2
            
            # Bottone OK (ELIMINA) - Coordinate (dx+20, dy+dh-50, 210, 32)
            if _in_rect((mx, my_raw), (dx + 20, dy + dh - 50, 210, 32)):
                self._gs_confirm_delete(); return
            # Bottone Annulla - Coordinate (dx+250, dy+dh-50, 210, 32)
            elif _in_rect((mx, my_raw), (dx + 250, dy + dh - 50, 210, 32)):
                self._gs_del_mode = None; self._gs_del_stage = 0; return
            return

        # 1. PRIORITÀ: Click dentro dialog "Nuovo" (se aperto)
        if hasattr(self, '_gs_new_mode') and self._gs_new_mode:
            dw, dh = 800, 800 if self._gs_new_mode == "game" else (450 if self._gs_new_mode == "scene" else 450)
            dx, dy = (w-dw)//2, (h-dh)//2
            off_y_game = 90 if self._gs_new_mode == "game" else 0

            # Bottone X chiusura (in alto a destra)
            xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
            if _in_rect((mx, my_raw), xr):
                self._gs_new_mode = None; return

            # Hitbox campi modalità livello (ID + 5 lingue)
            if self._gs_new_mode == "level":
                if _in_rect((mx, my_raw), (dx+20, dy+75, dw-40, 34)):
                    self._gs_new_active_field  = "id"
                    self._gs_new_all_selected  = False; return
                _lbufs = getattr(self, "_gs_new_lang_bufs",    {l: "" for l in self.LANGS})
                _lcurs = getattr(self, "_gs_new_lang_cursors", {l: 0  for l in self.LANGS})
                for _i, _l in enumerate(self.LANGS):
                    _fy = dy + 140 + _i * 42
                    if _in_rect((mx, my_raw), (dx+65, _fy, dw-85, 28)):
                        self._gs_new_active_field     = _l
                        self._gs_new_all_selected     = False
                        _lcurs[_l] = len(_lbufs.get(_l, ""))
                        self._gs_new_lang_cursors     = _lcurs; return

            if self._gs_new_mode in ("game", "scene"):
                # Hitbox Sfondo Immagine (Y=155)
                if _in_rect((mx, my_raw), (dx + 20, dy + 155 + off_y_game, 160, 34)):
                    self._bg_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new")
                    return
                # Hitbox Sfondo Video (Y=295)
                if _in_rect((mx, my_raw), (dx + 20, dy + 295 + off_y_game, 160, 34)):
                    self._vid_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new")
                    return
                # Hitbox Preview Video Play (Nuovo Progetto) - Sempre attiva se vpath esiste
                vpath = getattr(self, '_gs_new_vid_path', "")
                vprev_r = pygame.Rect(dx+580, dy+295 + off_y_game - 20, 200, 112)
                if vpath and _in_rect((mx, my_raw), vprev_r):
                    self._vid_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new", autoplay_path=vpath)
                    return
                # Hitbox Musica (Y=435)
                if self._gs_new_mode == "game":
                    if _in_rect((mx, my_raw), (dx + 20, dy + 435 + off_y_game, dw - 40, 34)):
                        self._music_modal_open(context="game_new"); return
                    
                    # Hitbox Dropdown Categoria
                    cat_r = pygame.Rect(dx + 20, dy + 142, 270, 32)
                    if _in_rect((mx, my_raw), cat_r):
                        self._gs_new_cat_dropdown = not getattr(self, "_gs_new_cat_dropdown", False)
                        return
                    
                    if getattr(self, "_gs_new_cat_dropdown", False):
                        if _in_rect((mx, my_raw), (dx + 20, dy + 174, 270, 32)):
                            self._gs_new_category = "desktop"
                            self._gs_new_cat_dropdown = False; return
                        if _in_rect((mx, my_raw), (dx + 20, dy + 206, 270, 32)):
                            self._gs_new_category = "android"
                            self._gs_new_cat_dropdown = False; return
                        # Click fuori chiude
                        self._gs_new_cat_dropdown = False

            btn_y = dy + dh - 60
            if _in_rect((mx, my_raw), (dx + 20, btn_y, 210, 34)): self._gs_confirm_new(); return
            elif _in_rect((mx, my_raw), (dx + dw - 230, btn_y, 210, 34)): self._gs_new_mode = None; return
            return
        
        # 2. PRIORITÀ: Click dentro dialog "Modifica" (se aperto)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            # Dimensioni sincronizzate con _r_gs_edit_dialog
            dw = min(1600, max(1200, int(w * 0.92)))
            dh = min(1000, max(820, int(h * 0.92)))
            dx, dy = (w-dw)//2, (h-dh)//2

            # STILE CAMPO LINGUA: stride e altezza aggiornati
            _LANG_FIELD_H: int = 34
            _LANG_FIELD_STRIDE: int = 40

            # Bottone X chiusura (hitbox allargata 34×34)
            xr = pygame.Rect(dx + dw - 46, dy + 13, 34, 34)
            if _in_rect((mx, my_raw), xr):
                self._gs_edit_mode = None; return

            if self._gs_edit_mode == "game":
                # Sincronizziamo layout modale game con coordinate assolute
                off_x2 = int(dw * 0.52)
                c1_x   = dx + 20
                c2_x   = dx + off_x2 + 10
                f_w    = off_x2 - 120

                _SEC1_Y = dy + 68
                for i, l in enumerate(self.LANGS):
                    field_r = (c1_x + 50, _SEC1_Y + 38 + i * _LANG_FIELD_STRIDE, f_w, _LANG_FIELD_H)
                    if _in_rect((mx, my_raw), field_r):
                        self._gs_edit_active_field = l
                        self._gs_edit_all_selected = False
                        self._gs_edit_cursors[l] = len(self._gs_edit_lang_bufs[l])
                        return

                _sep1_y = _SEC1_Y + 38 + len(self.LANGS) * _LANG_FIELD_STRIDE + 8
                _SEC2_Y = _sep1_y + 16
                cat_r = pygame.Rect(c1_x, _SEC2_Y + 22, 260, 34)
                if _in_rect((mx, my_raw), cat_r):
                    self._gs_edit_cat_dropdown = not getattr(self, "_gs_edit_cat_dropdown", False)
                    return

                if getattr(self, "_gs_edit_cat_dropdown", False):
                    if _in_rect((mx, my_raw), (c1_x, _SEC2_Y + 22 + 34, 260, 34)):
                        self._gs_edit_category = "desktop"; self._gs_edit_cat_dropdown = False; return
                    if _in_rect((mx, my_raw), (c1_x, _SEC2_Y + 22 + 68, 260, 34)):
                        self._gs_edit_category = "android"; self._gs_edit_cat_dropdown = False; return
                    self._gs_edit_cat_dropdown = False
                    return

                _sep2_y = _SEC2_Y + 68
                _SEC3_Y = _sep2_y + 16
                _cur_cat = getattr(self, "_gs_edit_category", "desktop")
                _THEME_INFO = [t for t in self.theme_manager.discover_themes()
                               if t.get("category", "desktop") == _cur_cat]
                if not _THEME_INFO: _THEME_INFO = [{"id": "default", "name": "Default"}]
                _t_btn_w, _t_btn_h, _t_gap = min(260, (off_x2 - 60) // 2), 42, 6
                _theme_grid_y = _SEC3_Y + 22
                for _ti, _tdata in enumerate(_THEME_INFO):
                    _tid = _tdata["id"]
                    _tx = c1_x + (_ti % 2) * (_t_btn_w + _t_gap)
                    _ty = _theme_grid_y + (_ti // 2) * (_t_btn_h + _t_gap)
                    if _in_rect((mx, my_raw), (_tx, _ty, _t_btn_w, _t_btn_h)):
                        self._gs_edit_theme_id = _tid; return

                _n_theme_rows = (len(_THEME_INFO) + 1) // 2
                _sep3_y = _theme_grid_y + _n_theme_rows * (_t_btn_h + _t_gap) + 12
                _SEC4_Y = _sep3_y + 10
                mag_r = pygame.Rect(c1_x, _SEC4_Y, off_x2 - 50, 32)
                if _in_rect((mx, my_raw), mag_r):
                    self._gs_edit_magnifier = not getattr(self, "_gs_edit_magnifier", False)
                    return

                _SEC5_Y = _SEC4_Y + 44
                btn_icon_r = pygame.Rect(c1_x, _SEC5_Y + 22, 190, 36)
                if _in_rect((mx, my_raw), btn_icon_r):
                    self._icon_modal_open(); return

                # Colonna 2 (Destra)
                _A_Y = dy + 68
                btn_i_r = pygame.Rect(c2_x, _A_Y + 22, 155, 34)
                if _in_rect((mx, my_raw), btn_i_r):
                    self._bg_modal_open(context="game_edit"); return

                r_col_w = dw - off_x2 - 40
                max_prev_h = max(80, (dh - 400) // 2)
                iprev_h = min(int(r_col_w * 9 / 16), max_prev_h)
                
                _B_Y = _A_Y + 66 + iprev_h + 22
                btn_v_r = pygame.Rect(c2_x, _B_Y + 22, 155, 34)
                if _in_rect((mx, my_raw), btn_v_r):
                    self._vid_modal_open(context="game_edit"); return
                
                vprev_h = iprev_h
                _C_Y = _B_Y + 66 + vprev_h + 16
                btn_m_r = pygame.Rect(c2_x, _C_Y + 22, r_col_w, 36)
                if _in_rect((mx, my_raw), btn_m_r):
                    self._music_modal_open(context="game_edit"); return

            elif self._gs_edit_mode == "scene":
                off_x2 = int(dw * 0.52)
                # Hitbox campi lingua (Colonna 1) — stride 40, h 34
                f_w = off_x2 - 150
                for i, l in enumerate(self.LANGS):
                    field_r = (dx + 90, dy + 106 + i * _LANG_FIELD_STRIDE, f_w, _LANG_FIELD_H)
                    if _in_rect((mx, my_raw), field_r):
                        self._gs_edit_active_field = l
                        self._gs_edit_all_selected = False
                        self._gs_edit_cursors[l] = len(self._gs_edit_lang_bufs[l])
                        return
                # Hitbox Sfondo Immagine (Punto 2)
                _y_img = dy + int(dh * 0.12)
                if _in_rect((mx, my_raw), (dx + off_x2, _y_img, 160, 34)):
                    self._bg_modal_open(context="scene_edit"); return
                # Hitbox Sfondo Video (Punto 3)
                _y_vid = dy + int(dh * 0.45)
                if _in_rect((mx, my_raw), (dx + off_x2, _y_vid, 160, 34)):
                    self._vid_modal_open(context="scene_edit"); return

            elif self._gs_edit_mode == "level":
                # Hitbox campi lingua (Colonna 1 del layout 2 col) — stride 40, h 34
                off_x2 = int(dw * 0.52)
                f_w = off_x2 - 150
                for i, l in enumerate(self.LANGS):
                    field_r = (dx + 90, dy + 106 + i * _LANG_FIELD_STRIDE, f_w, _LANG_FIELD_H)
                    if _in_rect((mx, my_raw), field_r):
                        self._gs_edit_active_field = l
                        self._gs_edit_all_selected = False
                        self._gs_edit_cursors[l] = len(self._gs_edit_lang_bufs[l])
                        return

            # Pulsanti SALVA / ANNULLA / ELIMINA — altezza aumentata a 40px
            btn_y = dy + dh - 64
            if _in_rect((mx, my_raw), (dx + 20, btn_y, 220, 40)):
                self._gs_confirm_edit(); return
            if _in_rect((mx, my_raw), (dx + dw - 240, btn_y, 220, 40)):
                self._gs_edit_mode = None; return

            if self._gs_edit_mode == "game":
                del_r = pygame.Rect(dx + 260, btn_y, 220, 40)
                if _in_rect((mx, my_raw), del_r):
                    self._gs_edit_del_stage = getattr(self, "_gs_edit_del_stage", 0) + 1
                    if self._gs_edit_del_stage >= 3:
                        self._gs_del_mode = "game"
                        self._gs_del_path = self.base_path / "games" / self.gs_games[self.gs_sel_game]
                        self._gs_del_name = self.gs_games[self.gs_sel_game]
                        self._gs_del_stage = 0
                        self._gs_edit_mode = None
                    return
            return

        # 2. Logica Dashboard Standard
        header_h = 80
        header_y = TOP_BAR_H
        ng_r = (w - 200, header_y + 20, 170, 40)
        if _in_rect((mx, my_raw), ng_r):
            self._gs_new_game(); return

        y_rec   = header_y + header_h + 30
        rec_w, rec_h = 280, 150
        for i in range(len(self.recent_scenes)):
            rx = 30 + i * (rec_w + 20)
            ry = y_rec + 25
            if _in_rect((mx, my_raw), (rx, ry, rec_w, rec_h)):
                item = self.recent_scenes[i]
                path = Path(item["path"])
                if path.exists():
                    gname = item.get("game")
                    if not gname or gname == "Unknown":
                        parts = path.parts
                        if "games" in parts:
                            idx_g = parts.index("games")
                            if idx_g + 1 < len(parts): gname = parts[idx_g + 1]
                    if gname: self._load_game(gname)
                    self._request_nav(lambda: self._load_scene(path))
                    self.state = STATE_MAIN; return
                else:
                    self.status_msg = "ERRORE: Scena non trovata!"; return

        y_browser = y_rec + 200
        col_w = (w - 80) // 3
        col_h = h - y_browser - 80
        for i in range(3):
            cx2 = 30 + i * (col_w + 10)
            cy2 = y_browser + 25
            if _in_rect((mx, my_raw), (cx2, cy2, col_w, col_h)):
                plus_r = (cx2 + col_w - 32, cy2 + 5, 26, 24)
                if _in_rect((mx, my_raw), plus_r):
                    if i == 0: self._gs_new_game()
                    elif i == 1: self._gs_new_level()
                    elif i == 2: self._gs_new_scene()
                    return
                # Bottone COMPILA EXE (solo per i==0, colonna giochi)
                if i == 0:
                    build_r = (cx2 + col_w - 62, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), build_r):
                        if self.gs_sel_game is not None:
                            self._gs_compile_game(self.gs_sel_game)
                        else:
                            self._status(self._TR("gs_select_game_first", "Select a game first"), WARN_C, 2)
                        return

                # Bottone COMPILA APK Android (solo per i==0)
                if i == 0:
                    apk_r = (cx2 + col_w - 92, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), apk_r):
                        if self.gs_sel_game is not None:
                            self._gs_compile_apk(self.gs_sel_game)
                        else:
                            self._status(self._TR("gs_select_game_first", "Select a game first"), WARN_C, 2)
                        return

                # Bottone ESPORTA HTML (solo per i==0)
                if i == 0:
                    html_r = (cx2 + col_w - 122, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), html_r):
                        if self.gs_sel_game is not None:
                            self._gs_export_html(self.gs_sel_game)
                        else:
                            self._status(self._TR("gs_select_game_first", "Select a game first"), WARN_C, 2)
                        return

                if i in (1, 2):
                    del_r = (cx2 + col_w - 62, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), del_r):
                        sel = self.gs_sel_level if i == 1 else self.gs_sel_scene
                        if sel is None: self._status(self._TR("gs_select_item_first", "Select an item first"), WARN_C, 2)
                        elif i == 1: self._gs_del_level(sel)
                        else: self._gs_del_scene(sel)
                        return

                # Bottone DUPLICA (livelli: slot -92, scene: slot -122 dopo il ✎)
                if i in (1, 2):
                    dup_x = cx2 + col_w - (92 if i == 1 else 122)
                    dup_r = (dup_x, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), dup_r):
                        sel = self.gs_sel_level if i == 1 else self.gs_sel_scene
                        if sel is None:
                            self._status(self._TR("gs_select_item_first", "Select an item first"), WARN_C, 2)
                        elif i == 1:
                            self._gs_duplicate_level(sel)
                        else:
                            self._gs_duplicate_scene(sel)
                        return

                # Bottone SPOSTA scena in altro livello (solo scene, slot -152)
                if i == 2:
                    mv_r = (cx2 + col_w - 152, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), mv_r):
                        if self.gs_sel_scene is None:
                            self._status(self._TR("gs_select_scene_first", "Select a scene first"), WARN_C, 2)
                        else:
                            self._gs_move_scene_dialog(self.gs_sel_scene)
                        return

                if i == 0:
                    # Spostato a -182 per fare spazio ai bottoni APK e HTML
                    del_r = (cx2 + col_w - 182, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), del_r):
                        if self.gs_sel_game is not None:
                            self._gs_del_game(self.gs_sel_game)
                        else:
                            self._status(self._TR("gs_select_game_first", "Select a game first"), WARN_C, 2)
                        return

                # Clic su Modifica (✎) — solo per Scene (i==2)
                # Per i Giochi (i==0) e Livelli (i==1): ✎ è inline nella riga
                if i == 2:
                    edit_off = -92
                    edit_r = (cx2 + col_w + edit_off, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), edit_r):
                        sel = self.gs_sel_scene
                        if sel is None:
                            self._status(self._TR("gs_select_item_first", "Select an item first"), WARN_C, 2)
                        else:
                            self._gs_edit_scene(sel)
                        return
                iy     = cy2 + 35
                ITEM_H = 64 if i == 2 else (50 if i == 1 else 34)
                scroll_offset = [self.gs_scroll_game, self.gs_scroll_lvl, self.gs_scroll_scn][i]
                idx = (my_raw - iy + scroll_offset * ITEM_H) // ITEM_H
                if idx < 0: return
                if i == 0 and idx < len(self.gs_games): 
                    # Coordinate bottoni riga Giochi
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    if (cy2 + 35 <= my_raw <= cy2 + col_h):
                        btn_w = 28
                        cw_safe = col_w - 15
                        bx_play = cx2 + cw_safe - 40
                        bx_edit_row = cx2 + cw_safe - 74
                        if _in_rect((mx, my_raw), (bx_edit_row, item_y + (ITEM_H-24)//2, btn_w, 24)):
                            import logging
                            logging.info(f"[GS_CLICK] Click ✎ riga gioco idx={idx}")
                            self._gs_select_game(idx)
                            self._gs_edit_game(idx)
                            return
                        if _in_rect((mx, my_raw), (bx_play, item_y + (ITEM_H-24)//2, btn_w, 24)):
                            self._gs_run_game(idx)
                            return
                    self._gs_select_game(idx)
                    # Drag Start per i Giochi (riordino globale)
                    self.gs_dragging_idx = idx
                    self.gs_dragging_col = i
                elif i == 1 and idx < len(self.gs_cur_levels):
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    if not (cy2 + 35 <= my_raw <= cy2 + col_h):
                        return

                    btn_w = 28
                    cw_safe = col_w - 15
                    bx_down     = cx2 + cw_safe - 40
                    bx_up       = cx2 + cw_safe - 74
                    bx_edit_row = cx2 + cw_safe - 108

                    # Bottone ✎ inline (come i giochi)
                    if _in_rect((mx, my_raw), (bx_edit_row, item_y + (ITEM_H - btn_w) // 2, btn_w, btn_w)):
                        self._gs_select_level(idx)
                        self._gs_edit_level(idx)
                        return

                    if idx > 0 and _in_rect((mx, my_raw), (bx_up, item_y + (ITEM_H - btn_w) // 2, btn_w, btn_w)):
                        self._gs_move_level(idx, -1); return

                    if idx < len(self.gs_cur_levels) - 1 and _in_rect((mx, my_raw), (bx_down, item_y + (ITEM_H - btn_w) // 2, btn_w, btn_w)):
                        self._gs_move_level(idx, 1); return

                    # Drag Start per i Livelli
                    self.gs_dragging_idx = idx
                    self.gs_dragging_col = i
                    self._gs_select_level(idx)
                elif i == 2 and idx < len(self.gs_cur_scenes):
                    # Click su bottoni specifici della riga
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    
                    # Verifica che il click sia dentro l'area visibile della colonna
                    if not (cy2 + 35 <= my_raw <= cy2 + col_h):
                        return
                    
                    # Coordinate bottoni (allineati a destra)
                    btn_w = 28
                    cw_safe = col_w - 15
                    bx_open = cx2 + cw_safe - 40
                    bx_down = cx2 + cw_safe - 74
                    bx_up   = cx2 + cw_safe - 108
                    
                    if _in_rect((mx, my_raw), (bx_open, item_y + (ITEM_H-btn_w)//2, btn_w, btn_w)):
                        self._gs_select_scene(idx)
                        self._request_nav(self._gs_open); return
                    
                    if idx > 0 and _in_rect((mx, my_raw), (bx_up, item_y + (ITEM_H-btn_w)//2, btn_w, btn_w)):
                        self._gs_move_scene(idx, -1); return
                        
                    if idx < len(self.gs_cur_scenes)-1 and _in_rect((mx, my_raw), (bx_down, item_y + (ITEM_H-btn_w)//2, btn_w, btn_w)):
                        self._gs_move_scene(idx, 1); return

                    # Drag Start per le Scene
                    self.gs_dragging_idx = idx
                    self.gs_dragging_col = i
                    self._gs_select_scene(idx)
                return

    def _gs_dblclick(self, mx, my_raw, w, h):
        # Sincronizziamo la logica coordinate con _gs_click / rendering
        col_w = (w - 80) // 3
        now   = time.time()
        
        col_idx = -1
        for i in range(3):
            cx = 30 + i * (col_w + 10)
            if cx <= mx <= cx + col_w:
                col_idx = i
                break
        
        if col_idx != -1 and now - self._gs_last_click < 0.4 and self._gs_last_col == col_idx:
            if col_idx == 0 and self.gs_sel_game is not None:
                self._request_nav(self._gs_open)
            elif col_idx == 1 and self.gs_sel_level is not None:
                # Per il livello, il dblclick lo "apre" (espande le scene)
                pass # Già gestito dal click singolo, ma lasciamo lo slot
            elif col_idx == 2 and self.gs_sel_scene is not None:
                self._request_nav(self._gs_open)
            
        self._gs_last_click = now
        self._gs_last_col   = col_idx

    def _gs_wheel(self, ev):
        mx, my_raw = pygame.mouse.get_pos()
        w, h = self.screen.get_size()
        col_w = (w - 80) // 3
        y_browser = 80 + 30 + 200 + 25
        
        # Priorità: Scroll Icon Modal
        if getattr(self, "_icon_modal", False):
            self._icon_wheel(ev); return

        # Priorità: Scroll lista livelli nel dialog "Sposta scena" (se aperto)
        if getattr(self, "_gs_mv_mode", False):
            dest_n = len(self._gs_mv_dest_indices())
            max_s = max(0, dest_n - self._GS_MV_MAX_ROWS)
            cur = getattr(self, "_gs_mv_scroll", 0)
            self._gs_mv_scroll = max(0, min(max_s, cur - ev.y))
            return

        # Priorità: Scroll Playlist in Dialog Modifica (se aperto)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode == "game":
            # Calcolo dinamico allineato con _r_gs_edit_dialog
            _dw_e = min(1600, max(1200, int(w * 0.92)))
            _dh_e = min(1000, max(820, int(h * 0.92)))
            _dx_e = (w - _dw_e) // 2
            _dy_e = (h - _dh_e) // 2
            _off_x2_e = int(_dw_e * 0.52)
            _y_mu_e = _dy_e + int(_dh_e * 0.78)
            _r_col_w_e = _dw_e - _off_x2_e - 40
            mu_r_scroll = pygame.Rect(_dx_e + _off_x2_e, _y_mu_e + 45, _r_col_w_e, 150)
            if mu_r_scroll.collidepoint(mx, my_raw):
                mu_list = getattr(self, "_gs_edit_music_paths", [])
                max_s = max(0, len(mu_list) - 8)
                self.gs_edit_mu_scroll = max(0, min(max_s, self.gs_edit_mu_scroll - ev.y))
                return

        if my_raw < y_browser: return
        
        # Calcolo numero di item visibili per i limiti di scroll
        col_h = h - (y_browser + 25) - 35 - 80 
        vis_count = max(1, col_h // 34)

        for i in range(3):
            cx2 = 30 + i * (col_w + 10)
            if cx2 <= mx <= cx2 + col_w:
                h_item = 64 if i == 2 else (50 if i == 1 else 34)
                vis_count = max(1, col_h // h_item)
                item_count = [len(self.gs_games), len(self.gs_cur_levels), len(self.gs_cur_scenes)][i]
                max_scroll = max(0, item_count - vis_count)
                
                if i == 0: self.gs_scroll_game = max(0, min(max_scroll, self.gs_scroll_game - ev.y))
                elif i == 1: self.gs_scroll_lvl = max(0, min(max_scroll, self.gs_scroll_lvl - ev.y))
                elif i == 2: self.gs_scroll_scn = max(0, min(max_scroll, self.gs_scroll_scn - ev.y))
                return

    def _gs_key(self, ev):
        # Dialog "Sposta scena" — ESC chiude, il resto viene consumato
        if getattr(self, "_gs_mv_mode", False):
            if ev.key == pygame.K_ESCAPE:
                self._gs_mv_mode = False
            return
        # Dialog conferma eliminazione — ha priorità su tutto
        if self._gs_del_mode:
            if ev.key == pygame.K_RETURN:
                self._gs_confirm_delete()
            elif ev.key == pygame.K_ESCAPE:
                self._gs_del_mode = None
                self._gs_del_path = None
                self._gs_del_name = ""
                self._gs_del_stage = 0  # evita di ereditare uno stage stantio nel prossimo dialog
            return
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            mods = pygame.key.get_mods()
            ctrl = bool(mods & pygame.KMOD_CTRL)
            af = self._gs_edit_active_field
            buf = self._gs_edit_lang_bufs.get(af, "")
            cur = self._gs_edit_cursors.get(af, 0)
            
            if ev.key == pygame.K_RETURN:
                self._gs_confirm_edit()
            elif ev.key == pygame.K_ESCAPE:
                self._gs_edit_mode = None
            elif ctrl:
                if ev.key == pygame.K_a:
                    self._gs_edit_all_selected = True
                elif ev.key == pygame.K_c:
                    from editor.ui.widgets import clipboard_set
                    clipboard_set(buf)
                elif ev.key == pygame.K_v:
                    from editor.ui.widgets import clipboard_get
                    pasted = clipboard_get()
                    if pasted:
                        if self._gs_edit_all_selected:
                            buf = pasted; cur = len(buf)
                            self._gs_edit_all_selected = False
                        else:
                            buf = buf[:cur] + pasted + buf[cur:]
                            cur += len(pasted)
                        self._gs_edit_lang_bufs[af] = buf
                        self._gs_edit_cursors[af] = cur
            elif ev.key == pygame.K_BACKSPACE:
                if self._gs_edit_all_selected:
                    buf = ""; cur = 0; self._gs_edit_all_selected = False
                elif cur > 0:
                    buf = buf[:cur-1] + buf[cur:]
                    cur -= 1
                self._gs_edit_lang_bufs[af] = buf
                self._gs_edit_cursors[af] = cur
            elif ev.key == pygame.K_DELETE:
                if self._gs_edit_all_selected:
                    buf = ""; cur = 0; self._gs_edit_all_selected = False
                elif cur < len(buf):
                    buf = buf[:cur] + buf[cur+1:]
                self._gs_edit_lang_bufs[af] = buf
            elif ev.key == pygame.K_LEFT:
                self._gs_edit_cursors[af] = max(0, cur - 1)
                self._gs_edit_all_selected = False
            elif ev.key == pygame.K_RIGHT:
                self._gs_edit_cursors[af] = min(len(buf), cur + 1)
                self._gs_edit_all_selected = False
            elif ev.key == pygame.K_HOME:
                self._gs_edit_cursors[af] = 0
            elif ev.key == pygame.K_END:
                self._gs_edit_cursors[af] = len(buf)
            elif ev.key == pygame.K_TAB:
                idx = (self.LANGS.index(af) + 1) % len(self.LANGS)
                self._gs_edit_active_field = self.LANGS[idx]
                self._gs_edit_all_selected = False
            elif ev.unicode and ev.unicode.isprintable():
                if self._gs_edit_all_selected:
                    buf = ev.unicode; cur = 1; self._gs_edit_all_selected = False
                else:
                    buf = buf[:cur] + ev.unicode + buf[cur:]
                    cur += 1
                self._gs_edit_lang_bufs[af] = buf
                self._gs_edit_cursors[af] = cur
            return

        if not self._gs_new_mode:
            if ev.key == pygame.K_RETURN and self.gs_sel_game is not None:
                self._request_nav(self._gs_open)
            return

        # --- MODALITÀ NUOVO (GIOCO/LIVELLO/SCENA) ---
        if self._gs_new_mode:
            mods = pygame.key.get_mods()
            ctrl = bool(mods & pygame.KMOD_CTRL)
            af = getattr(self, "_gs_new_active_field", "id")
            
            # Recupero buffer e cursore corretti
            if self._gs_new_mode == "level" and af in self.LANGS:
                l_bufs = getattr(self, "_gs_new_lang_bufs", {l: "" for l in self.LANGS})
                l_curs = getattr(self, "_gs_new_lang_cursors", {l: 0 for l in self.LANGS})
                buf = l_bufs[af]
                cur = l_curs[af]
                all_sel = False
            else:
                buf = self._gs_new_buf
                cur = getattr(self, "_gs_new_cursor", len(buf))
                all_sel = getattr(self, "_gs_new_all_selected", False)

            if ev.key == pygame.K_RETURN:
                self._gs_confirm_new()
            elif ev.key == pygame.K_ESCAPE:
                self._gs_new_mode = None
            elif ctrl:
                if ev.key == pygame.K_a:
                    all_sel = True
                elif ev.key == pygame.K_c:
                    from editor.ui.widgets import clipboard_set
                    clipboard_set(buf)
                elif ev.key == pygame.K_v:
                    from editor.ui.widgets import clipboard_get
                    pasted = clipboard_get()
                    if pasted:
                        if all_sel:
                            buf = pasted; cur = len(buf); all_sel = False
                        else:
                            buf = buf[:cur] + pasted + buf[cur:]
                            cur += len(pasted)
            elif ev.key == pygame.K_BACKSPACE:
                if all_sel:
                    buf = ""; cur = 0; all_sel = False
                elif cur > 0:
                    buf = buf[:cur-1] + buf[cur:]
                    cur -= 1
            elif ev.key == pygame.K_DELETE:
                if all_sel:
                    buf = ""; cur = 0; all_sel = False
                elif cur < len(buf):
                    buf = buf[:cur] + buf[cur+1:]
            elif ev.key == pygame.K_LEFT:
                cur = max(0, cur - 1); all_sel = False
            elif ev.key == pygame.K_RIGHT:
                cur = min(len(buf), cur + 1); all_sel = False
            elif ev.key == pygame.K_HOME:
                cur = 0; all_sel = False
            elif ev.key == pygame.K_END:
                cur = len(buf); all_sel = False
            elif ev.key == pygame.K_TAB:
                if self._gs_new_mode == "level":
                    fields = ["id"] + list(self.LANGS)
                    self._gs_new_active_field = fields[(fields.index(af) + 1) % len(fields)]
                    all_sel = False
            elif ev.unicode and ev.unicode.isprintable():
                if all_sel:
                    buf = ev.unicode; cur = 1; all_sel = False
                else:
                    buf = buf[:cur] + ev.unicode + buf[cur:]
                    cur += 1

            # Salvataggio stato aggiornato
            if self._gs_new_mode == "level" and af in self.LANGS:
                self._gs_new_lang_bufs[af] = buf
                self._gs_new_lang_cursors[af] = cur
            else:
                self._gs_new_buf = buf
                self._gs_new_cursor = cur
                self._gs_new_all_selected = all_sel
            return

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_game_select(self):
        w, h = self.screen.get_size()
        mx, my_raw = pygame.mouse.get_pos()

        header_h = 80
        header_y = TOP_BAR_H
        _rect(self.screen, (28, 28, 38), (0, header_y, w, header_h))
        pygame.draw.line(self.screen, (60, 60, 75),
                         (0, header_y + header_h), (w, header_y + header_h))
        _draw_text(self.screen, "HIDDEN INDEX", "xl", ACCENT, 30, header_y + 18)
        version_txt = self.lang_manager.get("gs_txt_editor_version", "Editor Professionale v{0}").format(VERSION)
        _draw_text(self.screen, version_txt, "sm", TXT_DIM, 33, header_y + 52)

        ng_label = self.lang_manager.get("gs_btn_new", "+ NUOVO GIOCO")
        ng_r = pygame.Rect(w - 200, header_y + 20, 170, 40)
        ng_hov = _in_rect((mx, my_raw), ng_r)
        _button(self.screen, ng_r, ng_label, ng_hov, font="md")
        if ng_hov: self.active_tooltip = self.lang_manager.get("gs_tip_new_game", "Crea un nuovo progetto di gioco da zero")

        y_rec    = header_y + header_h + 30
        _draw_text(self.screen, self.lang_manager.get("gs_recent", "PROGETTI RECENTI"), "sm", TXT_DIM, 30, y_rec)

        rec_w, rec_h = 280, 150
        for i in range(4):
            rx2 = 30 + i * (rec_w + 20)
            ry2 = y_rec + 25
            r_rect = pygame.Rect(rx2, ry2, rec_w, rec_h)
            hov = _in_rect((mx, my_raw), r_rect)
            if i < len(self.recent_scenes):
                item = self.recent_scenes[i]
                _rect(self.screen, (35, 35, 45) if hov else (30, 30, 38), r_rect, radius=8)
                _rect(self.screen, ACCENT if hov else BORDER, r_rect,
                      1 if not hov else 2, radius=8)
                _draw_text(self.screen, item["name"], "md", TXT_HI, rx2 + 12, ry2 + 12, rec_w - 24)
                _draw_text(self.screen, item["game"], "sm", TXT_DIM, rx2 + 12, ry2 + 34)
                
                thumb_r = pygame.Rect(rx2 + 10, ry2 + 55, rec_w - 20, 85)
                _rect(self.screen, (20, 20, 25), thumb_r, radius=4)
                
                # --- CARICAMENTO ANTEPRIMA ---
                scn_path = Path(item["path"])
                bg_surf = None
                
                # Tenta di recuperare l'immagine dallo scene.json
                try:
                    sd = _load_scene_data(scn_path)
                    bg_file = sd.get("background", "")
                    if bg_file and bg_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        full_bg_p = scn_path / bg_file
                        if full_bg_p.exists():
                            # Usa cache se disponibile
                            cache_key = f"thumb_{full_bg_p}"
                            if hasattr(self, "_img_cache") and cache_key in self._img_cache:
                                bg_surf = self._img_cache[cache_key]
                            else:
                                raw_img = pygame.image.load(str(full_bg_p)).convert()
                                # Resize "cover" style
                                iw, ih = raw_img.get_size()
                                tw, th = thumb_r.width, thumb_r.height
                                scale = max(tw/iw, th/ih)
                                nw, nh = int(iw * scale), int(ih * scale)
                                bg_surf = pygame.transform.smoothscale(raw_img, (nw, nh))
                                # Clip al thumb_r
                                final_thumb = pygame.Surface((tw, th))
                                final_thumb.blit(bg_surf, ((tw-nw)//2, (th-nh)//2))
                                bg_surf = final_thumb
                                if hasattr(self, "_img_cache"):
                                    self._img_cache[cache_key] = bg_surf
                except Exception: pass

                if bg_surf:
                    self.screen.blit(bg_surf, thumb_r)
                    # Overlay scuro per leggere meglio il testo se necessario
                    if hov:
                        overlay = pygame.Surface((thumb_r.width, thumb_r.height), pygame.SRCALPHA)
                        overlay.fill((0, 0, 0, 40))
                        self.screen.blit(overlay, thumb_r)
                else:
                    _draw_text(self.screen, self.lang_manager.get("gs_txt_video_na", "SFONDO VIDEO / N/A"), "sm",
                               (60, 60, 70), rx2 + 75, ry2 + 90)

                _draw_text(self.screen, self.lang_manager.get("gs_btn_open_scene", "APRI SCENA"), "sm",
                           (200, 200, 220) if hov else (100, 100, 120), rx2 + 100, ry2 + 90)
            else:
                _rect(self.screen, (22, 22, 28), r_rect, radius=8, border=1)
                _draw_text(self.screen, self.lang_manager.get("gs_slot_empty", "Slot vuoto"), "sm", (45, 45, 55), rx2 + 105, ry2 + 65)

        y_browser = y_rec + 200
        _draw_text(self.screen, self.lang_manager.get("gs_browser_title", "BROWSER PROGETTO"), "sm", TXT_DIM, 30, y_browser)

        col_w = (w - 80) // 3
        col_h = h - y_browser - 80
        col_titles = [
            self.lang_manager.get("gs_col_games", "GIOCHI"),
            self.lang_manager.get("gs_col_levels", "LIVELLI"),
            self.lang_manager.get("gs_col_scenes", "SCENE")
        ]
        for i, title in enumerate(col_titles):
            cx2 = 30 + i * (col_w + 10)
            cy2 = y_browser + 25
            c_rect = pygame.Rect(cx2, cy2, col_w, col_h)
            
            # --- INTESTAZIONE COLONNA (Premium Style) ---
            cw_safe = col_w - 15
            header_rect = pygame.Rect(cx2, cy2, cw_safe, 30)
            _rect(self.screen, (28, 30, 42), header_rect, radius=10)
            _rect(self.screen, (45, 48, 65), header_rect, 1, radius=10)
            _draw_text(self.screen, title, "sm", ACCENT, cx2 + 12, cy2 + 5)
            _rect(self.screen, (25, 25, 32), c_rect, radius=6)
            _rect(self.screen, BORDER, c_rect, 1, radius=6)
            _rect(self.screen, (34, 34, 44), (cx2, cy2, col_w, 35), radius=6, border=0)
            _draw_text(self.screen, title, "sm", ACCENT, cx2 + 12, cy2 + 8)
            plus_r = pygame.Rect(cx2 + col_w - 32, cy2 + 5, 26, 24)
            plus_hov = _in_rect((mx, my_raw), plus_r)
            _button(self.screen, plus_r, "+", plus_hov)
            if plus_hov: 
                tip_keys = ["gs_tip_add_game", "gs_tip_add_level", "gs_tip_add_scene"]
                tip_defs = ["Aggiungi un nuovo gioco", "Aggiungi un nuovo livello", "Aggiungi una nuova scena"]
                self.active_tooltip = self.lang_manager.get(tip_keys[i], tip_defs[i])
            
            # Pulsante COMPILA EXE (solo giochi, i==0)
            if i == 0:
                has_sel_build = self.gs_sel_game is not None
                build_r = pygame.Rect(cx2 + col_w - 62, cy2 + 5, 26, 24)
                build_hov = _in_rect((mx, my_raw), build_r)
                _button(self.screen, build_r, "EXE", build_hov, active=has_sel_build)
                if build_hov: self.active_tooltip = self.lang_manager.get("gs_tip_build", "Compila e pacchettizza il gioco (Crea EXE Windows)")

                # Pulsante COMPILA APK Android
                apk_r = pygame.Rect(cx2 + col_w - 92, cy2 + 5, 26, 24)
                apk_hov = _in_rect((mx, my_raw), apk_r)
                _button(self.screen, apk_r, "APK", apk_hov, active=has_sel_build)
                if apk_hov: self.active_tooltip = self.lang_manager.get("gs_tip_build_apk", "Compila e pacchettizza il gioco per Android (Crea APK)")

                # Pulsante ESPORTA HTML (sito statico)
                html_r = pygame.Rect(cx2 + col_w - 122, cy2 + 5, 26, 24)
                html_hov = _in_rect((mx, my_raw), html_r)
                _button(self.screen, html_r, "WEB", html_hov, active=has_sel_build)
                if html_hov: self.active_tooltip = self.lang_manager.get("gs_tip_export_html", "Esporta il gioco come sito statico HTML/JS → build_web/")

                # Pulsante ELIMINA GIOCO — spostato a -182 per fare spazio a EXE/APK/WEB
                del_g_r = pygame.Rect(cx2 + col_w - 182, cy2 + 5, 26, 24)
                del_g_hov = _in_rect((mx, my_raw), del_g_r)
                _button(self.screen, del_g_r, "×", del_g_hov, danger=has_sel_build)
                if del_g_hov: self.active_tooltip = self.lang_manager.get("gs_tip_delete_game", "ELIMINA COMPLETAMENTE il progetto dal disco")

            # Pulsante ✎ di modifica — solo per Scene (i==2)
            # Per Giochi (i==0) e Livelli (i==1) il ✎ è inline nella riga
            if i == 2:
                has_sel = (self.gs_sel_scene is not None)
                edit_r = pygame.Rect(cx2 + col_w - 92, cy2 + 5, 26, 24)
                edit_hov = _in_rect((mx, my_raw), edit_r)
                _button(self.screen, edit_r, "✎", edit_hov, active=has_sel)
                if edit_hov: self.active_tooltip = self.lang_manager.get(
                    "gs_tip_edit", "Modifica impostazioni e nomi dell'elemento selezionato")

            # Pulsante × di eliminazione (solo livelli e scene)
            if i in (1, 2):
                has_sel_del = (i == 1 and self.gs_sel_level is not None) or \
                              (i == 2 and self.gs_sel_scene is not None)
                del_r = pygame.Rect(cx2 + col_w - 62, cy2 + 5, 26, 24)
                del_hov = _in_rect((mx, my_raw), del_r)
                _button(self.screen, del_r, "×",
                        del_hov,
                        danger=has_sel_del)
                if del_hov: self.active_tooltip = self.lang_manager.get("gs_tip_delete_item", "Elimina definitivamente l'elemento selezionato")

            # Pulsante DUPLICA (livelli: slot -92, scene: slot -122 dopo il ✎)
            if i in (1, 2):
                has_sel_dup = (i == 1 and self.gs_sel_level is not None) or \
                              (i == 2 and self.gs_sel_scene is not None)
                dup_x = cx2 + col_w - (92 if i == 1 else 122)
                dup_r = pygame.Rect(dup_x, cy2 + 5, 26, 24)
                dup_hov = _in_rect((mx, my_raw), dup_r)
                _button(self.screen, dup_r, "DUP", dup_hov, active=has_sel_dup, font="xs")
                if dup_hov:
                    tip_key = "gs_tip_dup_level" if i == 1 else "gs_tip_dup_scene"
                    tip_def = ("Duplica il livello selezionato (tutte le scene incluse)"
                               if i == 1 else
                               "Duplica la scena selezionata (cartella completa)")
                    self.active_tooltip = self.lang_manager.get(tip_key, tip_def)

            # Pulsante SPOSTA scena in altro livello (solo scene, slot -152)
            if i == 2:
                mv_r = pygame.Rect(cx2 + col_w - 152, cy2 + 5, 26, 24)
                mv_hov = _in_rect((mx, my_raw), mv_r)
                _button(self.screen, mv_r, "MV", mv_hov,
                        active=(self.gs_sel_scene is not None), font="xs")
                if mv_hov:
                    self.active_tooltip = self.lang_manager.get(
                        "gs_tip_move_scene", "Sposta la scena selezionata in un altro livello")
            self._r_gs_column(i, cx2, cy2 + 35, col_w, col_h - 35)

        if self._gs_new_mode:
            self._r_gs_new_dialog(w, h)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            self._r_gs_edit_dialog(w, h)
        if self._gs_del_mode:
            self._r_gs_del_dialog(w, h)
        if getattr(self, "_gs_mv_mode", False):
            self._r_gs_move_dialog(w, h)

    def _r_gs_column(self, col_idx, cx, cy, cw, ch):
        mx, my_raw = pygame.mouse.get_pos()
        # Altezza variabile: 64px scene, 50px livelli (più aria), 34px giochi
        ITEM_H = 64 if col_idx == 2 else (50 if col_idx == 1 else 34)
        
        if col_idx == 0:
            count = len(self.gs_games); sel_idx = self.gs_sel_game; scroll = self.gs_scroll_game
        elif col_idx == 1:
            count = len(self.gs_cur_levels); sel_idx = self.gs_sel_level; scroll = self.gs_scroll_lvl
        else:
            count = len(self.gs_cur_scenes); sel_idx = self.gs_sel_scene; scroll = self.gs_scroll_scn

        # Logica Drag & Drop: recupero variabili di stato
        drag_col = getattr(self, "gs_dragging_col", None)
        drag_idx = getattr(self, "gs_dragging_idx", None)
        is_dragging_this_col = (drag_col == col_idx)

        vis_count = ch // ITEM_H
        if count > vis_count:
            from editor.ui.draw import _scrollbar
            _scrollbar(self.screen, cx + cw - 6, cy, 4, ch, scroll, count, vis_count)

        self.screen.set_clip(pygame.Rect(cx, cy, cw - 8, ch))
        # Sottraiamo un piccolo margine a destra per estetica (box non "attaccati")
        cw_safe = cw - 15
        for i in range(count):
            iy = cy + i * ITEM_H - scroll * ITEM_H
            if iy + ITEM_H < cy or iy > cy + ch: continue
            
            is_sel = (i == sel_idx)
            is_drag_item = (is_dragging_this_col and i == drag_idx)
            
            # Box di riga
            row_rect = pygame.Rect(cx+5, iy+2, cw_safe - 10, ITEM_H-4)
            
            if is_drag_item:
                # Feedback visivo "fantasma" per l'elemento trascinato
                _rect(self.screen, (ACCENT[0], ACCENT[1], ACCENT[2], 120), row_rect, radius=10)
                _rect(self.screen, (255, 255, 255, 80), row_rect, 1, radius=10)
            else:
                _rect(self.screen, (25, 26, 32), row_rect, radius=10)
                
            hov = _in_rect((mx, my_raw), row_rect)
            if (is_sel or hov) and not is_drag_item:
                _rect(self.screen, (BTN_AC if is_sel else BTN_HO), row_rect, radius=10)
            
            # Bordo di rifinitura
            if not is_drag_item:
                _rect(self.screen, (40, 42, 55) if is_sel else (32, 34, 45), row_rect, 1, radius=10)
            
            if not hasattr(self, "_gs_labels_cache"): self._gs_refresh_cache()
            try: label = self._gs_labels_cache[col_idx][i]
            except Exception: label = f"item_{i}"
            
            col = TXT_HI if (is_sel or hov) else TXT
            pad_w = 50
            if col_idx == 1: pad_w = 160  # Maggiore spazio per via del badge scene
            elif col_idx == 2: pad_w = 110
            
            # --- Rendering specifico per SCENE con anteprima ---
            if col_idx == 2:
                # Preview thumb (Chirurgica: usiamo la funzione centralizzata con cache)
                from editor.core.io import _get_scene_thumbnail
                bg_surf = _get_scene_thumbnail(self.gs_cur_scenes[i], (86, 48))

                thumb_rect = pygame.Rect(cx + 12, iy + (ITEM_H - 48) // 2, 86, 48)
                _rect(self.screen, (20, 20, 25), thumb_rect, radius=4)
                if bg_surf:
                    self.screen.blit(bg_surf, thumb_rect.topleft)
                _rect(self.screen, (100, 100, 120) if is_sel else (60, 60, 80), thumb_rect, 1, radius=4)
                
                # Testo spostato a destra della thumbnail
                tx_off = 110
                _draw_text(self.screen, label, "sm", col, cx + tx_off, iy + (ITEM_H - 20) // 2, cw_safe - tx_off - (pad_w - 15))
            elif col_idx == 0:
                # --- Rendering specifico per GIOCHI (con info tema) ---
                _meta = getattr(self, "_gs_meta_cache", {}).get(i, {})
                _theme = _meta.get("theme", "default")
                _cat = _meta.get("category", "desktop")
                
                # Badge Categoria (D o A)
                cat_col = (100, 150, 255) if _cat == "desktop" else (100, 255, 150)
                _badge_r = pygame.Rect(cx + 10, iy + (ITEM_H-18)//2, 18, 18)
                _rect(self.screen, cat_col, _badge_r, 1, radius=4)
                _draw_text(self.screen, _cat[0].upper(), "xs", cat_col, _badge_r.x+5, _badge_r.y+2)
                
                # Nome Gioco — larghezza ridotta per fare spazio a ▶ e ✎
                _draw_text(self.screen, label, "sm", col, cx + 35, iy + (ITEM_H - 20) // 2, cw_safe - 180)
                
                # Badge Tema (Destra, a sinistra dei pulsanti ✎ e ▶)
                t_label = _theme.upper()
                tw_t, th_t = _text_wh(t_label, "xs")
                t_r = pygame.Rect(cx + cw_safe - tw_t - 110, iy + (ITEM_H - 18) // 2, tw_t + 10, 18)
                _rect(self.screen, (60, 65, 80), t_r, radius=4)
                _draw_text(self.screen, t_label, "xs", (180, 190, 210), t_r.x + 5, t_r.y + 2)
            else:
                # Padding migliorato e centraggio verticale chirurgico (50px height)
                v_off = (ITEM_H - 20) // 2
                tx = cx + 20
                _draw_text(self.screen, label, "sm", col, tx, iy + v_off - 10 if ITEM_H >= 50 else iy + v_off, cw_safe - pad_w)
                
                if col_idx == 1:
                    try:
                        n_scenes = len(self.gs_cur_levels[i].get("scenes", []))
                        badge_txt = f"{n_scenes} SCENE"
                        tw, th = _text_wh(badge_txt, "xs")
                        # Sistema a SLOT: ✎ a -108, ▲▼ a -74/-40. Badge a -144
                        bx = cx + cw_safe - tw - 144
                        br = pygame.Rect(bx, iy + (ITEM_H - 22)//2, tw + 10, 22)
                        _rect(self.screen, (35, 40, 65), br, radius=6)
                        _rect(self.screen, (ACCENT[0], ACCENT[1], ACCENT[2], 180), br, 1, radius=6)
                        _draw_text(self.screen, badge_txt, "xs", TXT_HI, br.x + 5, br.y + 4)

                        if ITEM_H >= 50:
                            sub_txt = f"ID: {self.gs_cur_levels[i].get('id', '')}"
                            sub_col = (255, 255, 255) if (is_sel or hov) else (130, 135, 160)
                            _draw_text(self.screen, sub_txt, "xs", sub_col, tx, iy + v_off + 12, max_w=cw_safe - 160)
                    except Exception: pass
            
            if col_idx in (0, 1, 2):
                # Dimensioni pulsanti ottimizzate (Fitt's Law)
                btn_w, btn_h = 28, 28
                v_off_btn = (ITEM_H - btn_h) // 2
                
                # Sistema a SLOT (passo 34px): -40, -74, -108...
                bx_play = cx + cw_safe - 40
                
                if col_idx == 0:
                    # Bottone Play Standalone per Giochi
                    btn_play_hov = _in_rect((mx, my_raw), (bx_play, iy + (ITEM_H-24)//2, btn_w, 24))
                    _button(self.screen, (bx_play, iy + (ITEM_H-24)//2, btn_w, 24), "▶", btn_play_hov, font="sm")
                    if btn_play_hov:
                        self.active_tooltip = self.lang_manager.get("btn_play", "GIOCA")
                    # Bottone Modifica inline per Giochi
                    bx_edit = cx + cw_safe - 74
                    btn_edit_hov = _in_rect((mx, my_raw), (bx_edit, iy + (ITEM_H-24)//2, btn_w, 24))
                    _button(self.screen, (bx_edit, iy + (ITEM_H-24)//2, btn_w, 24), "✎",
                            btn_edit_hov, active=(i == sel_idx), font="sm")
                    if btn_edit_hov:
                        self.active_tooltip = self.lang_manager.get(
                            "gs_tip_edit", "Modifica impostazioni e nomi dell'elemento selezionato")
                
                elif col_idx == 1:
                    # Slot sistema: ▼=-40, ▲=-74, ✎=-108 (inline come i giochi)
                    bx_down   = cx + cw_safe - 40
                    bx_up     = cx + cw_safe - 74
                    bx_edit   = cx + cw_safe - 108

                    can_up   = (i > 0)
                    can_down = (i < count - 1)

                    btn_up_hov   = _in_rect((mx, my_raw), (bx_up, iy + v_off_btn, btn_w, btn_h)) if can_up else False
                    btn_down_hov = _in_rect((mx, my_raw), (bx_down, iy + v_off_btn, btn_w, btn_h)) if can_down else False
                    btn_edit_hov = _in_rect((mx, my_raw), (bx_edit, iy + v_off_btn, btn_w, btn_h))

                    _button(self.screen, (bx_edit, iy + v_off_btn, btn_w, btn_h), "✎",
                            btn_edit_hov, active=(i == sel_idx), font="sm")
                    if btn_edit_hov:
                        self.active_tooltip = self.lang_manager.get(
                            "gs_tip_edit", "Modifica impostazioni e nomi dell'elemento selezionato")

                    _button(self.screen, (bx_up, iy + v_off_btn, btn_w, btn_h), "▲", btn_up_hov, active=can_up, font="sm")
                    _button(self.screen, (bx_down, iy + v_off_btn, btn_w, btn_h), "▼", btn_down_hov, active=can_down, font="sm")
                        
                elif col_idx == 2:
                    bx_open = cx + cw_safe - 40
                    bx_down = cx + cw_safe - 74
                    bx_up   = cx + cw_safe - 108
                    
                    can_up   = (i > 0)
                    can_down = (i < count - 1)
                    
                    btn_open_hov = _in_rect((mx, my_raw), (bx_open, iy + v_off_btn, btn_w, btn_h))
                    _button(self.screen, (bx_open, iy + v_off_btn, btn_w, btn_h), "▶", btn_open_hov, font="sm")
                    if btn_open_hov:
                        self.active_tooltip = self.lang_manager.get("gs_btn_open_scene", "APRI SCENA")
                    
                    btn_up_hov   = _in_rect((mx, my_raw), (bx_up, iy + v_off_btn, btn_w, btn_h)) if can_up else False
                    btn_down_hov = _in_rect((mx, my_raw), (bx_down, iy + v_off_btn, btn_w, btn_h)) if can_down else False
                    
                    _button(self.screen, (bx_up, iy + v_off_btn, btn_w, btn_h), "▲", btn_up_hov, active=can_up, font="sm")
                    _button(self.screen, (bx_down, iy + v_off_btn, btn_w, btn_h), "▼", btn_down_hov, active=can_down, font="sm")

        self.screen.set_clip(None)

    def _r_gs_new_dialog(self, w, h):
        labels = {
            "game": self._TR("gs_modal_new_game", "New game"),
            "level": self._TR("gs_modal_new_level", "New level"),
            "scene": self._TR("gs_modal_new_scene", "New scene"),
        }
        stitle = labels.get(self._gs_new_mode, self._TR("gs_modal_new", "New"))

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))

        dw, dh = 800, 800 if self._gs_new_mode == "game" else (450 if self._gs_new_mode == "scene" else 450)
        dx, dy = (w-dw)//2, (h-dh)//2
        box    = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (40, 42, 54), box, radius=12); _rect(self.screen, ACCENT, box, 2, radius=12)

        _draw_text(self.screen, stitle, "lg", TXT_HI, dx + 30, dy + 20)
        
        # Bottone X di chiusura in alto a destra
        mx2, my2 = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
        x_hov = _in_rect((mx2, my2), xr)
        _button(self.screen, xr, "X", x_hov, danger=True)

        # Punto 1 — ID / nome univoco
        _draw_text(self.screen, self._TR("gs_label_title", "Step 1: Title / ID"), "sm", TXT_DIM, dx+20, dy+55)
        inp_r = pygame.Rect(dx+20, dy+75, dw-40, 34)
        placeholder = self._TR("gs_placeholder_new", "Enter ID or name...")
        if self._gs_new_mode == "level":
            _af      = getattr(self, "_gs_new_active_field", "id")
            _id_foc  = (_af == "id")
            _id_cur  = getattr(self, "_gs_new_cursor", len(self._gs_new_buf)) if _id_foc else None
            _id_asel = getattr(self, "_gs_new_all_selected", False) if _id_foc else False
            _input_box(self.screen, inp_r, self._gs_new_buf, focused=_id_foc, hint=placeholder, font="md",
                       cursor_pos=_id_cur, all_selected=_id_asel)
        else:
            _id_asel = getattr(self, "_gs_new_all_selected", False)
            _id_cur  = getattr(self, "_gs_new_cursor", len(self._gs_new_buf))
            _input_box(self.screen, inp_r, self._gs_new_buf, focused=True, hint=placeholder, font="md",
                       cursor_pos=_id_cur, all_selected=_id_asel)

        # Campi localizzazione — solo modalità livello
        if self._gs_new_mode == "level":
            _draw_text(self.screen, self._TR("gs_ingame_names", "In-game names (localization):"), "sm", TXT_DIM, dx+20, dy+122)
            _lbufs  = getattr(self, "_gs_new_lang_bufs",    {l: "" for l in self.LANGS})
            _lcurs  = getattr(self, "_gs_new_lang_cursors", {l: 0  for l in self.LANGS})
            _af     = getattr(self, "_gs_new_active_field", "id")
            _llbls  = {"it": "IT", "en": "EN", "es": "ES", "fr": "FR", "de": "DE"}
            for _i, _l in enumerate(self.LANGS):
                _fy   = dy + 140 + _i * 42
                _is_a = (_af == _l)
                _draw_text(self.screen, _llbls[_l], "sm", ACCENT if _is_a else TXT_DIM, dx+22, _fy+6)
                _f_r  = pygame.Rect(dx+65, _fy, dw-85, 28)
                _lbuf = _lbufs.get(_l, "")
                _lcur = _lcurs.get(_l, len(_lbuf)) if _is_a else None
                _input_box(self.screen, _f_r, _lbuf, focused=_is_a,
                           hint=self._TR("gs_placeholder_lang",
                                         "Name {0}...").format(_l.upper()),
                           font="md", cursor_pos=_lcur)

        mx2, my2 = pygame.mouse.get_pos()
        if self._gs_new_mode == "game":
            # Punto 1.5 - Categoria (Dropdown)
            _draw_text(self.screen, self._TR("gs_target_platform", "Category / target platform"), "sm", TXT_DIM, dx+20, dy+122)
            cat_r = pygame.Rect(dx+20, dy+142, 270, 32)
            cur_cat = getattr(self, "_gs_new_category", "desktop")
            _is_open = getattr(self, "_gs_new_cat_dropdown", False)
            cat_lbl = self._TR("gs_mode_label", "MODE: {0}").format(cur_cat.upper())
            _button(self.screen, cat_r,
                    cat_lbl + "  " + ("^" if _is_open else "v"),
                    _in_rect((mx2, my2), cat_r), active=_is_open)
            # Rimosso il disegno delle opzioni da qui per disegnarle sopra a tutto alla fine

        if self._gs_new_mode in ("game", "scene"):
            # Spostiamo Point 2 e 3 più in basso se siamo in modalità gioco per far posto alla categoria
            # Se il dropdown è aperto, spostiamo ancora più in basso o lasciamo sovrapporre? 
            # Per ora lasciamo spazio fisso.
            off_y_game = 90 if self._gs_new_mode == "game" else 0
            
            # IMMAGINE
            iy = dy + 155 + off_y_game
            _draw_text(self.screen, self.lang_manager.get("gs_label_bg_img", "Punto 2: Sfondo Immagine (Opzionale)"), "sm", TXT_DIM, dx+20, iy-25)
            btn_r = pygame.Rect(dx+20, iy, 160, 34); path = getattr(self, '_gs_new_bg_path', "")
            _button(self.screen, btn_r, self.lang_manager.get("gs_btn_choose_img", "Scegli Immagine..."), _in_rect((mx2, my2), btn_r))
            _rect(self.screen, (20, 22, 30), (dx+190, iy, 380, 34), radius=4)
            _draw_text(self.screen, Path(path).name if path else self.lang_manager.get("gs_no_asset", "Nessuna immagine"), "sm", (TXT_HI if path else TXT_DIM), dx+200, iy+8, 360)
            
            prev_r = pygame.Rect(dx+580, iy-20, 200, 112)
            _rect(self.screen, (10, 12, 20), prev_r, radius=8); _rect(self.screen, BORDER, prev_r, 1, radius=8)
            surf = getattr(self, "_gs_new_bg_preview_surf", None)
            if surf: self.screen.blit(surf, prev_r.topleft)
            else: _draw_text(self.screen, self.lang_manager.get("gs_txt_no_preview", "[ NESSUNA ANTEPRIMA ]"), "xs", (60, 65, 90), prev_r.x + 60, prev_r.y + 45)

            # VIDEO
            vy = dy + 295 + off_y_game
            _draw_text(self.screen, self.lang_manager.get("gs_label_bg_vid", "Punto 3: Sfondo Video (Alternativo)"), "sm", TXT_DIM, dx+20, vy-25)
            btn_v_r = pygame.Rect(dx+20, vy, 160, 34); vpath = getattr(self, '_gs_new_vid_path', "")
            _button(self.screen, btn_v_r, self.lang_manager.get("gs_btn_choose_vid", "Scegli Video..."), _in_rect((mx2, my2), btn_v_r))
            _rect(self.screen, (20, 22, 30), (dx+190, vy, 380, 34), radius=4)
            _draw_text(self.screen, Path(vpath).name if vpath else self.lang_manager.get("gs_no_asset_v", "Nessun video"), "sm", (OK_C if vpath else TXT_DIM), dx+200, vy+8, 360)

            vprev_r = pygame.Rect(dx+580, vy-20, 200, 112)
            _rect(self.screen, (10, 12, 20), vprev_r, radius=8); _rect(self.screen, BORDER, vprev_r, 1, radius=8)
            vpath = getattr(self, "_gs_new_vid_path", "")
            vsurf = getattr(self, "_gs_new_vid_preview_surf", None)
            if vsurf: 
                self.screen.blit(vsurf, vprev_r.topleft)
            else: 
                _draw_text(self.screen, self.lang_manager.get("gs_txt_no_preview", "[ NESSUNA ANTEPRIMA ]"), "xs", (60, 65, 90), vprev_r.x + 60, vprev_r.y + 45)
            
            # Pulsante Play Overlay (Indipendente da vsurf se vpath esiste)
            if vpath:
                cp = vprev_r.center
                p_hov = _in_rect((mx2, my2), vprev_r)
                pygame.draw.circle(self.screen, (50, 60, 100, 220) if p_hov else (25, 30, 55, 180), cp, 32)
                _draw_shape_icon(self.screen, (cp[0]-15, cp[1]-15, 30, 30), "play", TXT_HI if p_hov else TXT_DIM)

            if self._gs_new_mode == "game":
                my = dy + 435 + off_y_game
                btn_m_r = pygame.Rect(dx+20, my, dw-40, 34); mpath = getattr(self, '_gs_new_music_paths', [])
                label_m = f"{len(mpath)} " + self.lang_manager.get("gs_tracks_manage", "brani - Gestisci Playlist...")
                _button(self.screen, btn_m_r, label_m, _in_rect((mx2, my2), btn_m_r))
                list_r = pygame.Rect(dx+20, my+45, dw-40, 150)
                _rect(self.screen, (26, 28, 38), list_r, radius=8)
                for i, p in enumerate(mpath[:7]):
                    _draw_text(self.screen, f"{i+1}. {Path(p).name}", "sm", TXT, list_r.x+10, list_r.y+10+i*18)

        # Messaggio di errore inline (se presente e recente)
        if getattr(self, "status_until", 0) > time.time() and getattr(self, "status_col", None) == ERR_C:
            _draw_text(self.screen, self.status_msg, "sm", ERR_C, dx + 20, dy + dh - 85)

        btn_y = dy + dh - 60
        ok_r, esc_r = pygame.Rect(dx+20, btn_y, 210, 34), pygame.Rect(dx+dw-230, btn_y, 210, 34)
        _button(self.screen, ok_r, self.lang_manager.get("gs_btn_confirm", "CONFERMA"), _in_rect((mx2, my2), ok_r), active=True)
        _button(self.screen, esc_r, self.lang_manager.get("gs_btn_cancel", "ANNULLA"), _in_rect((mx2, my2), esc_r))

        # Disegno finale dei dropdown (sopra a tutto)
        if self._gs_new_mode == "game" and getattr(self, "_gs_new_cat_dropdown", False):
            mx2, my2 = pygame.mouse.get_pos()
            cur_cat = getattr(self, "_gs_new_category", "desktop")
            opt_d = pygame.Rect(dx+20, dy+174, 270, 32)
            opt_a = pygame.Rect(dx+20, dy+206, 270, 32)
            _button(self.screen, opt_d, "DESKTOP", _in_rect((mx2, my2), opt_d), active=(cur_cat=="desktop"))
            _button(self.screen, opt_a, "ANDROID", _in_rect((mx2, my2), opt_a), active=(cur_cat=="android"))

    def _r_gs_del_dialog(self, w: int, h: int):
        """Dialog di conferma eliminazione livello, scena o gioco (Tripla conferma per Game)."""
        mode_label = {
            "level": self.lang_manager.get("gs_label_level", "livello"), 
            "scene": self.lang_manager.get("gs_label_scene", "scena"), 
            "game": self.lang_manager.get("gs_label_game_caps", "GIOCO")
        }.get(self._gs_del_mode, "")
        stage = getattr(self, "_gs_del_stage", 0)

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))

        dw, dh = 480, 200 if stage == 0 else (240 if stage == 1 else 300)
        dx, dy = (w - dw) // 2, (h - dh) // 2
        box = pygame.Rect(dx, dy, dw, dh)
        
        bg_col  = (52, 22, 22) if stage == 0 else (80, 20, 20)
        brd_col = (200, 60, 60) if stage == 0 else (255, 0, 0)
        _rect(self.screen, bg_col, box, radius=8); _rect(self.screen, brd_col, box, 2, radius=8)

        # Header
        titles = [
            self.lang_manager.get("gs_del_title_0", "Elimina?"), 
            self.lang_manager.get("gs_del_title_1", "CONFERMA FINALE!"), 
            self.lang_manager.get("gs_del_title_2", "ULTIMA CHANCE!")
        ]
        hdr = titles[stage] if stage < len(titles) else titles[-1]
        t_surf = _txt(hdr, "lg", (255, 255, 255))
        self.screen.blit(t_surf, (dx + (dw - t_surf.get_width()) // 2, dy + 15))

        # Testo
        msgs = [ 
            self.lang_manager.get("gs_del_msg_0", "Vuoi eliminare {0} \"{1}\"?").format(mode_label, self._gs_del_name),
            self.lang_manager.get("gs_del_msg_1", "L'operazione è IRREVERSIBILE e cancellerà ogni file!"),
            self.lang_manager.get("gs_del_msg_2", "ATTENZIONE: Il progetto verrà eliminato definitivamente dal disco!") 
        ]
        info = _txt(msgs[stage], "sm", (255, 180, 180) if stage > 0 else TXT_DIM)
        self.screen.blit(info, (dx + (dw - info.get_width()) // 2, dy + 65))
        
        if stage == 2:
            warning = _txt(self.lang_manager.get("gs_del_warning", "Sei veramente sicuro? Non potrai tornare indietro."), "sm", (255, 50, 50))
            self.screen.blit(warning, (dx + (dw - warning.get_width()) // 2, dy + 100))

        mx2, my2 = pygame.mouse.get_pos()
        ok_r, esc_r = pygame.Rect(dx+20, dy+dh-50, 210, 32), pygame.Rect(dx+250, dy+dh-50, 210, 32)
        btn_labels = [
            self.lang_manager.get("gs_btn_del_0", "ELIMINA"), 
            self.lang_manager.get("gs_btn_del_1", "SI, CONFERMA"), 
            self.lang_manager.get("gs_btn_del_2", "SI, DISTRUGGI TUTTO")
        ]
        _button(self.screen, ok_r, btn_labels[stage] if stage < 3 else "ERRORE", _in_rect((mx2, my2), ok_r), danger=True)
        _button(self.screen, esc_r, self.lang_manager.get("gs_btn_cancel_esc", "Annulla (Esc)"), _in_rect((mx2, my2), esc_r))

    def _r_gs_move_dialog(self, w: int, h: int):
        """Dialog di scelta del livello destinazione per lo spostamento scena."""
        mx2, my2 = pygame.mouse.get_pos()
        dest = self._gs_mv_dest_indices()
        vis = min(len(dest), self._GS_MV_MAX_ROWS)
        dw = self._GS_MV_DIALOG_W
        dh = self._GS_MV_LIST_Y + vis * self._GS_MV_ROW_H + self._GS_MV_FOOTER_H
        dx, dy = (w - dw) // 2, (h - dh) // 2

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))
        box = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (40, 42, 54), box, radius=12)
        _rect(self.screen, ACCENT, box, 2, radius=12)

        title = self.lang_manager.get("gs_modal_move_scene", "Sposta scena in un altro livello")
        _draw_text(self.screen, title, "lg", TXT_HI, dx + 30, dy + 18)
        scene_idx = getattr(self, "_gs_mv_scene_idx", None)
        scn_name = ""
        if scene_idx is not None and scene_idx < len(self.gs_cur_scenes):
            scn_name = self.gs_cur_scenes[scene_idx].name
        sub = self.lang_manager.get(
            "gs_label_move_dest", "Scena '{0}' — scegli il livello destinazione:"
        ).format(scn_name)
        _draw_text(self.screen, sub, "sm", TXT_DIM, dx + 30, dy + 58, dw - 60)

        scroll = getattr(self, "_gs_mv_scroll", 0)
        for row in range(vis):
            if row + scroll >= len(dest):
                break
            di = dest[row + scroll]
            row_r = pygame.Rect(dx + 20, dy + self._GS_MV_LIST_Y + row * self._GS_MV_ROW_H,
                                dw - 40, self._GS_MV_ROW_H - 6)
            hov = _in_rect((mx2, my2), row_r)
            label = self._gs_get_human_name("level", di)
            lvl_id = self.gs_cur_levels[di]["id"]
            if label != lvl_id:
                label = f"{label}  [{lvl_id}]"
            _button(self.screen, row_r, label, hov, font="sm")
        if len(dest) > vis:
            _scrollbar(self.screen, dx + dw - 12, dy + self._GS_MV_LIST_Y, 4,
                       vis * self._GS_MV_ROW_H, scroll, len(dest), vis)

        cancel_r = pygame.Rect(dx + (dw - 210) // 2, dy + dh - 48, 210, 32)
        _button(self.screen, cancel_r,
                self.lang_manager.get("gs_btn_cancel_esc", "Annulla (Esc)"),
                _in_rect((mx2, my2), cancel_r))

    def _r_gs_edit_dialog(self, w, h):
        labels = {
            "game": self.lang_manager.get("gs_modal_edit_game", "Impostazioni Progetto"),
            "level": self.lang_manager.get("gs_modal_edit_level", "Modifica livello"),
            "scene": self.lang_manager.get("gs_modal_edit_scene", "Modifica scena")
        }
        etitle = labels.get(self._gs_edit_mode, "Modifica")

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))

        # Dimensioni dinamiche relative alla finestra — ingrandite per miglior usabilità
        dw = min(1600, max(1200, int(w * 0.92)))
        dh = min(1000, max(820, int(h * 0.92)))
        dx, dy = (w - dw) // 2, (h - dh) // 2
        box = pygame.Rect(dx, dy, dw, dh)
        # Sfondo con leggero gradiente simulato (layer doppio)
        _rect(self.screen, (22, 24, 36), box, radius=14)
        _rect(self.screen, (28, 30, 42), pygame.Rect(dx, dy + dh // 2, dw, dh // 2), radius=0)
        _rect(self.screen, (28, 30, 42), pygame.Rect(dx + 14, dy, dw - 28, dh), radius=0)
        _rect(self.screen, ACCENT, box, 2, radius=14)

        _draw_text(self.screen, etitle, "lg", TXT_HI, dx + 30, dy + 22)

        # Separatore header
        pygame.draw.line(self.screen, (*ACCENT[:3], 80), (dx + 20, dy + 52), (dx + dw - 20, dy + 52), 1)

        # Bottone X di chiusura — hitbox 34×34
        mx2, my2 = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 46, dy + 13, 34, 34)
        x_hov = _in_rect((mx2, my2), xr)
        _button(self.screen, xr, "X", x_hov, danger=True)

        # Costanti layout campi lingua (condivise render/click)
        _LANG_FIELD_H: int = 34
        _LANG_FIELD_STRIDE: int = 40

        if self._gs_edit_mode == "game":
            off_x2 = int(dw * 0.52)
            # Separatore verticale tra le due colonne
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + off_x2 - 14, dy + 62), (dx + off_x2 - 14, dy + dh - 70), 1
            )
            # ── COLONNA 1 (Sinistra): TESTI E TEMA ────────────────────────────
            # Punto 1: Localizzazione
            _draw_text(self.screen, self._TR("gs_step_title_tr", "1. TITLE AND TRANSLATIONS"), "sm", TXT_DIM, dx + 20, dy + 68)
            f_w = off_x2 - 150  # Larghezza dinamica campo testo
            for i, l in enumerate(self.LANGS):
                fy = dy + 106 + i * _LANG_FIELD_STRIDE
                is_active = (self._gs_edit_active_field == l)
                lbl_col = ACCENT if is_active else TXT_DIM
                # Etichetta lingua (font sm per leggibilità)
                _draw_text(self.screen, l.upper(), "sm", lbl_col, dx + 20, fy + 8)
            # ── LAYOUT: coordinate fisse dentro la modale (no percentuali di dh) ──
            # Colonna sx: 0..off_x2-14  Colonna dx: off_x2..dw
            off_x2 = int(dw * 0.52)
            c1_x   = dx + 20          # Inizio content col sinistra
            c2_x   = dx + off_x2 + 10  # Inizio content col destra
            c2_w   = dw - off_x2 - 50  # Larghezza utile col destra
            f_w    = off_x2 - 120       # Larghezza campo testo lingua

            # Separatore verticale
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + off_x2 - 14, dy + 62), (dx + off_x2 - 14, dy + dh - 70), 1
            )

            # ══════════════════════════════════════════════════
            # COLONNA SINISTRA
            # ══════════════════════════════════════════════════

            # ── Sez. 1: Titolo e traduzioni ───────────────────
            _SEC1_Y = dy + 68   # Y inizio sezione 1
            _draw_text(self.screen, self._TR("gs_step_game_title", "❶  GAME TITLE"), "sm", TXT_DIM, c1_x, _SEC1_Y)

            # Hint TAB
            _draw_text(self.screen,
                       self._TR("gs_tab_hint", "TAB -> next field  |  Ctrl+A / C / V"),
                       "xs", (70, 74, 95), c1_x, _SEC1_Y + 18)

            for i, l in enumerate(self.LANGS):
                fy = _SEC1_Y + 38 + i * _LANG_FIELD_STRIDE
                is_active = (self._gs_edit_active_field == l)
                lbl_col = ACCENT if is_active else TXT_DIM
                _draw_text(self.screen, l.upper(), "sm", lbl_col, c1_x, fy + 8)
                field_r = pygame.Rect(c1_x + 50, fy, f_w, _LANG_FIELD_H)
                buf     = self._gs_edit_lang_bufs.get(l, "")
                is_all  = (is_active and getattr(self, "_gs_edit_all_selected", False))
                cur_pos = self._gs_edit_cursors.get(l, 0) if is_active else None
                _input_box(self.screen, field_r, buf, focused=is_active,
                           hint=f"{l.upper()}...", font="md",
                           all_selected=is_all, cursor_pos=cur_pos)

            # Separatore orizzontale post-campi
            _sep1_y = _SEC1_Y + 38 + len(self.LANGS) * _LANG_FIELD_STRIDE + 8
            pygame.draw.line(
                self.screen, (*BORDER[:3], 55),
                (c1_x, _sep1_y), (dx + off_x2 - 30, _sep1_y), 1
            )

            # ── Sez. 2: Piattaforma target ────────────────────
            _SEC2_Y = _sep1_y + 16
            _draw_text(self.screen, self._TR("gs_step_platform", "❷  TARGET PLATFORM"), "sm", TXT_DIM, c1_x, _SEC2_Y)
            _cur_cat = getattr(self, "_gs_edit_category", "desktop")
            _is_open = getattr(self, "_gs_edit_cat_dropdown", False)
            cat_r = pygame.Rect(c1_x, _SEC2_Y + 22, 260, 34)
            _button(self.screen, cat_r,
                    f"{'💻 DESKTOP' if _cur_cat == 'desktop' else '📱 ANDROID'}  {'▲' if _is_open else '▼'}",
                    _in_rect((mx2, my2), cat_r), active=_is_open)

            # ── Sez. 3: Tema interfaccia ──────────────────────
            _sep2_y = _SEC2_Y + 68
            pygame.draw.line(
                self.screen, (*BORDER[:3], 55),
                (c1_x, _sep2_y), (dx + off_x2 - 30, _sep2_y), 1
            )
            _SEC3_Y = _sep2_y + 16
            _draw_text(self.screen, self._TR("gs_step_theme", "❸  MENU INTERFACE THEME"), "sm", TXT_DIM, c1_x, _SEC3_Y)

            _THEME_INFO = [t for t in self.theme_manager.discover_themes()
                           if t.get("category", "desktop") == _cur_cat]
            if not _THEME_INFO:
                _THEME_INFO = [{"id": "default", "name": "Default"}]

            _cur_theme = getattr(self, "_gs_edit_theme_id", "default")
            _t_btn_w, _t_btn_h, _t_gap = min(260, (off_x2 - 60) // 2), 42, 6

            def _tcol(colors, key, fallback):
                v = colors.get(key)
                return tuple(v[:3]) if v else fallback

            _theme_grid_y = _SEC3_Y + 22
            for _ti, _tdata in enumerate(_THEME_INFO):
                _tid    = _tdata["id"]
                _tlabel = _tdata["name"]
                _cols   = self.theme_manager._cached_themes.get(_tid, {}).get("colors", {})
                _bg  = _tcol(_cols, "background_overlay", (30, 32, 42))
                _acc = _tcol(_cols, "btn_border_hover", _tcol(_cols, "btn_glow_color", ACCENT))
                _ico = _tcol(_cols, "icon_color", _tcol(_cols, "text_normal", (235, 238, 245)))

                _tx = c1_x + (_ti % 2) * (_t_btn_w + _t_gap)
                _ty = _theme_grid_y + (_ti // 2) * (_t_btn_h + _t_gap)
                _tr = pygame.Rect(_tx, _ty, _t_btn_w, _t_btn_h)
                _is_sel = (_cur_theme == _tid)
                _t_hov  = _in_rect((mx2, my2), _tr)

                _fill = tuple(min(255, c + 22) for c in _bg) if _t_hov else _bg
                _rect(self.screen, _fill, _tr, radius=8)
                _rect(self.screen, _acc, (_tx, _ty, 5, _t_btn_h), radius=0)
                _rect(self.screen, ACCENT if _is_sel else BORDER, _tr,
                      2 if _is_sel else 1, radius=8)
                _draw_text(self.screen, _tlabel, "sm", TXT_HI,
                           _tx + 14, _ty + 12, max_w=_t_btn_w - 80)
                _cy = _ty + _t_btn_h // 2
                for _ci, _cc in enumerate((_acc, _ico)):
                    _cr = pygame.Rect(_tx + _t_btn_w - 46 + _ci * 22, _cy - 8, 16, 16)
                    _rect(self.screen, _cc, _cr, radius=4)
                    _rect(self.screen, (0, 0, 0), _cr, 1, radius=4)
                if _is_sel:
                    _draw_text(self.screen, "●", "xs", ACCENT,
                               _tx + _t_btn_w - 12, _ty + 4)

            # ── Sez. 4: Extra tema + Icona ────────────────────
            _n_theme_rows = (len(_THEME_INFO) + 1) // 2
            _sep3_y = _theme_grid_y + _n_theme_rows * (_t_btn_h + _t_gap) + 12
            pygame.draw.line(
                self.screen, (*BORDER[:3], 55),
                (c1_x, _sep3_y), (dx + off_x2 - 30, _sep3_y), 1
            )
            _SEC4_Y = _sep3_y + 10

            # Toggle Magnifier
            mag_r   = pygame.Rect(c1_x, _SEC4_Y, off_x2 - 50, 32)
            mag_hov = _in_rect((mx2, my2), mag_r)
            _mag_on = self._gs_edit_magnifier
            _rect(self.screen, (40, 42, 55) if mag_hov else (26, 28, 40), mag_r, radius=7)
            _rect(self.screen, ACCENT if _mag_on else BORDER, mag_r, 1, radius=7)
            # Pill on/off
            _pill_col = ACCENT if _mag_on else (55, 58, 75)
            _pill_r   = pygame.Rect(mag_r.x + 8, mag_r.y + 7, 36, 18)
            _rect(self.screen, _pill_col, _pill_r, radius=9)
            _knob_x   = _pill_r.x + 20 if _mag_on else _pill_r.x + 2
            pygame.draw.circle(self.screen, TXT_HI, (_knob_x + 7, _pill_r.y + 9), 7)
            _draw_text(self.screen, self._TR("gs_magnifier_fx", "MAGNIFIER EFFECT"),
                       "xs", TXT_HI if mag_hov else TXT, mag_r.x + 52, mag_r.y + 9)

            # Icona progetto
            _SEC5_Y = _SEC4_Y + 44
            _draw_text(self.screen, self._TR("gs_step_icon", "❹  PROJECT ICON"), "sm", TXT_DIM, c1_x, _SEC5_Y)
            btn_icon_r = pygame.Rect(c1_x, _SEC5_Y + 22, 190, 36)
            _button(self.screen, btn_icon_r, self._TR("gs_choose_icon", "Choose icon..."), _in_rect((mx2, my2), btn_icon_r))
            g_id = self.gs_games[self.gs_sel_game]
            icon_path = self.base_path / "games" / g_id / "assets" / "icon.png"
            _icon_prev_r = pygame.Rect(c1_x + 200, _SEC5_Y + 14, 48, 48)
            _rect(self.screen, (10, 10, 15), _icon_prev_r, radius=8)
            _rect(self.screen, BORDER, _icon_prev_r, 1, radius=8)
            if icon_path.exists():
                try:
                    i_key = f"gs_icon_{g_id}"
                    if i_key not in self._img_cache:
                        sur = pygame.image.load(str(icon_path)).convert_alpha()
                        self._img_cache[i_key] = pygame.transform.smoothscale(sur, (48, 48))
                    self.screen.blit(self._img_cache[i_key], _icon_prev_r.topleft)
                except Exception: pass
            else:
                _draw_shape_icon(
                    self.screen,
                    (_icon_prev_r.x + 12, _icon_prev_r.y + 12, 24, 24),
                    "image", (60, 60, 75)
                )

            # ══════════════════════════════════════════════════
            # COLONNA DESTRA
            # ══════════════════════════════════════════════════
            r_col_w  = dw - off_x2 - 40
            path_w   = r_col_w - 185

            # ── Sez. A: Immagine di sfondo ────────────────────
            _A_Y = dy + 68
            _draw_text(self.screen, self._TR("gs_step_bg_image", "❺  BACKGROUND IMAGE"), "sm", TXT_DIM, c2_x, _A_Y)
            btn_i_r = pygame.Rect(c2_x, _A_Y + 22, 155, 34)
            _button(self.screen, btn_i_r, self._TR("gs_choose", "Choose..."), _in_rect((mx2, my2), btn_i_r))
            ipath   = getattr(self, '_gs_edit_bg_path', "")
            _path_box_r = pygame.Rect(c2_x + 163, _A_Y + 22, path_w, 34)
            _rect(self.screen, (20, 22, 30), _path_box_r, radius=5)
            _rect(self.screen, BORDER, _path_box_r, 1, radius=5)
            _draw_text(
                self.screen,
                Path(ipath).name if ipath else "— nessuna immagine —",
                "xs", TXT_HI if ipath else (65, 70, 90),
                _path_box_r.x + 10, _path_box_r.y + 10, path_w - 16
            )
            # Preview
            # Calcoliamo l'altezza massima per non sforare la modale (circa 400px spazio fisso usato + footer)
            max_prev_h = max(80, (dh - 400) // 2)
            iprev_h = min(int(r_col_w * 9 / 16), max_prev_h)
            iprev_w = int(iprev_h * 16 / 9)
            iprev_r = pygame.Rect(c2_x, _A_Y + 66, iprev_w, iprev_h)
            _rect(self.screen, (10, 12, 18), iprev_r, radius=10)
            _rect(self.screen, BORDER, iprev_r, 1, radius=10)
            isurf = getattr(self, "_gs_edit_bg_preview_surf", None)
            if isurf:
                is_scaled = pygame.transform.smoothscale(isurf, (iprev_w, iprev_h))
                self.screen.blit(is_scaled, iprev_r.topleft)
            else:
                _draw_text(
                    self.screen, self._TR("gs_preview_tag", "[ PREVIEW ]"), "xs", (55, 60, 82),
                    iprev_r.x + iprev_w // 2 - 35, iprev_r.y + iprev_h // 2 - 7
                )

            # ── Sez. B: Video di sfondo ───────────────────────
            _B_Y = _A_Y + 66 + iprev_h + 22
            _draw_text(self.screen, self._TR("gs_step_bg_video", "❻  BACKGROUND VIDEO (LOOP)"), "sm", TXT_DIM, c2_x, _B_Y)
            btn_v_r = pygame.Rect(c2_x, _B_Y + 22, 155, 34)
            _button(self.screen, btn_v_r, self._TR("gs_choose", "Choose..."), _in_rect((mx2, my2), btn_v_r))
            vpath = getattr(self, '_gs_edit_vid_path', "")
            _vpath_box_r = pygame.Rect(c2_x + 163, _B_Y + 22, path_w, 34)
            _rect(self.screen, (20, 22, 30), _vpath_box_r, radius=5)
            _rect(self.screen, BORDER, _vpath_box_r, 1, radius=5)
            _draw_text(
                self.screen,
                Path(vpath).name if vpath else "— nessun video —",
                "xs", OK_C if vpath else (65, 70, 90),
                _vpath_box_r.x + 10, _vpath_box_r.y + 10, path_w - 16
            )
            # Preview video
            vprev_h = iprev_h
            vprev_r = pygame.Rect(c2_x, _B_Y + 66, iprev_w, vprev_h)
            _rect(self.screen, (10, 12, 18), vprev_r, radius=10)
            _rect(self.screen, BORDER, vprev_r, 1, radius=10)
            vsurf = getattr(self, "_gs_edit_vid_preview_surf", None)
            if vsurf:
                vs_scaled = pygame.transform.smoothscale(vsurf, (iprev_w, vprev_h))
                self.screen.blit(vs_scaled, vprev_r.topleft)
            else:
                _draw_text(
                    self.screen, self._TR("gs_preview_tag", "[ PREVIEW ]"), "xs", (55, 60, 82),
                    vprev_r.x + iprev_w // 2 - 35, vprev_r.y + vprev_h // 2 - 7
                )

            # ── Sez. C: Playlist musicale ─────────────────────
            _C_Y = _B_Y + 66 + vprev_h + 16
            _draw_text(self.screen, self._TR("gs_step_playlist", "❼  MUSIC PLAYLIST"), "sm", TXT_DIM, c2_x, _C_Y)
            mu_list = getattr(self, "_gs_edit_music_paths", [])
            _mu_label = (f"{len(mu_list)} bran{'o' if len(mu_list)==1 else 'i'} — Gestisci..."
                         if mu_list else "Nessuna traccia — Aggiungi...")
            btn_m_r = pygame.Rect(c2_x, _C_Y + 22, r_col_w, 36)
            _button(self.screen, btn_m_r, _mu_label, _in_rect((mx2, my2), btn_m_r))

            # Riferimenti Y da usare nel click handler (salvati come costanti locali
            # per hitbox allineate — il click handler usa le stesse formule)
            # _A_Y, _B_Y, _C_Y sono variabili locali; le hitbox nel click usano
            # le stesse variabili ri-calcolate identicamente.
            # NB: salviamo i valori calcolati per il click handler nello state
            self._gs_modal_layout = {
                "off_x2": off_x2, "c1_x": c1_x, "c2_x": c2_x,
                "f_w": f_w, "c2_w": c2_w, "r_col_w": r_col_w,
                "_SEC1_Y": _SEC1_Y, "_SEC2_Y": _SEC2_Y, "_SEC3_Y": _SEC3_Y,
                "_SEC4_Y": _SEC4_Y, "_SEC5_Y": _SEC5_Y,
                "_A_Y": _A_Y, "_B_Y": _B_Y, "_C_Y": _C_Y,
                "iprev_h": iprev_h, "cat_r": cat_r,
                "mag_r": mag_r, "btn_icon_r": btn_icon_r,
                "_THEME_INFO": _THEME_INFO,
                "_t_btn_w": _t_btn_w, "_t_btn_h": _t_btn_h, "_t_gap": _t_gap,
                "_theme_grid_y": _theme_grid_y,
            }

        elif self._gs_edit_mode == "scene":
            off_x2 = int(dw * 0.52)
            # Separatore verticale tra le due colonne
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + off_x2 - 14, dy + 62), (dx + off_x2 - 14, dy + dh - 70), 1
            )
            # ── COLONNA 1 (Sinistra): NOME SCENA ────────────────────────────
            _draw_text(self.screen, self._TR("gs_step_scene_name", "1. SCENE NAME AND TRANSLATIONS"), "sm", TXT_DIM, dx + 20, dy + 68)
            f_w = off_x2 - 150
            for i, l in enumerate(self.LANGS):
                fy = dy + 106 + i * _LANG_FIELD_STRIDE
                is_active = (self._gs_edit_active_field == l)
                lbl_col = ACCENT if is_active else TXT_DIM
                _draw_text(self.screen, l.upper(), "sm", lbl_col, dx + 20, fy + 8)
                field_r = pygame.Rect(dx + 90, fy, f_w, _LANG_FIELD_H)
                buf = self._gs_edit_lang_bufs.get(l, "")
                is_all = (is_active and getattr(self, "_gs_edit_all_selected", False))
                cur_pos = self._gs_edit_cursors.get(l, 0) if is_active else None
                _input_box(self.screen, field_r, buf, focused=is_active,
                           hint=f"{l.upper()}...", font="md",
                           all_selected=is_all, cursor_pos=cur_pos)

            # Separatore orizzontale post-campi
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + 20, dy + 106 + len(self.LANGS) * _LANG_FIELD_STRIDE + 6),
                (dx + off_x2 - 30, dy + 106 + len(self.LANGS) * _LANG_FIELD_STRIDE + 6), 1
            )

            # ── COLONNA 2 (Destra): SFONDO SCENA ────────────────────────────
            r_col_w = dw - off_x2 - 40
            path_w = r_col_w - 185

            # Punto 2: Immagine di Sfondo
            _y_img = dy + int(dh * 0.12)
            _draw_text(self.screen, self._TR("gs_step2_bg_image", "2. BACKGROUND IMAGE"), "sm", TXT_DIM, dx + off_x2, _y_img - 28)
            btn_i_r = pygame.Rect(dx + off_x2, _y_img, 160, 34)
            _button(self.screen, btn_i_r, self._TR("gs_choose_image", "Choose image"), _in_rect((mx2, my2), btn_i_r))
            
            ipath = getattr(self, '_gs_edit_bg_path', "")
            path_w = r_col_w - 180
            _rect(self.screen, (20, 22, 30), (dx + off_x2 + 175, _y_img, path_w, 34), radius=6)
            _draw_text(self.screen, Path(ipath).name if ipath else "Nessuna immagine", "xs", TXT_HI if ipath else TXT_DIM, dx+off_x2+185, _y_img+8, path_w - 20)
            
            iprev_w, iprev_h = 320, 180
            iprev_r = pygame.Rect(dx + off_x2, _y_img + 45, iprev_w, iprev_h)
            _rect(self.screen, (10, 12, 18), iprev_r, radius=12); _rect(self.screen, BORDER, iprev_r, 1, radius=12)
            isurf = getattr(self, "_gs_edit_bg_preview_surf", None)
            if isurf:
                is_scaled = pygame.transform.smoothscale(isurf, (iprev_w, iprev_h))
                self.screen.blit(is_scaled, iprev_r.topleft)

            # Punto 3: Video di Sfondo
            _y_vid = dy + int(dh * 0.45)
            _draw_text(self.screen, self._TR("gs_step3_bg_video", "3. BACKGROUND VIDEO"), "sm", TXT_DIM, dx + off_x2, _y_vid - 28)
            btn_v_r = pygame.Rect(dx + off_x2, _y_vid, 160, 34)
            _button(self.screen, btn_v_r, self._TR("gs_choose_video", "Choose video"), _in_rect((mx2, my2), btn_v_r))
            
            vpath = getattr(self, '_gs_edit_vid_path', "")
            _rect(self.screen, (20, 22, 30), (dx + off_x2 + 175, _y_vid, path_w, 34), radius=6)
            _draw_text(self.screen, Path(vpath).name if vpath else "Nessun video", "xs", OK_C if vpath else TXT_DIM, dx+off_x2+185, _y_vid+8, path_w - 20)
            
            vprev_w, vprev_h = 320, 180
            vprev_r = pygame.Rect(dx + off_x2, _y_vid + 45, vprev_w, vprev_h)
            _rect(self.screen, (10, 12, 18), vprev_r, radius=12); _rect(self.screen, BORDER, vprev_r, 1, radius=12)
            vsurf = getattr(self, "_gs_edit_vid_preview_surf", None)
            if vsurf:
                vs_scaled = pygame.transform.smoothscale(vsurf, (vprev_w, vprev_h))
                self.screen.blit(vs_scaled, vprev_r.topleft)

        elif self._gs_edit_mode == "level":
            # ── LAYOUT 2 COLONNE: sinistra=traduzioni, destra=info/stat ──
            off_x2 = int(dw * 0.52)
            # Separatore verticale
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + off_x2 - 14, dy + 62), (dx + off_x2 - 14, dy + dh - 70), 1
            )

            # ── COLONNA 1 (Sinistra): NOME LIVELLO E TRADUZIONI ────────────
            _draw_text(self.screen, self._TR("gs_step_level_name", "1. LEVEL NAME AND TRANSLATIONS"), "sm", TXT_DIM, dx + 30, dy + 68)
            f_w = off_x2 - 150
            for i, l in enumerate(self.LANGS):
                fy = dy + 106 + i * _LANG_FIELD_STRIDE
                is_active = (self._gs_edit_active_field == l)
                lbl_col = ACCENT if is_active else TXT_DIM
                _draw_text(self.screen, l.upper(), "sm", lbl_col, dx + 20, fy + 8)
                field_r = pygame.Rect(dx + 90, fy, f_w, _LANG_FIELD_H)
                buf = self._gs_edit_lang_bufs.get(l, "")
                is_all = (is_active and getattr(self, "_gs_edit_all_selected", False))
                cur_pos = self._gs_edit_cursors.get(l, 0) if is_active else None
                _input_box(self.screen, field_r, buf, focused=is_active,
                           hint=f"{l.upper()}...", font="md",
                           all_selected=is_all, cursor_pos=cur_pos)

            # Separatore orizzontale post-campi
            _sep_y = dy + 106 + len(self.LANGS) * _LANG_FIELD_STRIDE + 10
            pygame.draw.line(
                self.screen, (*BORDER[:3], 60),
                (dx + 20, _sep_y), (dx + off_x2 - 30, _sep_y), 1
            )

            # Hint TAB navigation
            _draw_text(
                self.screen,
                self.lang_manager.get("gs_tip_tab_nav", "TAB → campo successivo  •  Ctrl+A → seleziona tutto"),
                "xs", (80, 85, 105), dx + 20, _sep_y + 12
            )

            # ── COLONNA 2 (Destra): INFO LIVELLO ────────────────────────────
            _draw_text(self.screen, self._TR("gs_step_level_info", "2. LEVEL INFO"), "sm", TXT_DIM, dx + off_x2, dy + 68)

            # Recupera dati livello selezionato
            try:
                _lvl_idx = getattr(self, "gs_sel_level", None)
                _lvl_data = self.gs_cur_levels[_lvl_idx] if _lvl_idx is not None else {}
                _lvl_id = _lvl_data.get("id", "—")
                _lvl_scenes = _lvl_data.get("scenes", [])
                _lvl_cfg = _lvl_data.get("cfg", {})
                _lvl_nk = _lvl_cfg.get("name_key", f"{_lvl_id}_name")
            except Exception:
                _lvl_id = "—"; _lvl_scenes = []; _lvl_nk = "—"

            _info_y = dy + 100
            _info_x = dx + off_x2
            _info_card_w = dw - off_x2 - 40

            # Card ID
            id_card_r = pygame.Rect(_info_x, _info_y, _info_card_w, 52)
            _rect(self.screen, (26, 28, 40), id_card_r, radius=10)
            _rect(self.screen, BORDER, id_card_r, 1, radius=10)
            _draw_text(self.screen, self._TR("gs_level_id", "LEVEL ID"), "xs", TXT_DIM, _info_x + 14, _info_y + 8)
            _draw_text(self.screen, str(_lvl_id), "md", TXT_HI, _info_x + 14, _info_y + 24)

            # Card N. Scene
            sc_card_r = pygame.Rect(_info_x, _info_y + 64, _info_card_w // 2 - 6, 52)
            _rect(self.screen, (26, 28, 40), sc_card_r, radius=10)
            _rect(self.screen, (*ACCENT[:3], 120), sc_card_r, 1, radius=10)
            _draw_text(self.screen, self._TR("gs_card_scenes", "SCENES"), "xs",
                       TXT_DIM, sc_card_r.x + 14, sc_card_r.y + 8)
            _draw_text(self.screen, str(len(_lvl_scenes)), "lg", ACCENT, sc_card_r.x + 14, sc_card_r.y + 22)

            # Card Name Key
            nk_card_r = pygame.Rect(_info_x + _info_card_w // 2 + 6, _info_y + 64, _info_card_w // 2 - 6, 52)
            _rect(self.screen, (26, 28, 40), nk_card_r, radius=10)
            _rect(self.screen, BORDER, nk_card_r, 1, radius=10)
            _draw_text(self.screen, self._TR("gs_card_name_key", "NAME KEY"), "xs",
                       TXT_DIM, nk_card_r.x + 14, nk_card_r.y + 8)
            _draw_text(self.screen, str(_lvl_nk), "sm", TXT, nk_card_r.x + 14, nk_card_r.y + 24,
                       max_w=nk_card_r.width - 20)

            # Lista scene del livello (preview compatta)
            _list_y = _info_y + 132
            _draw_text(self.screen, self._TR("gs_scenes_in_level", "SCENES IN THE LEVEL"), "xs", TXT_DIM, _info_x, _list_y - 18)
            _list_r = pygame.Rect(_info_x, _list_y, _info_card_w, dh - (_list_y - dy) - 80)
            _rect(self.screen, (22, 24, 34), _list_r, radius=8)
            _rect(self.screen, BORDER, _list_r, 1, radius=8)
            self.screen.set_clip(_list_r)
            for _si, _scn in enumerate(_lvl_scenes[:20]):
                _sname = Path(_scn.get("path", str(_si))).name if isinstance(_scn, dict) else str(_scn)
                _sy = _list_r.y + 8 + _si * 24
                _row_r = pygame.Rect(_list_r.x + 4, _sy, _list_r.width - 8, 22)
                if _si % 2 == 0:
                    _rect(self.screen, (28, 30, 44), _row_r, radius=4)
                _draw_text(self.screen, f"{_si + 1:02d}. {_sname}", "sm", TXT,
                           _list_r.x + 14, _sy + 3, max_w=_list_r.width - 22)
            if not _lvl_scenes:
                _draw_text(self.screen,
                           self.lang_manager.get("gs_level_no_scenes", "Nessuna scena in questo livello"),
                           "sm", (60, 65, 85), _list_r.x + 14, _list_r.y + 14)
            self.screen.set_clip(None)

        # ── FOOTER: Pulsanti azione — altezza 40px per hitbox più generosa ──
        btn_y = dy + dh - 64
        ok_r = pygame.Rect(dx + 20, btn_y, 220, 40)
        esc_r = pygame.Rect(dx + dw - 240, btn_y, 220, 40)
        _button(self.screen, ok_r, self.lang_manager.get("gs_btn_save", "SALVA MODIFICHE"),
                _in_rect((mx2, my2), ok_r), active=True)
        if self._gs_edit_mode == "game":
            del_r = pygame.Rect(dx + 260, btn_y, 220, 40)
            stage = getattr(self, "_gs_edit_del_stage", 0)
            _button(self.screen, del_r,
                    self.lang_manager.get(f"gs_btn_edit_del_{stage}", "ELIMINA PROGETTO"),
                    _in_rect((mx2, my2), del_r), danger=True)
        _button(self.screen, esc_r, self.lang_manager.get("gs_btn_cancel", "ANNULLA"),
                _in_rect((mx2, my2), esc_r))

        if self._gs_edit_mode == "game" and getattr(self, "_gs_edit_cat_dropdown", False):
            if hasattr(self, "_gs_modal_layout"):
                _SEC2_Y = self._gs_modal_layout["_SEC2_Y"]
                c1_x = self._gs_modal_layout["c1_x"]
                _cur_cat = getattr(self, "_gs_edit_category", "desktop")
                opt_d = pygame.Rect(c1_x, _SEC2_Y + 22 + 34, 260, 34)
                opt_a = pygame.Rect(c1_x, _SEC2_Y + 22 + 68, 260, 34)
                _button(self.screen, opt_d, self._TR("gs_platform_desktop", "DESKTOP"), _in_rect((mx2, my2), opt_d), active=(_cur_cat == "desktop"))
                _button(self.screen, opt_a, self._TR("gs_platform_android", "ANDROID"), _in_rect((mx2, my2), opt_a), active=(_cur_cat == "android"))


# ─────────────────────────────────────────────────────────────────────────────
# MODALE PROGRESSO EXPORT HTML (stack modale unificato)
# ─────────────────────────────────────────────────────────────────────────────

# Geometria del modale di progresso export
_WX_W, _WX_H = 560, 390
_WX_PAD = 20
_WX_BAR_H = 18
_WX_LOG_LINES = 8          # ultimi N messaggi mostrati
_WX_LOG_LINE_H = 18
_WX_BTN_W, _WX_BTN_H = 130, 30
_WX_BTN_GAP = 10
_WX_OVERLAY_ALPHA = 150
_WX_STEP_MAX_CHARS = 78    # troncamento testo step corrente
_WX_LOG_MAX_CHARS = 92     # troncamento righe di log
_WX_ERR_MAX_CHARS = 70     # troncamento messaggio d'errore nell'esito


class _WebExportProgressModal:
    """Modale di progresso NON bloccante per l'export HTML.

    Protocollo dello stack modale unificato: handle_event(editor, ev) -> bool
    e render(editor). L'export gira in un thread daemon che NON tocca pygame:
    comunica con il main thread solo tramite campi di tipo semplice e una
    deque (append thread-safe) letti dal render ad ogni frame.

    Annulla: imposta un flag; la progress_cb (eseguita nel thread di export)
    lo vede alla tappa successiva e solleva ExportCancelled, che il worker
    cattura per una interruzione pulita. A export finito il modale mostra
    l'esito con i bottoni Chiudi e Apri cartella.
    """

    def __init__(self, editor, game_id: str, output_dir: Path) -> None:
        self._editor = editor
        self.game_id = game_id
        self.output_dir = Path(output_dir)

        # Stato condiviso con il thread di export (scritture atomiche sotto GIL)
        self._log: deque = deque(maxlen=_WX_LOG_LINES)
        self._step: str = "Avvio export..."
        self._frac: float = 0.0
        self._done: bool = False
        self._result: "dict | None" = None
        self._error: "str | None" = None
        self._cancel_requested: bool = False
        self._cancelled: bool = False

        self.btn_cancel = Button((0, 0, _WX_BTN_W, _WX_BTN_H), "Annulla",
                                 self._request_cancel, danger=True)
        self.btn_open = Button((0, 0, _WX_BTN_W, _WX_BTN_H), "Apri cartella",
                               self._open_folder)
        self.btn_close = Button((0, 0, _WX_BTN_W, _WX_BTN_H), "Chiudi",
                                lambda: self._close(editor))
        self.group = WidgetGroup([self.btn_cancel, self.btn_open, self.btn_close])

        self._thread = threading.Thread(
            target=self._worker, daemon=True, name=f"web-export-{game_id}")
        self._thread.start()

    # ── Thread di export (NIENTE pygame qui dentro) ──────────────────────────

    def _worker(self) -> None:
        from editor.web_exporter import export_web_game, ExportCancelled
        try:
            self._result = export_web_game(
                self.game_id, self.output_dir, self._editor.base_path,
                progress_cb=self._on_progress)
        except ExportCancelled:
            self._cancelled = True
            logger.info(f"Export HTML annullato dall'utente: {self.game_id}")
        except Exception as e:
            logger.exception(f"Errore esportazione HTML: {e}")
            self._error = str(e)
        finally:
            self._done = True

    def _on_progress(self, msg: str, frac: float) -> None:
        """progress_cb per export_web_game: eseguita nel thread di export."""
        from editor.web_exporter import ExportCancelled
        if self._cancel_requested:
            raise ExportCancelled(f"Export di '{self.game_id}' annullato")
        self._step = msg
        # Clamp + monotonia: la barra non torna mai indietro
        self._frac = max(self._frac, min(1.0, max(0.0, frac)))
        self._log.append(msg)

    # ── Azioni bottoni (main thread) ─────────────────────────────────────────

    def _request_cancel(self) -> None:
        if not self._done and not self._cancel_requested:
            self._cancel_requested = True
            self._step = "Annullamento in corso..."

    def _open_folder(self) -> None:
        try:
            os.startfile(str(self.output_dir))
        except OSError as e:
            logger.error(f"Apertura cartella export fallita: {e}")
            self._editor._status(self._editor._TR(
                "gs_open_folder_error",
                "Cannot open the folder: {0}").format(e), ERR_C, 4)

    def _close(self, editor) -> None:
        editor._modal_pop(self)
        if self._result and self._result.get("success"):
            lvls = self._result.get("levels", 0)
            scenes = self._result.get("scenes", 0)
            editor._status(
                editor._TR(
                    "gs_html_exported",
                    "HTML exported: {0} ({1} levels, {2} scenes) -> build_web/{3}"
                ).format(self.game_id, lvls, scenes, self.game_id),
                OK_C, 5)
        elif self._cancelled:
            editor._status(editor._TR(
                "gs_export_cancelled",
                "HTML export cancelled: {0}").format(self.game_id), WARN_C, 3)
        else:
            editor._status(editor._TR(
                "gs_export_failed",
                "HTML export failed: {0}").format(self.game_id), ERR_C, 4)

    # ── Layout / eventi / render (main thread) ───────────────────────────────

    def _layout(self, w_win: int, h_win: int) -> pygame.Rect:
        panel = pygame.Rect((w_win - _WX_W) // 2, (h_win - _WX_H) // 2,
                            _WX_W, _WX_H)
        by = panel.bottom - _WX_PAD - _WX_BTN_H
        bx_right = panel.right - _WX_PAD - _WX_BTN_W
        self.btn_cancel.rect.update(bx_right, by, _WX_BTN_W, _WX_BTN_H)
        self.btn_close.rect.update(bx_right, by, _WX_BTN_W, _WX_BTN_H)
        self.btn_open.rect.update(bx_right - _WX_BTN_W - _WX_BTN_GAP, by,
                                  _WX_BTN_W, _WX_BTN_H)
        running = not self._done
        self.btn_cancel.visible = running
        self.btn_cancel.enabled = running and not self._cancel_requested
        self.btn_close.visible = self._done
        self.btn_open.visible = self._done and self.output_dir.exists()
        return panel

    def handle_event(self, editor, ev) -> bool:
        self._layout(*editor.screen.get_size())
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self._done:
                self._close(editor)
            else:
                self._request_cancel()
            return True
        self.group.handle_event(ev)
        return True  # app-modal: consuma comunque l'input utente

    def render(self, editor) -> None:
        screen = editor.screen
        w_win, h_win = screen.get_size()
        panel = self._layout(w_win, h_win)

        overlay = pygame.Surface((w_win, h_win), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, _WX_OVERLAY_ALPHA))
        screen.blit(overlay, (0, 0))
        _rect(screen, PANEL, panel, radius=8)
        _rect(screen, BORDER, panel, 1, radius=8)

        _draw_text(screen, self._editor._TR(
                       "gs_export_html_title",
                       "HTML export - {0}").format(self.game_id), "md", TXT_HI,
                   panel.x + _WX_PAD, panel.y + _WX_PAD)

        # Step corrente + percentuale (snapshot dei campi scritti dal thread)
        step = self._step
        frac = self._frac
        step_y = panel.y + 56
        _draw_text(screen, step[:_WX_STEP_MAX_CHARS], "sm", TXT,
                   panel.x + _WX_PAD, step_y)
        pct = f"{int(frac * 100)}%"
        pct_w, _ = _text_wh(pct, "sm")
        _draw_text(screen, pct, "sm", TXT_DIM,
                   panel.right - _WX_PAD - pct_w, step_y)

        # Barra di progresso determinata
        bar = pygame.Rect(panel.x + _WX_PAD, step_y + 26,
                          _WX_W - _WX_PAD * 2, _WX_BAR_H)
        _rect(screen, (30, 32, 42), bar, radius=6)
        if self._error:
            bar_color = ERR_C
        elif self._cancelled:
            bar_color = WARN_C
        elif self._done:
            bar_color = OK_C
        else:
            bar_color = ACCENT
        fill_w = int(round(bar.w * frac))
        if fill_w > 0:
            _rect(screen, bar_color, (bar.x, bar.y, fill_w, bar.h), radius=6)
        _rect(screen, BORDER, bar, 1, radius=6)

        # Ultimi messaggi (list() su deque: copia atomica sotto GIL)
        log_y = bar.bottom + 14
        _draw_text(screen, "LOG", "xs", TXT_DIM, panel.x + _WX_PAD, log_y)
        y = log_y + _WX_LOG_LINE_H
        for msg in list(self._log):
            _draw_text(screen, msg[:_WX_LOG_MAX_CHARS], "xs", TXT_DIM,
                       panel.x + _WX_PAD, y)
            y += _WX_LOG_LINE_H

        # Esito finale
        if self._done:
            if self._result and self._result.get("success"):
                esito = (f"Completato: {self._result.get('levels', 0)} livelli, "
                         f"{self._result.get('scenes', 0)} scene, "
                         f"{self._result.get('objects', 0)} oggetti")
                col = OK_C
            elif self._cancelled:
                esito, col = "Annullato dall'utente", WARN_C
            else:
                esito = f"Errore: {(self._error or '?')[:_WX_ERR_MAX_CHARS]}"
                col = ERR_C
            _draw_text(screen, esito, "sm", col, panel.x + _WX_PAD,
                       panel.bottom - _WX_PAD - _WX_BTN_H - 28)

        self.group.draw(screen)
