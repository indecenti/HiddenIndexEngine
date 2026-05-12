"""
editor/mixins/game_select.py

GameSelectMixin — schermata di selezione gioco/livello/scena:
                  logica, eventi, rendering dashboard.
"""

import sys
import os
import shutil
import time
import json
import subprocess
import tempfile
import logging
import pygame
from pathlib import Path

from editor.constants import (
    TOP_BAR_H, STATE_MAIN,
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
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
from engine.utils import get_base_path, get_logger

logger = get_logger("game_select")


class GameSelectMixin:
    """Dashboard selezione progetto (3 colonne) + dialogo creazione."""

    # ─────────────────────────────────────────────────────────────────────────
    # COMPILAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_compile_game(self, idx: int):
        """Avvia la compilazione e il packaging di un gioco."""
        if idx is None or idx >= len(self.gs_games):
            self._status("Errore: gioco non valido", ERR_C, 2)
            return

        game_id = self.gs_games[idx]
        game_path = self.base_path / "games" / game_id
        game_config_path = game_path / "game_config.json"

        if not game_config_path.exists():
            self._status(f"Errore: game_config.json non trovato per '{game_id}'", ERR_C, 3)
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

        self._status(f"Avvio compilazione: {game_id} v{version}...", WARN_C, 2)

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
            self._status(f"Finestra build aperta: {game_id} v{version}", OK_C, 3)

        except Exception as e:
            logger.exception(f"Errore lancio subprocess: {e}")
            self._status(f"Errore: {str(e)}", ERR_C, 4)

    def _gs_run_game(self, idx: int):
        """Avvia il gioco in modalità standalone."""
        if idx is None or idx >= len(self.gs_games):
            self._status("Errore: gioco non valido", ERR_C, 2)
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
            self._status(f"Avvio standalone: {game_id}", OK_C, 2)
            logger.info(f"Gioco standalone avviato: {game_id}")
        except Exception as e:
            logger.exception(f"Errore avvio gioco Standalone: {e}")
            self._status(f"Errore: {str(e)}", ERR_C, 4)

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
        self._status(f"Gioco: {gname}", OK_C, 2)

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
            self._status("Seleziona prima un gioco", WARN_C, 3); return
            
        # Attivazione overlay di caricamento
        self._loading = True
        self._render()
        pygame.display.flip()
        
        # Forza l'OS ad elaborare il refresh grafico prima di saturare la CPU col caricamento
        pygame.event.pump()
        pygame.time.delay(10) 
        
        try:
            # Operazioni di caricamento lente (I/O, surface conversion)
            gname = self.gs_games[self.gs_sel_game]
            
            # Pump eventi per evitare "Not Responding" su caricamenti lunghi
            pygame.event.pump()
            self._load_game(gname)
            
            # Refresh overlay tra gioco e scena (lo stato potrebbe essere cambiato)
            self._render()
            pygame.display.flip()
            pygame.event.pump()
            
            if self.gs_sel_scene is not None:
                self._load_scene(self.gs_cur_scenes[self.gs_sel_scene])
            elif self.gs_cur_scenes:
                self._load_scene(self.gs_cur_scenes[0])
        except Exception as e:
            logging.error(f"Errore durante il caricamento: {e}")
            self._status(f"Errore caricamento: {e}", ERR_C, 5)
        finally:
            # Disattivazione overlay garantita
            self._loading = False
            # Forza un ultimo render pulito
            self._render()
            pygame.display.flip()

    # ─────────────────────────────────────────────────────────────────────────
    # CREAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_new_game(self):
        self._gs_new_mode = "game"
        self._gs_new_buf  = "nuovo_gioco"
        self._gs_new_bg_path = ""
        self._gs_new_vid_path = ""
        self._gs_new_bg_preview_surf = None
        self._gs_new_vid_preview_surf = None
        self._gs_new_music_paths = []

    def _gs_new_level(self):
        if self.gs_sel_game is None: return
        self._gs_new_mode = "level"
        self._gs_new_buf  = "level_nuovo"

    def _gs_new_scene(self):
        if self.gs_sel_level is None: return
        self._gs_new_mode = "scene"
        self._gs_new_buf  = "scene_nuova"
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

    def _gs_get_human_name(self, mode, idx):
        """Recupera il nome tradotto per un elemento della dashboard con caricamento on-the-fly."""
        lang = getattr(self, "current_lang", "it")
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
        """Recupera una stringa specifica per una lingua da un gioco."""
        p = self.base_path / "games" / game_id / "strings" / f"{lang}.json"
        if p.exists():
            try:
                data = _load_json(p)
                return data.get(key, fallback)
            except: pass
        return fallback

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
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
        self._gs_edit_del_stage = 0
        
        self._gs_edit_bg_path = ""
        self._gs_edit_vid_path = ""
        self._gs_edit_bg_preview_surf = None
        self._gs_edit_vid_preview_surf = None
        self._gs_edit_music_paths = []

        # Carica musica esistente se presente
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
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]

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
        self._gs_edit_active_field = self.current_lang
        self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
        
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
        """Conferma e persiste le modifiche dal dialog di editing (ID, Titolo, Assets)."""
        import re, shutil, tempfile, gc, configparser
        from pathlib import Path
        
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except: pass
        
        raw_name = self._gs_edit_buf.strip()
        if not raw_name:
            self._gs_edit_mode = None; return

        clean_id = re.sub(r'[^\w\-]', '_', raw_name.replace(" ", "_"))

        try:
            # Sincronizzazione Path Editor
            def sync_editor_state(old_p: Path, new_p: Path):
                if self.game_path and (self.game_path == old_p or old_p in self.game_path.parents):
                    rel = self.game_path.relative_to(old_p)
                    self.game_path = new_p / rel
                    self.game_name = self.game_path.name
                if self.scene_path and (self.scene_path == old_p or old_p in self.scene_path.parents):
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
                    except:
                        shutil.copytree(old_p, new_p, dirs_exist_ok=True)
                        try: shutil.rmtree(old_p)
                        except: pass
                    
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
                            except: pass
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
                    except: pass
                cfg["menu"]["music"] = music_list
                _save_json(cfg_p, cfg)

                # --- PULIZIA AUTOMATICA FILE MUSICA NON USATI (Richiesta User) ---
                used_in_scenes = self._gs_get_used_music(new_p)
                menu_music = {Path(m).name for m in music_list}
                all_active_music = used_in_scenes.union(menu_music)
                
                audio_dir = new_p / "audio" / "music"
                if audio_dir.exists():
                    for f in audio_dir.glob("*.mp3"):
                        if f.name not in all_active_music:
                            try:
                                logger.info(f"Pulizia musica inutilizzata: {f.name}")
                                f.unlink()
                            except Exception as e:
                                logger.error(f"Errore eliminazione file inutilizzato {f.name}: {e}")
                for l, val in getattr(self, "_gs_edit_lang_bufs", {}).items():
                    self._gs_update_strings(clean_id, {t_key: val}, lang=l)
                
                for it in self.recent_scenes:
                    if it.get("game") == old_id:
                        it["game"] = clean_id
                        it["path"] = it["path"].replace(str(old_p), str(new_p))
                _save_json(self.base_path / ".editor_settings.json", {"recent_scenes": self.recent_scenes})

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
                        
                        # Pulizia vecchia risorsa scena (IMG <-> VID)
                        if old_s and old_s != p.name:
                            old_p_del = (scn_p / old_s).resolve()
                            new_p_check = dst.resolve()
                            
                            if old_p_del.exists() and old_p_del != new_p_check:
                                try:
                                    logger.info(f"Pulizia asset scena: {old_p_del}")
                                    old_p_del.unlink(missing_ok=True)
                                except: pass

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
                            except: pass
                    sd["background"] = ""
                
                _save_json(scn_p / "scene.json", sd)
                for l, val in getattr(self, "_gs_edit_lang_bufs", {}).items():
                    self._gs_update_strings(gname, {nk: val}, lang=l)

            self._load_strings()
            self._gs_refresh_cache()
            self._status(f"'{raw_name}' salvato con successo", OK_C, 2)
        except Exception as e:
            logger.exception("Errore aggiornamento")
            self._status("Errore salvataggio info", ERR_C, 4)
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
                    except: pass
        return used

    def _gs_update_strings(self, game_id: str, new_data: dict, remove_keys: list = None, lang: str = None):
        """Helper per aggiornare traduzioni. Se lang è specificata, aggiorna solo quel file."""
        s_dir = self.base_path / "games" / game_id / "strings"
        if not s_dir.exists(): return
        
        target_files = [s_dir / f"{lang}.json"] if lang else s_dir.glob("*.json")
        for sf in target_files:
            if not sf.exists(): continue
            data = _load_json(sf)
            if remove_keys:
                for k in remove_keys:
                    if k and k in data: del data[k]
            data.update(new_data)
            _save_json(sf, data)


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
            except: pass
            
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
                    except: pass
            
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
                except: pass

    def _gs_confirm_new(self):
        # Rilascia audio per evitare WinError 32 su Windows
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except: pass
        
        name = self._gs_new_buf.strip().replace(" ", "_")
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
                    self._status(f"Errore copia video: {e}", ERR_C)
            elif bg_path and Path(bg_path).exists():
                p = Path(bg_path)
                target_name = f"menu_bg{p.suffix}"
                target_path = gpath / "assets" / target_name
                try:
                    shutil.copy2(bg_path, target_path)
                    final_bg_path = f"assets/{target_name}"
                except Exception as e:
                    self._status(f"Errore copia asset: {e}", ERR_C)
            
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
                        except: pass

            _save_json(gpath / "game_config.json",
                       {
                           "id": name, 
                           "game_id": name, # Compatibilità
                           "title_key": "game_title", 
                           "version": "1.0",
                           "menu": {
                               "background": final_bg_path,
                               "music": music_list
                           }
                       })
            
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
            langs = [f.stem for f in engine_strings_dir.glob("*.json")] if engine_strings_dir.exists() else ["it", "en"]
            
            for lang in langs:
                # Carica traduzioni globali dall'engine
                eng_p = engine_strings_dir / f"{lang}.json"
                eng_data = {}
                if eng_p.exists():
                    try:
                        with open(eng_p, "r", encoding="utf-8-sig") as f:
                            eng_data = json.load(f)
                    except: pass
                
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
                self._status(f"Errore: Livello '{name}' gia' esistente", ERR_C, 4); return
            lpath.mkdir(parents=True, exist_ok=False)
            _save_json(lpath / "level_config.json",
                       {"id": name, "name_key": f"{name}_name",
                        "difficulty": "normal", "timer_behavior": "complete",
                        "scenes": []})
            self._gs_select_game(self.gs_sel_game)
            idx = next((i for i, l in enumerate(self.gs_cur_levels) if l["id"] == name), 0)
            self._gs_select_level(idx)

        elif self._gs_new_mode == "scene":
            gname = self.gs_games[self.gs_sel_game]
            lvl   = self.gs_cur_levels[self.gs_sel_level]
            spath = lvl["path"] / name
            if spath.exists():
                self._status(f"Errore: Scena '{name}' gia' esistente", ERR_C, 4); return
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
                    self._status(f"Errore copia asset scena: {e}", ERR_C)

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
            if p.is_dir():
                shutil.rmtree(p)
            self._status(f"Eliminato: {self._gs_del_name}", WARN_C, 3)
            if self._gs_del_mode == "level":
                # Pulisce i progetti recenti che contengono questo livello
                lp = str(self._gs_del_path)
                self.recent_scenes = [r for r in self.recent_scenes if lp not in r.get("path", "")]
                _save_json(Path(".editor_settings.json"), {"recent_scenes": self.recent_scenes})

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
                _save_json(Path(".editor_settings.json"), {"recent_scenes": self.recent_scenes})

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
                _save_json(Path(".editor_settings.json"), {"recent_scenes": self.recent_scenes})

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
            self._status(f"Errore: {exc}", ERR_C, 4)
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
            current_ids[idx], current_ids[idx+delta] = current_ids[idx+delta], current_ids[idx]
            
            g_cfg["levels"] = current_ids
            if _save_json(g_cfg_p, g_cfg):
                logger.info(f"Ordine livelli aggiornato per {gname}: {current_ids}")
            
            self.gs_cur_levels = _discover_levels(self.game_path)
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
            
            # Refresh dei dati
            self.gs_cur_levels = _discover_levels(self.game_path)
            self._gs_select_level(self.gs_sel_level)
            self.gs_sel_scene = idx + delta
            self._gs_refresh_cache(2)

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _gs_click(self, mx, my_raw):
        w, h = self.screen.get_size()
        
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
            dw, dh = 800, 750 if self._gs_new_mode == "game" else (450 if self._gs_new_mode == "scene" else 220)
            dx, dy = (w-dw)//2, (h-dh)//2
            
            # Bottone X chiusura (in alto a destra)
            xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
            if _in_rect((mx, my_raw), xr):
                self._gs_new_mode = None; return
            
            if self._gs_new_mode in ("game", "scene"):
                # Hitbox Sfondo Immagine (Y=155)
                if _in_rect((mx, my_raw), (dx + 20, dy + 155, 160, 34)):
                    self._bg_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new")
                    return
                # Hitbox Sfondo Video (Y=295)
                if _in_rect((mx, my_raw), (dx + 20, dy + 295, 160, 34)):
                    self._vid_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new")
                    return
                # Hitbox Preview Video Play (Nuovo Progetto) - Sempre attiva se vpath esiste
                vpath = getattr(self, '_gs_new_vid_path', "")
                vprev_r = pygame.Rect(dx+580, dy+295-20, 200, 112)
                if vpath and _in_rect((mx, my_raw), vprev_r):
                    self._vid_modal_open(context="game_new" if self._gs_new_mode == "game" else "scene_new", autoplay_path=vpath)
                    return
                # Hitbox Musica (Y=435)
                if self._gs_new_mode == "game":
                    if _in_rect((mx, my_raw), (dx + 20, dy + 435, dw - 40, 34)):
                        self._music_modal_open(context="game_new"); return

            btn_y = dy + dh - 60
            if _in_rect((mx, my_raw), (dx + 20, btn_y, 210, 34)): self._gs_confirm_new(); return
            elif _in_rect((mx, my_raw), (dx + dw - 230, btn_y, 210, 34)): self._gs_new_mode = None; return
            return
        
        # 2. PRIORITÀ: Click dentro dialog "Modifica" (se aperto)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            dh = 950 if self._gs_edit_mode == "game" else (850 if self._gs_edit_mode == "scene" else 600)
            dw = 1000
            dx, dy = (w-dw)//2, (h-dh)//2
            
            # Bottone X chiusura (in alto a destra)
            xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
            if _in_rect((mx, my_raw), xr):
                self._gs_edit_mode = None; return
            
            # Hitbox campi lingua (5 campi)
            for i, l in enumerate(self.LANGS):
                field_r = (dx + 120, dy + 75 + i*32, dw - 140, 28)
                if _in_rect((mx, my_raw), field_r):
                    self._gs_edit_active_field = l
                    self._gs_edit_buf = self._gs_edit_lang_bufs[l]
                    return

            if self._gs_edit_mode in ("game", "scene"):
                off_img = 210 # Sotto le traduzioni
                # Hitbox Sfondo Immagine
                if _in_rect((mx, my_raw), (dx + 20, dy + 75 + off_img, 160, 34)):
                    self._bg_modal_open(context="game_edit" if self._gs_edit_mode == "game" else "scene_edit")
                    return
                
                off_vid = 380 # Sotto l'immagine
                # Hitbox Sfondo Video
                if _in_rect((mx, my_raw), (dx + 20, dy + 75 + off_vid, 160, 34)):
                    self._vid_modal_open(context="game_edit" if self._gs_edit_mode == "game" else "scene_edit")
                    return
                
                vpath = getattr(self, '_gs_edit_vid_path', "")
                vprev_r = pygame.Rect(dx+680, dy + 75 + off_vid - 20, 280, 157) # Preview più grande
                if vpath and _in_rect((mx, my_raw), vprev_r):
                    self._vid_modal_open(context="game_edit" if self._gs_edit_mode == "game" else "scene_edit", autoplay_path=vpath)
                    return
                
                if self._gs_edit_mode == "game":
                    # Hitbox Musica (Y ricalcolato)
                    my = dy + 650
                    if _in_rect((mx, my_raw), (dx + 20, my, dw - 100, 34)):
                        self._music_modal_open(context="game_edit"); return
                    mu_list = getattr(self, "_gs_edit_music_paths", [])
                    for i in range(min(8, len(mu_list) - self.gs_edit_mu_scroll)):
                        idx = self.gs_edit_mu_scroll + i
                        row_x = dx + 20 + (dw - 40) - 32
                        row_y = my + 45 + 10 + i*18
                        if _in_rect((mx, my_raw), (row_x, row_y, 18, 18)):
                            mu_list.pop(idx); self._status("Brano rimosso", WARN_C, 2); return
                    if _in_rect((mx, my_raw), (dx + dw - 70, my, 50, 34)):
                        self._gs_edit_music_paths = []; self._status("Playlist svuotata", ERR_C, 2); return

            btn_y = dy + dh - 60
            if _in_rect((mx, my_raw), (dx + 20, btn_y, 210, 34)): self._gs_confirm_edit(); return
            
            # Pulsante ELIMINA (Tripla conferma interna)
            if self._gs_edit_mode == "game":
                del_r = pygame.Rect(dx + 250, btn_y, 210, 34)
                if _in_rect((mx, my_raw), del_r):
                    self._gs_edit_del_stage = getattr(self, "_gs_edit_del_stage", 0) + 1
                    if self._gs_edit_del_stage >= 3:
                        gname = self.gs_games[self.gs_sel_game]
                        self._gs_del_mode = "game"
                        self._gs_del_path = self.base_path / "games" / gname
                        self._gs_del_name = gname
                        self._gs_del_stage = 2
                        self._gs_confirm_delete()
                        self._gs_edit_mode = None
                    return

            if _in_rect((mx, my_raw), (dx + dw - 230, btn_y, 210, 34)): self._gs_edit_mode = None; return
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
                # Bottone COMPILA (solo per i==0, colonna giochi)
                if i == 0:
                    build_r = (cx2 + col_w - 62, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), build_r):
                        if self.gs_sel_game is not None:
                            self._gs_compile_game(self.gs_sel_game)
                        else:
                            self._status("Seleziona prima un gioco", WARN_C, 2)
                        return

                if i in (1, 2):
                    del_r = (cx2 + col_w - 62, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), del_r):
                        sel = self.gs_sel_level if i == 1 else self.gs_sel_scene
                        if sel is None: self._status("Seleziona prima un elemento", WARN_C, 2)
                        elif i == 1: self._gs_del_level(sel)
                        else: self._gs_del_scene(sel)
                        return
                        
                if i == 0:
                    del_r = (cx2 + col_w - 122, cy2 + 5, 26, 24)
                    if _in_rect((mx, my_raw), del_r):
                        if self.gs_sel_game is not None:
                            self._gs_del_game(self.gs_sel_game)
                        else:
                            self._status("Seleziona prima un gioco", WARN_C, 2)
                        return

                # Clic su Modifica (✎) — offset aggiornato per i==0 (ora sposto il bottone)
                edit_off = -92 if i == 0 else -92
                edit_r = (cx2 + col_w + edit_off, cy2 + 5, 26, 24)
                if _in_rect((mx, my_raw), edit_r):
                    sel = self.gs_sel_game if i == 0 else (self.gs_sel_level if i == 1 else self.gs_sel_scene)
                    if sel is None: self._status("Seleziona prima un elemento", WARN_C, 2)
                    elif i == 0: self._gs_edit_game(sel)
                    elif i == 1: self._gs_edit_level(sel)
                    else: self._gs_edit_scene(sel)
                    return
                iy     = cy2 + 35
                ITEM_H = 34
                scroll_offset = [self.gs_scroll_game, self.gs_scroll_lvl, self.gs_scroll_scn][i]
                idx = (my_raw - iy + scroll_offset * ITEM_H) // ITEM_H
                if idx < 0: return
                if i == 0 and idx < len(self.gs_games): 
                    # Coordinate bottoni riga Giochi
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    if (cy2 + 35 <= my_raw <= cy2 + col_h):
                        btn_w = 24
                        bx_play = cx2 + col_w - 38
                        if _in_rect((mx, my_raw), (bx_play, item_y + 5, btn_w, 24)):
                            self._gs_run_game(idx)
                            return
                    self._gs_select_game(idx)
                elif i == 1 and idx < len(self.gs_cur_levels): 
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    if not (cy2 + 35 <= my_raw <= cy2 + col_h):
                        return
                    
                    btn_w = 24
                    bx_down = cx2 + col_w - 58
                    bx_up   = cx2 + col_w - 86
                    
                    if idx > 0 and _in_rect((mx, my_raw), (bx_up, item_y + 5, btn_w, 24)):
                        self._gs_move_level(idx, -1); return
                        
                    if idx < len(self.gs_cur_levels)-1 and _in_rect((mx, my_raw), (bx_down, item_y + 5, btn_w, 24)):
                        self._gs_move_level(idx, 1); return

                    self._gs_select_level(idx)
                elif i == 2 and idx < len(self.gs_cur_scenes):
                    # Click su bottoni specifici della riga
                    item_y = iy + idx * ITEM_H - scroll_offset * ITEM_H
                    
                    # Verifica che il click sia dentro l'area visibile della colonna
                    if not (cy2 + 35 <= my_raw <= cy2 + col_h):
                        return
                    
                    # Coordinate bottoni (allineati a destra)
                    btn_w = 24
                    bx_open = cx2 + col_w - 30
                    bx_down = cx2 + col_w - 58
                    bx_up   = cx2 + col_w - 86
                    
                    if _in_rect((mx, my_raw), (bx_open, item_y + 5, btn_w, 24)):
                        self._gs_select_scene(idx)
                        self._request_nav(self._gs_open); return
                    
                    if idx > 0 and _in_rect((mx, my_raw), (bx_up, item_y + 5, btn_w, 24)):
                        self._gs_move_scene(idx, -1); return
                        
                    if idx < len(self.gs_cur_scenes)-1 and _in_rect((mx, my_raw), (bx_down, item_y + 5, btn_w, 24)):
                        self._gs_move_scene(idx, 1); return

                    # Click generico sulla riga -> Solo selezione
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
            if col_idx == 0 and self.gs_sel_game  is not None: self._request_nav(self._gs_open)
            if col_idx == 1 and self.gs_sel_level is not None: self._request_nav(self._gs_open)
            if col_idx == 2 and self.gs_sel_scene is not None: self._request_nav(self._gs_open)
            
        self._gs_last_click = now
        self._gs_last_col   = col_idx

    def _gs_wheel(self, ev):
        mx, my_raw = pygame.mouse.get_pos()
        w, h = self.screen.get_size()
        col_w = (w - 80) // 3
        y_browser = 80 + 30 + 200 + 25
        
        # Priorità: Scroll Playlist in Dialog Modifica (se aperto)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode == "game":
            dh, dw = 950, 1000
            dx, dy = (w-dw)//2, (h-dh)//2
            my = dy + 650
            list_r = pygame.Rect(dx+20, my+45, dw-40, 150)
            if list_r.collidepoint(mx, my_raw):
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
                item_count = [len(self.gs_games), len(self.gs_cur_levels), len(self.gs_cur_scenes)][i]
                # Modificata logica per consentire scorrimento quando l'ultimo item è parzialmente coperto
                max_scroll = max(0, item_count - vis_count)
                
                if i == 0: self.gs_scroll_game = max(0, min(max_scroll, self.gs_scroll_game - ev.y))
                elif i == 1: self.gs_scroll_lvl = max(0, min(max_scroll, self.gs_scroll_lvl - ev.y))
                elif i == 2: self.gs_scroll_scn = max(0, min(max_scroll, self.gs_scroll_scn - ev.y))
                return

        # Scroll per lista musica nel dialog Edit Game
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode == "game":
            dw, dh = 1000, 950
            dx, dy = (w-dw)//2, (h-dh)//2
            mu_r = pygame.Rect(dx+20, dy + 650 + 45, dw-40, 150)
            if _in_rect((mx, my_raw), mu_r):
                mu_list = getattr(self, "_gs_edit_music_paths", [])
                max_s = max(0, len(mu_list) - 8)
                self.gs_edit_mu_scroll = max(0, min(max_s, self.gs_edit_mu_scroll - ev.y))

    def _gs_key(self, ev):
        # Dialog conferma eliminazione — ha priorità su tutto
        if self._gs_del_mode:
            if ev.key == pygame.K_RETURN:
                self._gs_confirm_delete()
            elif ev.key == pygame.K_ESCAPE:
                self._gs_del_mode = None
                self._gs_del_path = None
                self._gs_del_name = ""
            return
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            if ev.key == pygame.K_RETURN:
                self._gs_confirm_edit()
            elif ev.key == pygame.K_ESCAPE:
                self._gs_edit_mode = None
                self._gs_edit_buf  = ""
            elif ev.key == pygame.K_BACKSPACE:
                lb = self._gs_edit_lang_bufs.get(self._gs_edit_active_field, "")
                if lb: self._gs_edit_lang_bufs[self._gs_edit_active_field] = lb[:-1]
                self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
            elif ev.key == pygame.K_TAB:
                # Cicla tra i campi lingua
                idx = (self.LANGS.index(self._gs_edit_active_field) + 1) % len(self.LANGS)
                self._gs_edit_active_field = self.LANGS[idx]
                self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
            elif ev.unicode and ev.unicode.isprintable():
                self._gs_edit_lang_bufs[self._gs_edit_active_field] += ev.unicode
                self._gs_edit_buf = self._gs_edit_lang_bufs[self._gs_edit_active_field]
            return

        if not self._gs_new_mode:
            if ev.key == pygame.K_RETURN and self.gs_sel_game is not None:
                self._request_nav(self._gs_open)
            return
        if ev.key == pygame.K_RETURN:
            self._gs_confirm_new()
        elif ev.key == pygame.K_ESCAPE:
            self._gs_new_mode = None
            self._gs_new_buf  = ""
        elif ev.key == pygame.K_BACKSPACE:
            self._gs_new_buf = self._gs_new_buf[:-1]
        elif ev.unicode and ev.unicode.isprintable():
            self._gs_new_buf += ev.unicode

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
            
            # Pulsante COMPILA (solo giochi, i==0)
            if i == 0:
                has_sel_build = self.gs_sel_game is not None
                build_r = pygame.Rect(cx2 + col_w - 62, cy2 + 5, 26, 24)
                build_hov = _in_rect((mx, my_raw), build_r)
                _button(self.screen, build_r, "EXE", build_hov, active=has_sel_build)
                if build_hov: self.active_tooltip = self.lang_manager.get("gs_tip_build", "Compila e pacchettizza il gioco (Crea EXE)")
                
                # Pulsante ELIMINA GIOCO
                del_g_r = pygame.Rect(cx2 + col_w - 122, cy2 + 5, 26, 24)
                del_g_hov = _in_rect((mx, my_raw), del_g_r)
                _button(self.screen, del_g_r, "×", del_g_hov, danger=has_sel_build)
                if del_g_hov: self.active_tooltip = self.lang_manager.get("gs_tip_delete_game", "ELIMINA COMPLETAMENTE il progetto dal disco")

            # Pulsante ✎ di modifica — offset aggiornato per i==0
            has_sel = (i == 0 and self.gs_sel_game is not None) or \
                      (i == 1 and self.gs_sel_level is not None) or \
                      (i == 2 and self.gs_sel_scene is not None)
            edit_off = -92 if i == 0 else -92
            edit_r = pygame.Rect(cx2 + col_w + edit_off, cy2 + 5, 26, 24)
            edit_hov = _in_rect((mx, my_raw), edit_r)
            _button(self.screen, edit_r, "✎", edit_hov, active=has_sel)
            if edit_hov: self.active_tooltip = self.lang_manager.get("gs_tip_edit", "Modifica impostazioni e nomi dell'elemento selezionato")

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
            self._r_gs_column(i, cx2, cy2 + 35, col_w, col_h - 35)

        if self._gs_new_mode:
            self._r_gs_new_dialog(w, h)
        if hasattr(self, '_gs_edit_mode') and self._gs_edit_mode:
            self._r_gs_edit_dialog(w, h)
        if self._gs_del_mode:
            self._r_gs_del_dialog(w, h)

    def _r_gs_column(self, col_idx, cx, cy, cw, ch):
        mx, my_raw = pygame.mouse.get_pos()
        ITEM_H = 34
        
        if col_idx == 0:
            count = len(self.gs_games); sel_idx = self.gs_sel_game; scroll = self.gs_scroll_game
        elif col_idx == 1:
            count = len(self.gs_cur_levels); sel_idx = self.gs_sel_level; scroll = self.gs_scroll_lvl
        else:
            count = len(self.gs_cur_scenes); sel_idx = self.gs_sel_scene; scroll = self.gs_scroll_scn

        vis_count = ch // ITEM_H
        if count > vis_count:
            from editor.ui.draw import _scrollbar
            _scrollbar(self.screen, cx + cw - 6, cy, 4, ch, scroll, count, vis_count)

        self.screen.set_clip(pygame.Rect(cx, cy, cw - 8, ch))
        for i in range(count):
            iy = cy + i * ITEM_H - scroll * ITEM_H
            if iy + ITEM_H < cy or iy > cy + ch: continue
            
            is_sel = (i == sel_idx)
            hov    = _in_rect((mx, my_raw), (cx+5, iy+2, cw-10, ITEM_H-4))
            if is_sel or hov:
                _rect(self.screen, (BTN_AC if is_sel else BTN_HO), (cx+5, iy+2, cw-10, ITEM_H-4), radius=4)
            
            if not hasattr(self, "_gs_labels_cache"): self._gs_refresh_cache()
            try: label = self._gs_labels_cache[col_idx][i]
            except: label = f"item_{i}"
            
            col = TXT_HI if (is_sel or hov) else TXT
            pad_w = 50
            if col_idx == 1: pad_w = 80
            elif col_idx == 2: pad_w = 110
            
            _draw_text(self.screen, label, "sm", col, cx+15, iy+8, cw - pad_w)
            
            if col_idx in (0, 1, 2):
                # Coordinate bottoni (allineati a destra)
                btn_w = 24
                bx_play = cx + cw - 38
                
                if col_idx == 0:
                    # Bottone Play Standalone per Giochi
                    btn_play_hov = _in_rect((mx, my_raw), (bx_play, iy+5, btn_w, 24))
                    _button(self.screen, (bx_play, iy+5, btn_w, 24), "▶", btn_play_hov, font="sm")
                    if btn_play_hov:
                        self.active_tooltip = self.lang_manager.get("btn_play", "GIOCA")
                
                elif col_idx == 1:
                    bx_down = cx + cw - 58
                    bx_up   = cx + cw - 86
                    
                    if i > 0:
                        btn_up_hov = _in_rect((mx, my_raw), (bx_up, iy+5, btn_w, 24))
                        _button(self.screen, (bx_up, iy+5, btn_w, 24), "▲", btn_up_hov, font="sm")
                    
                    if i < count - 1:
                        btn_down_hov = _in_rect((mx, my_raw), (bx_down, iy+5, btn_w, 24))
                        _button(self.screen, (bx_down, iy+5, btn_w, 24), "▼", btn_down_hov, font="sm")
                        
                elif col_idx == 2:
                    bx_open = cx + cw - 30
                    bx_down = cx + cw - 58
                    bx_up   = cx + cw - 86
                    
                    btn_open_hov = _in_rect((mx, my_raw), (bx_open, iy+5, btn_w, 24))
                    _button(self.screen, (bx_open, iy+5, btn_w, 24), "▶", btn_open_hov, font="sm")
                    if btn_open_hov:
                        self.active_tooltip = self.lang_manager.get("gs_btn_open_scene", "APRI SCENA")
                    
                    if i > 0:
                        btn_up_hov = _in_rect((mx, my_raw), (bx_up, iy+5, btn_w, 24))
                        _button(self.screen, (bx_up, iy+5, btn_w, 24), "▲", btn_up_hov, font="sm")
                    
                    if i < count - 1:
                        btn_down_hov = _in_rect((mx, my_raw), (bx_down, iy+5, btn_w, 24))
                        _button(self.screen, (bx_down, iy+5, btn_w, 24), "▼", btn_down_hov, font="sm")

        self.screen.set_clip(None)

    def _r_gs_new_dialog(self, w, h):
        labels = {
            "game": self.lang_manager.get("gs_modal_new_game", "Nuovo gioco"),
            "level": self.lang_manager.get("gs_modal_new_level", "Nuovo livello"),
            "scene": self.lang_manager.get("gs_modal_new_scene", "Nuova scena")
        }
        stitle = labels.get(self._gs_new_mode, "Nuovo")

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))

        dw, dh = 800, 750 if self._gs_new_mode == "game" else (450 if self._gs_new_mode == "scene" else 220)
        dx, dy = (w-dw)//2, (h-dh)//2
        box    = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (40, 42, 54), box, radius=12); _rect(self.screen, ACCENT, box, 2, radius=12)

        _draw_text(self.screen, stitle, "lg", TXT_HI, dx + 30, dy + 20)
        
        # Bottone X di chiusura in alto a destra
        mx2, my2 = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
        x_hov = _in_rect((mx2, my2), xr)
        _button(self.screen, xr, "X", x_hov, danger=True)

        # Punto 1
        _draw_text(self.screen, self.lang_manager.get("gs_label_title", "Punto 1: Titolo / ID"), "sm", TXT_DIM, dx+20, dy+55)
        inp_r = pygame.Rect(dx+20, dy+75, dw-40, 34)
        placeholder = self.lang_manager.get("gs_placeholder_new", "Inserisci ID o nome...")
        _input_box(self.screen, inp_r, self._gs_new_buf, focused=True, hint=placeholder, font="md")

        mx2, my2 = pygame.mouse.get_pos()
        if self._gs_new_mode in ("game", "scene"):
            # IMMAGINE
            iy = dy + 155
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
            vy = dy + 295
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
                my = dy + 435
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

    def _r_gs_edit_dialog(self, w, h):
        labels = {
            "game": self.lang_manager.get("gs_modal_edit_game", "Modifica gioco"),
            "level": self.lang_manager.get("gs_modal_edit_level", "Modifica livello"),
            "scene": self.lang_manager.get("gs_modal_edit_scene", "Modifica scena")
        }
        etitle = labels.get(self._gs_edit_mode, "Modifica")

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180)); self.screen.blit(dim, (0, 0))

        dw = 1000
        dh = 950 if self._gs_edit_mode == "game" else (850 if self._gs_edit_mode == "scene" else 600)
        dx, dy = (w-dw)//2, (h-dh)//2
        box    = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (32, 28, 48), box, radius=12); _rect(self.screen, ACCENT, box, 2, radius=12)

        _draw_text(self.screen, etitle, "lg", TXT_HI, dx + 30, dy + 20)
        
        # Bottone X di chiusura in alto a destra
        mx2, my2 = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 42, dy + 15, 28, 28)
        x_hov = _in_rect((mx2, my2), xr)
        _button(self.screen, xr, "X", x_hov, danger=True)

        # Punto 1: Localizzazione
        _draw_text(self.screen, self.lang_manager.get("gs_label_edit_title_multi", "Punto 1: Traduzioni Nome"), "sm", TXT_DIM, dx+20, dy+52)
        import math
        t = pygame.time.get_ticks() / 1000.0
        
        for i, l in enumerate(self.LANGS):
            fy = dy + 75 + i*32
            is_act = (self._gs_edit_active_field == l)
            lbl_c = ACCENT if is_act else TXT_DIM
            _draw_text(self.screen, l.upper(), "sm", lbl_c, dx+30, fy+6)
            
            f_rect = pygame.Rect(dx+120, fy, dw-140, 28)
            buf = self._gs_edit_lang_bufs.get(l, "")
            placeholder = self.lang_manager.get("gs_placeholder_edit", f"Testo per {l.upper()}...")
            _input_box(self.screen, f_rect, buf, focused=is_act, hint=placeholder, font="md")

        mx2, my2 = pygame.mouse.get_pos()
        if self._gs_edit_mode in ("game", "scene"):
            off_img = 210
            # IMMAGINE
            iy = dy + 75 + off_img
            _draw_text(self.screen, self.lang_manager.get("gs_label_bg_img", "Punto 2: Sfondo Immagine (Opzionale)"), "sm", TXT_DIM, dx+20, iy-25)
            btn_r = pygame.Rect(dx+20, iy, 160, 34); path = getattr(self, '_gs_edit_bg_path', "")
            _button(self.screen, btn_r, self.lang_manager.get("gs_btn_choose_img", "Scegli Immagine..."), _in_rect((mx2, my2), btn_r))
            _rect(self.screen, (15, 12, 25), (dx+190, iy, 450, 34), radius=4)
            _draw_text(self.screen, Path(path).name if path else self.lang_manager.get("gs_no_asset", "Nessuna immagine"), "sm", (TXT_HI if path else TXT_DIM), dx+200, iy+8, 430)
            
            prev_r = pygame.Rect(dx+680, iy-20, 280, 157)
            _rect(self.screen, (10, 12, 20), prev_r, radius=8); _rect(self.screen, BORDER, prev_r, 1, radius=8)
            surf = getattr(self, "_gs_edit_bg_preview_surf", None)
            if surf: 
                # Scaliamo l'anteprima per riempire il nuovo box più grande
                scaled = pygame.transform.smoothscale(surf, (280, 157))
                self.screen.blit(scaled, prev_r.topleft)
            else: _draw_text(self.screen, self.lang_manager.get("gs_txt_no_preview", "[ NESSUNA ANTEPRIMA ]"), "sm", (60, 65, 90), prev_r.x + 80, prev_r.y + 65)

            # VIDEO
            off_vid = 380
            vy = dy + 75 + off_vid
            _draw_text(self.screen, self.lang_manager.get("gs_label_bg_vid", "Punto 3: Sfondo Video (Alternativo)"), "sm", TXT_DIM, dx+20, vy-25)
            btn_v_r = pygame.Rect(dx+20, vy, 160, 34)
            vpath = getattr(self, '_gs_edit_vid_path', "")
            _button(self.screen, btn_v_r, self.lang_manager.get("gs_btn_choose_vid", "Scegli Video..."), _in_rect((mx2, my2), btn_v_r))
            _rect(self.screen, (15, 12, 25), (dx+190, vy, 450, 34), radius=4)
            _draw_text(self.screen, Path(vpath).name if vpath else self.lang_manager.get("gs_no_asset_v", "Nessun video"), "sm", (OK_C if vpath else TXT_DIM), dx+200, vy+8, 430)

            # Preview Video (Edit)
            vprev_r = pygame.Rect(dx+680, vy-20, 280, 157)
            _rect(self.screen, (10, 12, 20), vprev_r, radius=8); _rect(self.screen, BORDER, vprev_r, 1, radius=8)
            vsurf = getattr(self, "_gs_edit_vid_preview_surf", None)
            if vsurf: 
                scaled_v = pygame.transform.smoothscale(vsurf, (280, 157))
                self.screen.blit(scaled_v, vprev_r.topleft)
            else: 
                _draw_text(self.screen, self.lang_manager.get("gs_txt_no_preview", "[ NESSUNA ANTEPRIMA ]"), "sm", (60, 65, 90), vprev_r.x + 80, vprev_r.y + 65)

            if vpath:
                cp = vprev_r.center
                p_hov = _in_rect((mx2, my2), vprev_r)
                pygame.draw.circle(self.screen, (50, 60, 100, 220) if p_hov else (25, 30, 55, 180), cp, 40)
                _draw_shape_icon(self.screen, (cp[0]-20, cp[1]-20, 40, 40), "play", TXT_HI if p_hov else TXT_DIM)

            if self._gs_edit_mode == "game":
                # MUSICA
                my = dy + 650
                _draw_text(self.screen, self.lang_manager.get("gs_label_music_menu", "Punto 4: Playlist Musicale Menu"), "sm", TXT_DIM, dx+20, my-25)
                mu_list = getattr(self, "_gs_edit_music_paths", [])
                btn_m_r = pygame.Rect(dx+20, my, dw-100, 34)
                cl_btn_r = pygame.Rect(dx+dw-70, my, 50, 34)
                label_m = f"{len(mu_list)} " + self.lang_manager.get("gs_tracks_manage", "brani - Gestisci Playlist...")
                _button(self.screen, btn_m_r, label_m, _in_rect((mx2, my2), btn_m_r))
                _button(self.screen, cl_btn_r, "X", _in_rect((mx2, my2), cl_btn_r), danger=len(mu_list)>0)
                
                # Lista
                list_r = pygame.Rect(dx+20, my+45, dw-40, 150)
                _rect(self.screen, (20, 22, 32), list_r, radius=8)
                
                mu_slice = mu_list[self.gs_edit_mu_scroll : self.gs_edit_mu_scroll + 8]
                for i, p in enumerate(mu_slice):
                    idx = self.gs_edit_mu_scroll + i
                    txt = f"{idx+1}. {Path(p).name}"
                    _draw_text(self.screen, txt, "sm", TXT, list_r.x+10, list_r.y+10+i*18)
                    xr = pygame.Rect(list_r.x + list_r.w - 32, list_r.y + 10 + i*18, 18, 18)
                    x_hov = _in_rect((mx2, my2), xr)
                    _rect(self.screen, (180, 50, 50) if x_hov else (60, 60, 75), xr, radius=4)
                    # Utilizziamo il simbolo di moltiplicazione che è più bilanciato della 'x' minuscola
                    tw_x, th_x = _text_wh("×", "xs")
                    _draw_shape_icon(self.screen, xr.inflate(-4,-4), "x", (255, 255, 255))
                
                # Scrollbar discreta se necessario
                if len(mu_list) > 8:
                    _scrollbar(self.screen, list_r.x + list_r.w - 6, list_r.y + 5, 4, list_r.h - 10, self.gs_edit_mu_scroll, len(mu_list), 8)

        btn_y = dy + dh - 60
        ok_r  = pygame.Rect(dx+20, btn_y, 210, 34)
        esc_r = pygame.Rect(dx+dw-230, btn_y, 210, 34)
        _button(self.screen, ok_r, self.lang_manager.get("gs_btn_save", "SALVA MODIFICHE"), _in_rect((mx2, my2), ok_r), active=True)

        if self._gs_edit_mode == "game":
            del_r = pygame.Rect(dx + 250, btn_y, 210, 34)
            stage = getattr(self, "_gs_edit_del_stage", 0)
            del_label = self.lang_manager.get(f"gs_btn_edit_del_{stage}", "ELIMINA PROGETTO")
            _button(self.screen, del_r, del_label, _in_rect((mx2, my2), del_r), danger=True)
        
        cancel_label = self.lang_manager.get("gs_btn_cancel", "ANNULLA")
        _button(self.screen, esc_r, cancel_label, _in_rect((mx2, my2), esc_r))
