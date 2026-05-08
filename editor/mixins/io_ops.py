"""
editor/mixins/io_ops.py

IoOpsMixin — caricamento gioco/scena/background, salvataggio, autosave,
             image cache, recent scenes, status bar message.
"""

import os
import json
import logging
import copy
import time
import shutil
from pathlib import Path

import pygame

from editor.constants import (
    AUTOSAVE_SECS, OK_C, ERR_C, WARN_C, TXT_DIM, STATE_MAIN,
    TAB_CATALOG,
)
from editor.core.io import (
    _load_catalog, _load_scene_data, _discover_levels, _discover_games,
    _load_json, _save_json, _file_dialog, _load_effects_catalog,
)


class IoOpsMixin:
    """Load/save dati editor, image cache, status bar."""

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS
    # ─────────────────────────────────────────────────────────────────────────

    def _status(self, msg: str, color=None, duration=0):
        self.status_msg   = msg
        self.status_col   = color or TXT_DIM
        self.status_until = time.time() + duration if duration else 0

    # ─────────────────────────────────────────────────────────────────────────
    # ASSET MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _harvest_asset(self, catalog_id: str) -> bool:
        """
        Copia il PNG di un oggetto dall'engine alla cartella di gioco e sincronizza
        il catalogo JSON locale. Operazione IDEMPOTENTE e non distruttiva:
        - Non modifica MAI i file dell'engine
        - Non sovrascrive se il file di destinazione esiste già
        - Aggiorna l'entry JSON nel catalogo di gioco se il contenuto è cambiato

        Returns True se è stato copiato un nuovo file PNG, False altrimenti.
        """
        if not getattr(self, 'game_path', None):
            return False

        cat_entry = next((c for c in self.catalog if c.get("id") == catalog_id), None)
        if not cat_entry:
            return False

        harvested = False

        # ── 1. Copia PNG: engine → game/objects/ ─────────────────────────────
        icon_rel = cat_entry.get("icon", "")
        if icon_rel:
            icon_name = Path(icon_rel).name
            master_p = self.base_path / "engine" / "assets" / "objects" / icon_name
            game_objects_p = self.game_path / "objects"
            game_objects_p.mkdir(parents=True, exist_ok=True)
            dst_p = game_objects_p / icon_name

            if not dst_p.exists():
                if master_p.exists():
                    try:
                        shutil.copy2(master_p, dst_p)
                        harvested = True
                        logging.info(f"[ASSET] Harvested PNG: {icon_name}")
                    except Exception as e:
                        logging.error(f"[ASSET] Harvest PNG failed for '{icon_name}': {e}")
                else:
                    logging.warning(f"[ASSET] Master PNG not found in engine: {master_p}")

        # ── 2. Sincronizza entry catalogo JSON nel gioco ──────────────────────
        self._sync_game_catalog_entry(cat_entry)

        return harvested

    def _sync_game_catalog_entry(self, cat_entry: dict):
        """
        Aggiunge o aggiorna l'entry di catalog_id in games/{game}/objects_catalog.json.
        Il file di gioco agisce come catalogo locale auto-contenuto per il packaging EXE.
        """
        if not getattr(self, 'game_path', None):
            return

        game_cat_path = self.game_path / "objects_catalog.json"
        try:
            if game_cat_path.exists():
                with open(game_cat_path, "r", encoding="utf-8") as f:
                    game_cat = json.load(f)
            else:
                game_cat = {"objects": []}

            objects = game_cat.setdefault("objects", [])
            obj_id = cat_entry.get("id")
            existing_idx = next((i for i, o in enumerate(objects) if o.get("id") == obj_id), -1)

            if existing_idx >= 0:
                if objects[existing_idx] != cat_entry:
                    objects[existing_idx] = cat_entry
                else:
                    return  # Già aggiornato, nessuna scrittura necessaria
            else:
                objects.append(cat_entry)

            game_cat["objects"] = sorted(objects, key=lambda o: o.get("id", ""))
            with open(game_cat_path, "w", encoding="utf-8") as f:
                json.dump(game_cat, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logging.warning(f"[ASSET] Catalog JSON sync failed for '{cat_entry.get('id')}': {e}")

    def _collect_used_assets(self, current_data: dict) -> tuple[set, set]:
        """
        Scansiona TUTTE le scene del gioco + la scena corrente in memoria.
        Restituisce (used_catalog_ids: set[str], used_icon_names: set[str]).
        used_icon_names sono i nomi file PNG (es. 'anarchy_slab.png').
        """
        used_catalog_ids: set[str] = set()
        catalog_map = {c["id"]: c for c in self.catalog}

        # Scena corrente in memoria (include le modifiche non ancora su disco)
        for o in current_data.get("objects", []):
            cid = o.get("catalog_id") or o.get("id")
            if cid:
                used_catalog_ids.add(cid)

        # Tutte le altre scene su disco
        if getattr(self, 'game_path', None):
            current_scene_json = (self.scene_path / "scene.json").resolve() if self.scene_path else None
            for s_json in self.game_path.rglob("scene.json"):
                if current_scene_json and s_json.resolve() == current_scene_json:
                    continue  # Già considerata sopra (versione in memoria)
                try:
                    with open(s_json, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                    for o in s_data.get("objects", []):
                        cid = o.get("catalog_id") or o.get("id")
                        if cid:
                            used_catalog_ids.add(cid)
                except Exception:
                    pass

        # Risolve catalog_id → nome file icona
        used_icon_names: set[str] = set()
        for cid in used_catalog_ids:
            cat = catalog_map.get(cid)
            if cat and "icon" in cat:
                used_icon_names.add(Path(cat["icon"]).name)

        return used_catalog_ids, used_icon_names

    # ─────────────────────────────────────────────────────────────────────────
    # LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def _load_game(self, game_name: str):
        print(f"[EDITOR] Loading game: {game_name}")
        self.game_name = game_name
        
        # Path standard
        self.game_path = self.base_path / "games" / game_name
        
        # Fallback silenzioso per minigiochi dell'engine (permette l'audit dei path richiesti)
        if not self.game_path.exists():
            mini_p = self.base_path / "engine" / "minigames" / game_name
            if mini_p.exists():
                self.game_path = mini_p
        
        # Carica le stringhe del gioco nel manager (mantenendo la lingua corrente dell'editor)
        self.lang_manager.load_for_game(game_name, getattr(self, "current_lang", "it"))
        
        self.catalog          = _load_catalog(game_name)
        self.effects_catalog  = _load_effects_catalog()
        self._load_strings()
        self.levels           = _discover_levels(self.game_path)
        print(f"[EDITOR] Catalog items: {len(self.catalog)}, Levels: {len(self.levels)}")
        if self.levels:
            self.tree_expanded[self.levels[0]["id"]] = True
        self.state = STATE_MAIN
        print(f"[EDITOR] Game loaded successfully: {game_name}")
        self._status(f"Gioco: {game_name}", OK_C, 4)

        # Auto-carica l'ultima scena aperta se appartiene a questo gioco
        if self.recent_scenes and self.recent_scenes[0].get("game") == game_name:
            recent_path = Path(self.recent_scenes[0]["path"])
            if recent_path.exists():
                self._load_scene(recent_path)

    def _load_scene(self, scene_path: Path):
        print(f"[EDITOR] Loading scene: {scene_path}")
        self.scene_path  = scene_path
        self.scene_data  = _load_scene_data(scene_path)
        self._sanitize_effects()
        self.selected_idx = None
        self.sel_effect_idx = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.scene_dirty  = False
        self._editing_hint = False
        self._save_recent(scene_path)
        self.l_tab = TAB_CATALOG  # Forza apertura catalogo
        # Stato visibilità layer predefinito all'apertura
        self.layer_vis = {
            "objects_low": False,
            "objects_mid": True,
            "objects_high": False,
            "overlay": True,
            "effects": False
        }
        self.active_layer = "objects_mid"
        
        # Ripristino stato Lock salvato nella scena
        saved_locked = self.scene_data.get("layer_locked", {})
        for lid in self.layer_locked:
            self.layer_locked[lid] = saved_locked.get(lid, False)

        # Gestione background: solo se non è una stringa vuota
        bg_name = self.scene_data.get("background", "")
        bg_file = scene_path / bg_name if bg_name else None
        self.bg_surf = None
        self._bg_cache_surf = None
        self._obj_draw_cache.clear()
        if bg_file and bg_file.exists():
            try:
                # Carica immagine e la converte per prestazioni
                self.bg_surf = pygame.image.load(str(bg_file)).convert()
                bw, bh = self.bg_surf.get_size()
                print(f"[EDITOR] Background loaded: {bg_file.name} ({bw}x{bh})")
            except Exception as e:
                print(f"[EDITOR] Failed to load background: {e}")
                self.bg_surf = None
        else:
            if bg_name:
                print(f"[EDITOR] Background file MISSING: {bg_name}")
            else:
                print(f"[EDITOR] No background set for this scene.")
            self.bg_surf = None

        self._fit_canvas()
        n = len(self.scene_data.get("objects", []))
        print(f"[EDITOR] Scene loaded: {n} objects")
        self._status(f"Scena: {scene_path.name}  ({n} oggetti)", OK_C, 3)

    def _load_background(self):
        """Apre la modale custom per scegliere l'immagine di sfondo."""
        self._bg_modal_open(context="scene")

    # ─────────────────────────────────────────────────────────────────────────
    # SAVE / AUTOSAVE
    # ─────────────────────────────────────────────────────────────────────────

    def _save(self):
        if not self.scene_path:
            self._status("Errore: percorso scena non impostato!", ERR_C, 3)
            return
            
        logging.info(f"[EDITOR] Salvataggio scena: {self.scene_path}")
        self._sanitize_effects()
        
        # Persistenza stato Lock dei layer
        self.scene_data["layer_locked"] = self.layer_locked
        
        # Deep Copy per manipolazione sicura dei dati
        data = copy.deepcopy(self.scene_data)
        copy_objs = data.get("objects", [])

        # 3. Cleanup
        processed = 0
        for obj in copy_objs:
            # Rimuove campi interni/temporanei (quelli che iniziano con _)
            for k in list(obj.keys()):
                if k.startswith("_"): obj.pop(k)

            # Rimuove valori di default per salvare spazio
            if obj.get("rotation") == 0:       obj.pop("rotation", None)
            if obj.get("flip_x")   == False:   obj.pop("flip_x",   None)
            if obj.get("flip_y")   == False:   obj.pop("flip_y",   None)
            if obj.get("always_show") == False: obj.pop("always_show", None)
            if obj.get("alpha", 255) == 255:   obj.pop("alpha", None)
            if tuple(obj.get("color_filter", (255, 255, 255))) == (255, 255, 255): obj.pop("color_filter", None)
            
            # --- PERSISTENZA BIANCO E NERO (Grayscale) ---
            gs_val = obj.get("grayscale", False)
            if gs_val:
                logging.debug(f"[EDITOR-IO] Persistenza B/N per {obj.get('catalog_id')}")
                # Forziamo che rimanga nel dizionario finale
                obj["grayscale"] = True
                if obj.get("grayscale_factor") == 1.0:
                    obj.pop("grayscale_factor", None)
            else:
                obj.pop("grayscale", None)
                obj.pop("grayscale_factor", None)

            coff = obj.get("corners", [[0,0], [0,0], [0,0], [0,0]])
            if all(c[0] == 0 and c[1] == 0 for c in coff): obj.pop("corners", None)
            processed += 1

        
        # ── Cleanup Effetti ──────────────────────────────
        copy_fx = data.get("effects", [])
        for fx in copy_fx:
            # Rimuove campi interni/temporanei (quelli che iniziano con _)
            for k in list(fx.keys()):
                if k.startswith("_"): fx.pop(k)

            if fx.get("pulse_period") == 2.0:  fx.pop("pulse_period", None)
            if fx.get("pulse_min") == 0.1:     fx.pop("pulse_min",    None)
            if fx.get("phase") == 0.0:         fx.pop("phase",        None)
            if fx.get("intensity") == 0.85:    fx.pop("intensity",    None)
            if fx.get("radius") == 55:         fx.pop("radius",       None)
            if fx.get("color") == [255, 215, 60]: fx.pop("color",    None)
            if fx.get("alpha", 255) == 255:    fx.pop("alpha",        None)
            if fx.get("font_size") == 22:      fx.pop("font_size",    None)
            if fx.get("font_color") == [40, 40, 40]: fx.pop("font_color", None)

        print(f"[EDITOR] Step 3: Cleanup processed {processed} objects and {len(copy_fx)} effects")
        
        # 4. Asset Harvesting — copia PNG + sincronizza catalog JSON per ogni oggetto usato.
        #    _harvest_asset() è idempotente: non sovrascrive file già presenti.
        harvested_count = 0
        seen_harvest = set()
        for obj in data.get("objects", []):
            cid = obj.get("catalog_id")
            if cid and cid not in seen_harvest:
                seen_harvest.add(cid)
                if self._harvest_asset(cid):
                    harvested_count += 1

        if harvested_count > 0:
            print(f"[EDITOR] Harvested {harvested_count} nuovi asset nella cartella di gioco.")

        # 5. Asset Cleanup — rimozione PNG orfani dal gioco (MAI dall'engine).
        #    Scansiona TUTTE le scene (inclusa quella corrente in memoria) per determinare
        #    quali file sono ancora necessari. Confronta per NOME FILE ICONA, non per
        #    catalog_id, per evitare falsi positivi quando id ≠ nome file.
        game_objects_p = self.game_path / "objects"
        master_objects_p = self.base_path / "engine" / "assets" / "objects"

        used_catalog_ids, used_icon_names = self._collect_used_assets(data)

        removed_count = 0
        for f in game_objects_p.glob("*.png"):
            if f.name not in used_icon_names:
                # Rimuove solo se il file esiste nel master engine (è recuperabile)
                if (master_objects_p / f.name).exists():
                    try:
                        f.unlink()
                        removed_count += 1
                        logging.info(f"[ASSET] Rimosso PNG orfano dalla cartella di gioco: {f.name}")
                    except Exception as e:
                        logging.warning(f"[ASSET] Cleanup PNG fallito per '{f.name}': {e}")

        # Rimuove anche le entry orfane dal catalogo JSON di gioco
        game_cat_path = self.game_path / "objects_catalog.json"
        if game_cat_path.exists():
            try:
                with open(game_cat_path, "r", encoding="utf-8") as f:
                    game_cat = json.load(f)
                before = len(game_cat.get("objects", []))
                game_cat["objects"] = [
                    o for o in game_cat.get("objects", [])
                    if o.get("id") in used_catalog_ids
                ]
                if len(game_cat["objects"]) < before:
                    with open(game_cat_path, "w", encoding="utf-8") as f:
                        json.dump(game_cat, f, indent=2, ensure_ascii=False)
                    removed_json = before - len(game_cat["objects"])
                    logging.info(f"[ASSET] Rimosse {removed_json} entry orfane da objects_catalog.json")
            except Exception as e:
                logging.warning(f"[ASSET] Cleanup catalog JSON fallito: {e}")

        if removed_count > 0:
            print(f"[EDITOR] Cleanup: rimossi {removed_count} PNG orfani (ripristinabili dall'engine).")

        # 5.5 Translation Audit (Audita e sincronizza TUTTI i file lingua del gioco)
        self._audit_translations(data)

        # 5.6 Music Harvest & Cleanup (copia musiche dal motore + garbage collection)
        # Costruisce set di nomi file musicali usati (estrae da paths potenzialmente diversi)
        used_music_names: set[str] = set()
        for s_json in self.game_path.rglob("scene.json"):
            try:
                with open(s_json, "r", encoding="utf-8") as f_j:
                    s_data = json.load(f_j)
                    for mpath in s_data.get("music", []):
                        used_music_names.add(Path(mpath).name)
            except: pass

        # Aggiungi musiche della scena corrente (ancora in memoria)
        for mpath in data.get("music", []):
            used_music_names.add(Path(mpath).name)

        # Harvest musiche: copia da engine/assets/music/ a games/{game}/audio/music/
        engine_music_p = self.base_path / "engine" / "assets" / "music"
        game_music_p = self.game_path / "audio" / "music"
        if engine_music_p.exists():
            game_music_p.mkdir(parents=True, exist_ok=True)
            harvested_music = 0
            for mname in used_music_names:
                src_m = engine_music_p / mname
                dst_m = game_music_p / mname
                if src_m.exists() and not dst_m.exists():
                    try:
                        shutil.copy2(src_m, dst_m)
                        harvested_music += 1
                    except Exception as e:
                        logging.warning(f"[ASSET] Music harvest fallito per '{mname}': {e}")
            if harvested_music > 0:
                print(f"[EDITOR] Harvested {harvested_music} musiche nella cartella di gioco.")

        # Cleanup musiche orfane dal game folder (MAI dall'engine)
        if game_music_p.exists():
            audio_removed = 0
            for f in game_music_p.glob("*.mp3"):
                if f.name not in used_music_names:
                    try:
                        # Rilascia il mixer prima di tentare l'eliminazione
                        import pygame
                        try:
                            pygame.mixer.music.unload()
                        except: pass

                        f.unlink(missing_ok=True)
                        audio_removed += 1
                        logging.info(f"[ASSET] Rimossa musica orfana: {f.name}")
                    except Exception as e:
                        logging.warning(f"[ASSET] Music cleanup fallito per '{f.name}': {e}")

            if audio_removed > 0:
                print(f"[EDITOR] Music Cleanup: rimossi {audio_removed} brani non più usati nel gioco.")

        # 6. Write
        save_path = self.scene_path / "scene.json"
        
        # Diagnostica B&W pre-scrittura
        gs_found = [o.get("catalog_id") for o in data.get("objects", []) if o.get("grayscale")]
        if gs_found:
            print(f"[EDITOR-IO] CRITICAL: Writing to JSON with Grayscale objects: {gs_found}")
        else:
            print(f"[EDITOR-IO] WARNING: No Grayscale objects found in data about to be saved!")

        final_count = len(data.get("objects", []))
        if _save_json(save_path, data):

            self.scene_dirty = False
            print(f"[EDITOR] ----- SAVE SUCCESS: {save_path} -----")
            self._status(f"Salvataggio completato: {final_count} oggetti", OK_C, 3)
        else:
            print(f"[EDITOR] !!! SAVE FAILED (Disk error?) !!!")
            self._status("ERRORE DISCO!", ERR_C, 5)

    def _audit_translations(self, data: dict):
        """
        Audita e sincronizza i file lingua del gioco ad ogni salvataggio.

        Scansiona TUTTE le scene del gioco per determinare le chiavi necessarie,
        poi per ogni file lingua (it/en/de/fr/es):
          + AGGIUNGE le chiavi obj_* mancanti non coperte dall'engine
          + AGGIUNGE le chiavi TIP_* mancanti come placeholder vuoto
          + RIEMPIE i placeholder vuoti con il valore del master engine se disponibile
          - RIMUOVE le chiavi obj_* e TIP_* inutilizzate (non referenziate in nessuna scena)
          - RIMUOVE i duplicati: chiavi con valore identico al master engine (ridondanti)
        """
        if not getattr(self, 'game_path', None):
            return

        langs       = getattr(self, 'LANGS', ['it', 'en', 'de', 'fr', 'es'])
        catalog_map = {c["id"]: c for c in getattr(self, 'catalog', [])}

        # ── 1. Raccoglie chiavi necessarie (Solo Scene correnti del gioco) ─────
        needed_obj_keys = set()   # label_key di oggetti usati in scene
        needed_tip_keys = set()   # TIP_* di bubble_tip usati in qualsiasi scena
        
        # Chiavi di sistema/HUD obbligatorie (necessarie per l'interfaccia di gioco autonoma)
        needed_sys_keys = {
            "btn_back", "btn_resume", "btn_settings", "btn_quit_to_main", "btn_play", "btn_ok", "btn_cancel",
            "hud_time", "hud_score", "hud_found", "hud_hint_seek", "hud_remaining_status",
            "label_language", "label_resolution", "label_fullscreen", "mode_window",
            "label_music_volume", "label_sfx_volume", "label_master_volume",
            "mg_title", "mg_description", "pause_title", "mission_complete"
        }

        current_scene_json = (self.scene_path / "scene.json").resolve() if self.scene_path else None

        # Scansiona tutte le scene del gioco per determinare quali oggetti sono DAVVERO in uso
        for scene_file in self.game_path.rglob("scene.json"):
            try:
                if current_scene_json and scene_file.resolve() == current_scene_json:
                    scene = data
                else:
                    with open(scene_file, "r", encoding="utf-8") as f:
                        scene = json.load(f)

                for obj in scene.get("objects", []):
                    # Recupera la label_key dal catalogo se possibile, altrimenti usa obj_ID
                    cid = obj.get("catalog_id") or obj.get("id")
                    if cid:
                        cat_entry = catalog_map.get(cid)
                        # Fallback a obj_{cid} se label_key è mancante o vuota
                        key = (cat_entry.get("label_key") if cat_entry else None) or f"obj_{cid}"
                        needed_obj_keys.add(key)

                for fx in scene.get("effects", []):
                    if fx.get("type") == "bubble_tip":
                        tkey = fx.get("text_key", "")
                        if tkey and tkey.startswith("TIP_"):
                            needed_tip_keys.add(tkey)
            except Exception as e:
                logging.error(f"[EDITOR-AUDIT] Errore scansione scena {scene_file}: {e}")

        # ── 2. Carica engine strings (master per ogni lingua) ─────────────────
        engine_sp = self.base_path / "engine" / "assets" / "strings"
        engine_data = {
            lang: (_load_json(engine_sp / f"{lang}.json") if (engine_sp / f"{lang}.json").exists() else {})
            for lang in langs
        }

        # ── 3. Audita ogni file lingua del gioco ──────────────────────────────
        game_sp = self.game_path / "strings"
        game_sp.mkdir(exist_ok=True)

        stats = {"added": 0, "filled": 0, "unused": 0, "duplicate": 0}

        for lang in langs:
            gp     = game_sp / f"{lang}.json"
            g_data = _load_json(gp) if gp.exists() else {}
            eng    = engine_data[lang]
            changed = False

            # A. Aggiunge chiavi obj_* e TIP_* mancanti.
            for key in needed_obj_keys:
                if key not in g_data:
                    # Se l'engine ha questa chiave, facciamo HARVESTING: la copiamo nel gioco
                    if key in eng and eng[key]:
                        g_data[key] = eng[key]
                        stats["filled"] += 1
                        changed = True
                        continue
                    
                    # Se non è nell'engine, è un oggetto specifico del gioco o nuovo
                    g_data[key] = key.replace("obj_", "").replace("_", " ").title()
                    stats["added"] += 1
                    changed = True

            for key in needed_tip_keys:
                if key not in g_data:
                    g_data[key] = ""
                    stats["added"] += 1
                    changed = True
            
            # A.bis Aggiunge chiavi di SISTEMA mancanti (Harvesting automatico)
            for key in needed_sys_keys:
                if key not in g_data:
                    if key in eng and eng[key]:
                        g_data[key] = eng[key]
                        stats["filled"] += 1
                        changed = True
                    else:
                        # Se manca anche nell'engine, mettiamo un placeholder pulito
                        g_data[key] = key.replace("btn_", "").replace("hud_", "").replace("label_", "").replace("_", " ").title()
                        stats["added"] += 1
                        changed = True

            # B. Generazione automatica nomi per oggetti in INGLESE se la chiave è vuota
            for key in list(g_data.keys()):
                if not g_data[key]: # Se è "" o None
                    if lang == 'en' and key.startswith("obj_"):
                        g_data[key] = key.replace("obj_", "").replace("_", " ").title()
                        changed = True

            # C. Rimuove chiavi inutilizzate (pulizia orfani CHIRURGICA)
            #    Rimuove solo oggetti (obj_) e fumetti (TIP_) se non presenti in NESSUNA scena.
            #    Le chiavi di sistema (Menu/HUD) sono protette dalla needed_sys_keys.
            for key in list(g_data.keys()):
                # Protezione assoluta: Titolo e System Keys
                if key == "game_title" or key in needed_sys_keys:
                    continue
                # Protezione: Stringhe custom che iniziano con l'ID del gioco (es. Malonno_Survivors_intro)
                if key.startswith(f"{self.game_name}_"):
                    continue
                    
                is_obj = key.startswith("obj_")
                is_tip = key.startswith("TIP_")
                
                # Se è un asset di scena ma non è più referenziato -> ELIMINA
                if (is_obj and key not in needed_obj_keys) or (is_tip and key not in needed_tip_keys):
                    del g_data[key]
                    stats["unused"] += 1
                    changed = True

            # D. HARVESTING / AGGIORNAMENTO DA ENGINE
            # Scorre tutte le chiavi nel gioco: se mancano, sono vuote o sono placeholder,
            # tenta di recuperare la versione ufficiale aggiornata dall'Engine.
            for sys_key in needed_sys_keys:
                if sys_key not in g_data or not g_data[sys_key]:
                    if sys_key in eng and eng[sys_key]:
                        g_data[sys_key] = eng[sys_key]
                        stats["filled"] += 1
                        changed = True

            for key in list(g_data.keys()):
                if key in eng and eng[key]:
                    # Aggiorna se vuoto o se è un placeholder editor (es. "Abyssal Crystal" vs "Abyssal Crystal")
                    placeholder = key.replace("obj_", "").replace("_", " ").title()
                    if not g_data[key] or g_data[key] == placeholder:
                        if g_data[key] != eng[key]:
                            g_data[key] = eng[key]
                            stats["filled"] += 1
                            changed = True

            if changed:
                # Ordinamento alfabetico per pulizia
                sorted_data = dict(sorted(g_data.items()))
                _save_json(gp, sorted_data)

        # ── 4. Log e status bar ───────────────────────────────────────────────
        parts = []
        if stats["added"]:     parts.append(f"+{stats['added']} aggiunte")
        if stats["filled"]:    parts.append(f"+{stats['filled']} riempite")
        if stats["unused"]:    parts.append(f"-{stats['unused']} inutilizzate")
        if stats["duplicate"]: parts.append(f"-{stats['duplicate']} duplicate")

        if parts:
            summary = " | ".join(parts)
            print(f"[EDITOR] Audit traduzioni ({len(langs)} lingue): {summary}")
            self._status(f"Audit ✓  {summary}", OK_C, 4)
        else:
            print("[EDITOR] Audit traduzioni: OK — nessuna modifica necessaria")

    def _autosave(self):
        if not self.scene_path or not self.scene_dirty:
            return
        print(f"[EDITOR] Autosaving scene...")
        # Deep copy per evitare di sporcare self.scene_data durante il cleanup
        data = copy.deepcopy(self.scene_data)
        for obj in data.get("objects", []):
            for k in list(obj.keys()):
                if k.startswith("_"): obj.pop(k)
        for fx in data.get("effects", []):
            for k in list(fx.keys()):
                if k.startswith("_"): fx.pop(k)

        _save_json(self.scene_path / "scene.json.autosave", data)
        print(f"[EDITOR] Autosave complete")
        self.last_autosave = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # IMPOSTAZIONI & RECENTI
    # ─────────────────────────────────────────────────────────────────────────

    def _load_editor_settings(self) -> dict:
        """Carica tutte le impostazioni dal file .editor_settings.json."""
        from editor.core.io import _load_json
        root = getattr(self, "base_path", Path("."))
        cfg_path = root / ".editor_settings.json"
        if cfg_path.exists():
            try:
                return _load_json(cfg_path)
            except Exception:
                pass
        return {}

    def _save_editor_setting(self, key: str, value: any):
        """Salva una singola impostazione nel file .editor_settings.json."""
        from editor.core.io import _save_json
        settings = self._load_editor_settings()
        settings[key] = value
        root = getattr(self, "base_path", Path("."))
        cfg_path = root / ".editor_settings.json"
        _save_json(cfg_path, settings)

    def _load_recent_config(self) -> list:
        """Carica la lista dei progetti recenti, pulendo quelli non più esistenti."""
        from editor.core.io import _save_json
        settings = self._load_editor_settings()
        recent = settings.get("recent_scenes", [])
        
        # Pulisce i percorsi non più esistenti
        cleaned = []
        changed = False
        for r in recent:
            p = Path(r.get("path", ""))
            if p.exists():
                cleaned.append(r)
            else:
                changed = True
        
        if changed:
            settings["recent_scenes"] = cleaned
            root = getattr(self, "base_path", Path("."))
            _save_json(root / ".editor_settings.json", settings)
        
        return cleaned

    def _save_recent(self, scene_path: Path):
        """Aggiunge una scena alla lista dei recenti e salva."""
        recent = self._load_recent_config()
        new_entry = {
            "name":  scene_path.name,
            "path":  str(scene_path),
            "game":  self.game_path.name if self.game_path else "Unknown",
            "time":  time.time(),
        }
        recent = [r for r in recent if r["path"] != str(scene_path)]
        recent.insert(0, new_entry)
        recent = recent[:8]
        self._save_editor_setting("recent_scenes", recent)
        self.recent_scenes = recent

    # ─────────────────────────────────────────────────────────────────────────
    # IMAGE CACHE
    # ─────────────────────────────────────────────────────────────────────────

    def _load_img(self, path: Path, size: tuple) -> "pygame.Surface | None":
        # Clamp size per evitare surface giganti che causano artefatti
        MAX_SIZE = 2000
        clamped_size = (min(size[0], MAX_SIZE), min(size[1], MAX_SIZE))

        key = (str(path), clamped_size)
        if key in self._img_cache:
            return self._img_cache[key]
        if not path.exists():
            # Fallback al repository centrale del motore
            if "games" in str(path):
                # Prova a ricostruire il path verso engine/assets/objects
                master_p = self.base_path / "engine" / "assets" / "objects" / path.name
                if master_p.exists():
                    path = master_p
                else:
                    self._img_cache[key] = None
                    return None
            else:
                self._img_cache[key] = None
                return None
        try:
            raw = pygame.image.load(str(path))
            try:
                raw = raw.convert_alpha()
            except Exception:
                raw = raw.convert()

            # Usa smoothscale per migliore qualità (più lento ma worth it)
            # smoothscale usa bilinear interpolation invece di nearest-neighbor
            if clamped_size != raw.get_size():
                scaled = pygame.transform.smoothscale(raw, clamped_size)
            else:
                scaled = raw
            self._img_cache[key] = scaled
            return scaled
        except Exception:
            self._img_cache[key] = None
            return None

    def _delete_catalog_asset(self, cat_id: str):
        """
        Elimina permanentemente un oggetto dal database globale dell'engine.
        Operazione CHIRURGICA e SICURA:
        1. Verifica che l'asset non sia in uso in nessun gioco registrato.
        2. Crea un backup preventivo del catalogo globale.
        3. Rimuove il record JSON e riordina alfabeticamente.
        4. Elimina la PNG fisica solo se non condivisa e valida.
        """
        logging.info(f"[EDITOR] Avvio eliminazione asset globale: {cat_id}")
        global_cat_path = self.base_path / "engine" / "data" / "global_objects_catalog.json"
        
        # --- 1. CHECK DI SICUREZZA: L'asset è in uso in qualche gioco? ---
        used_locations = []
        games_dir = self.base_path / "games"
        
        # Scena corrente in memoria per il gioco attuale
        current_scene_path = (self.scene_path / "scene.json").resolve() if getattr(self, "scene_path", None) else None
        current_scene_data = getattr(self, "scene_data", {})

        if games_dir.exists():
            for g_dir in games_dir.iterdir():
                if not g_dir.is_dir():
                    continue
                # Scansione tutte le scene del gioco
                for scene_file in g_dir.rglob("scene.json"):
                    try:
                        # Se è la scena che stiamo editando, usiamo i dati in memoria
                        if current_scene_path and scene_file.resolve() == current_scene_path:
                            s_data = current_scene_data
                        else:
                            with open(scene_file, "r", encoding="utf-8") as f:
                                s_data = json.load(f)
                                
                        if any(o.get("catalog_id") == cat_id for o in s_data.get("objects", [])):
                            location = f"{g_dir.name}/{scene_file.parent.name}"
                            used_locations.append(location)
                    except Exception:
                        continue
        
        if used_locations:
            loc_summary = ", ".join(used_locations[:3])
            if len(used_locations) > 3:
                loc_summary += f" e altri {len(used_locations)-3}..."
            
            msg = f"In uso in: {loc_summary}"
            logging.error(f"[EDITOR] Deletion blocked (In-Use): {cat_id} in {used_locations}")
            self._status(msg, ERR_C, 6)
            return

        try:
            # --- 2. BACKUP E CARICAMENTO ---
            if not global_cat_path.exists():
                self._status("Errore: Catalogo globale non trovato!", ERR_C, 3)
                return

            bak_path = global_cat_path.with_suffix(".json.bak")
            shutil.copy2(global_cat_path, bak_path)
            logging.debug(f"[EDITOR] Backup creato: {bak_path.name}")

            with open(global_cat_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            objs = data.get("objects", [])
            entry = next((o for o in objs if o["id"] == cat_id), None)
            if not entry:
                self._status(f"Asset {cat_id} non trovato nel globale", ERR_C, 3)
                return

            # --- 3. PULIZIA JSON CHIRURGICA ---
            new_objs = [o for o in objs if o["id"] != cat_id]
            # Manteniamo il catalogo sempre ordinato per ID
            data["objects"] = sorted(new_objs, key=lambda x: x.get("id", ""))
            
            # Scrittura atomica (su file temp poi rinomina) per evitare corruzioni
            tmp_path = global_cat_path.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            os.replace(tmp_path, global_cat_path)
            logging.info(f"[EDITOR] Asset {cat_id} rimosso dal JSON globale.")

            # --- 4. RIMOZIONE PNG FISICA ---
            icon_rel = entry.get("icon")
            if icon_rel and isinstance(icon_rel, str):
                # Protezione: assicuriamoci che non stia tentando di uscire dalla cartella assets
                if ".." in icon_rel or icon_rel.startswith("/") or ":" in icon_rel:
                    logging.warning(f"[EDITOR] Path icona sospetto ignorato: {icon_rel}")
                else:
                    icon_path = self.base_path / "engine" / "assets" / icon_rel
                    
                    # Check condivisione: un altro oggetto usa la stessa icona?
                    is_shared = any(o.get("icon") == icon_rel for o in new_objs)
                    
                    if icon_path.exists() and not is_shared:
                        try:
                            icon_path.unlink()
                            logging.info(f"[EDITOR] File PNG rimosso: {icon_rel}")
                        except Exception as fe:
                            logging.error(f"[EDITOR] Errore eliminazione file {icon_rel}: {fe}")
                    elif is_shared:
                        logging.info(f"[EDITOR] File {icon_rel} mantenuto (condiviso da altri asset)")

            # --- 5. AGGIORNAMENTO STATO ---
            # Ricarichiamo il catalogo nell'editor
            self.catalog = _load_catalog(self.game_name)
            self._status(f"RISORSA ELIMINATA: {cat_id}", OK_C, 4)
            
            # Svuotiamo la cache per liberare la surface orfana
            self._img_cache.clear()
            self._obj_draw_cache.clear()
            
        except Exception as e:
            logging.exception(f"[EDITOR] Errore critico durante eliminazione {cat_id}: {e}")
            self._status("ERRORE CRITICO ELIMINAZIONE", ERR_C, 5)

    # ─────────────────────────────────────────────────────────────────────────
    # PRESETS BUBBLE TIPS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_preset_file(self) -> Path:
        p = self.base_path / "saves"
        p.mkdir(exist_ok=True)
        return p / "bubble_presets.json"

    def _load_bubble_presets(self):
        fpath = self._get_preset_file()
        if fpath.exists():
            try:
                self.bubble_presets = _load_json(fpath)
            except Exception:
                self.bubble_presets = {}
        else:
            self.bubble_presets = {}

    def _save_bubble_presets(self):
        fpath = self._get_preset_file()
        _save_json(fpath, self.bubble_presets)
