"""
editor/mixins/object_ops.py

ObjectOpsMixin — operazioni sugli oggetti: handles, hit-test, selezione,
                 piazzamento, delete, duplicate, layer, context menu.
"""

import copy
import math
import logging
import pygame
import random
import re
from pathlib import Path

from editor.constants import (
    HANDLE_R, MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_SCATTER,
    ACCENT, BORDER, BTN, PANEL,
    TXT, TXT_DIM, TXT_HI, SEL_C, OK_C, ERR_C, WARN_C,
    TAB_PROPS, REF_W, REF_H,
)
from editor.core.io import _default_obj
from editor.ui.draw import _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _slider
from editor.constants import layer_z, layer_color


class ObjectOpsMixin:
    """Handles, hit-test, operazioni CRUD oggetti, context menu."""

    # ─────────────────────────────────────────────────────────────────────────
    # HANDLES
    # ─────────────────────────────────────────────────────────────────────────

    def _obj_handles(self, obj: dict) -> list:
        """Restituisce [(handle_id, screen_x, screen_y), ...]"""
        dt  = obj.get("detection_type", "circle")
        x, y = obj["x"], obj["y"]
        rot  = obj.get("rotation", 0)

        # Carica offset angoli
        coff = obj.get("corners", [[0,0], [0,0], [0,0], [0,0]]) # NW, NE, SE, SW

        if dt == "circle":
            r_x = obj.get("width", obj.get("radius", 30) * 2) / 2
            r_y = obj.get("height", obj.get("radius", 30) * 2) / 2
            pts = [
                ("move", x,   y),
                ("nw",   x-r_x+coff[0][0], y-r_y+coff[0][1]), 
                ("n",    x,                y-r_y+(coff[0][1]+coff[1][1])/2), 
                ("ne",   x+r_x+coff[1][0], y-r_y+coff[1][1]),
                ("e",    x+r_x+(coff[1][0]+coff[2][0])/2, y),
                ("se",   x+r_x+coff[2][0], y+r_y+coff[2][1]), 
                ("s",    x,                y+r_y+(coff[2][1]+coff[3][1])/2),
                ("sw",   x-r_x+coff[3][0], y+r_y+coff[3][1]), 
                ("w",    x-r_x+(coff[0][0]+coff[3][0])/2, y),
                ("rot",  x,     y-r_y-25),
            ]
            res = []
            for hid, rx, ry in pts:
                rrx, rry = self._rotate_pt(rx, ry, x, y, rot)
                sx_h, sy_h = self._r2s(rrx, rry)
                res.append((hid, sx_h, sy_h))
            return res

        elif dt == "rect":
            w  = obj.get("width",  60)
            h  = obj.get("height", 60)
            cx, cy = x + w/2, y + h/2
            pts = [
                ("move", cx,   cy),
                ("nw",   x+coff[0][0],   y+coff[0][1]),
                ("n",    cx+(coff[0][0]+coff[1][0])/2, y+(coff[0][1]+coff[1][1])/2),
                ("ne",   x+w+coff[1][0], y+coff[1][1]),
                ("e",    x+w+(coff[1][0]+coff[2][0])/2, cy+(coff[1][1]+coff[2][1])/2),
                ("se",   x+w+coff[2][0], y+h+coff[2][1]),
                ("s",    cx+(coff[2][0]+coff[3][0])/2, y+h+(coff[2][1]+coff[3][1])/2),
                ("sw",   x+coff[3][0],   y+h+coff[3][1]),
                ("w",    x+(coff[0][0]+coff[3][0])/2, cy+(coff[0][1]+coff[3][1])/2),
                ("rot",  cx,   y-25),
            ]
            res = []
            for hid, rx, ry in pts:
                rrx, rry = self._rotate_pt(rx, ry, cx, cy, rot)
                sx_h, sy_h = self._r2s(rrx, rry)
                res.append((hid, sx_h, sy_h))
            return res
        return []

    def _fx_handles(self, fx: dict) -> list:
        """Restituisce handles per gli effetti visivi."""
        t_type = fx.get("type", "glint")
        x, y = fx["x"], fx["y"]
        if t_type == "bubble_tip":
            w = fx.get("width", 300)
            h = fx.get("height", 180)
            bx, by = x - w // 2, y - h - 35
            cx, cy = x, by + h / 2
            pts = [
                ("move", cx, cy),
                ("nw", bx, by), ("ne", bx+w, by), ("se", bx+w, by+h), ("sw", bx, by+h),
                ("n", cx, by), ("s", cx, by+h), ("e", bx+w, cy), ("w", bx, cy)
            ]
            res = []
            for hid, rx, ry in pts:
                sx_h, sy_h = self._r2s(rx, ry)
                res.append((hid, sx_h, sy_h))
            return res
        else:
            sx, sy = self._r2s(x, y)
            r = fx.get("radius", 55)
            # Garantisce che l'handle sia sempre a una distanza minima cliccabile (almeno 20px)
            display_r = max(20, r)
            sx_r, sy_r = self._r2s(x + display_r, y)
            return [("move", sx, sy), ("radius", sx_r, sy_r)]

    def _hit_handle(self, obj: dict, mpos) -> str:
        for hid, hx, hy in self._obj_handles(obj):
            if math.hypot(mpos[0]-hx, mpos[1]-hy) <= HANDLE_R + 3:
                return hid
        return None

    def _hit_obj(self, obj: dict, rx, ry) -> bool:
        dt  = obj.get("detection_type", "circle")
        rot = obj.get("rotation", 0)
        ox, oy = obj["x"], obj["y"]
        if dt == "circle":
            cx, cy = ox, oy
            rrx, rry = self._rotate_pt(rx, ry, cx, cy, -rot)
            r_x = obj.get("width",  obj.get("radius", 30) * 2) / 2
            r_y = obj.get("height", obj.get("radius", 30) * 2) / 2
            dx, dy = rrx - ox, rry - oy
            if r_x <= 0 or r_y <= 0: return False
            return (dx / r_x) ** 2 + (dy / r_y) ** 2 <= 1.0001
        elif dt == "rect":
            w, h = obj.get("width", 60), obj.get("height", 60)
            cx, cy = ox + w/2, oy + h/2
            rrx, rry = self._rotate_pt(rx, ry, cx, cy, -rot)
            return ox <= rrx <= ox+w and oy <= rry <= oy+h
        return False

    def _effects_at(self, rx: float, ry: float) -> list:
        hits = []
        effects = self.scene_data.get("effects", [])
        for i, fx in enumerate(effects):
            # Controllo visibilità layer effetti
            lid = fx.get("layer", "effects")
            if not getattr(self, "layer_vis", {}).get(lid, True):
                continue
                
            t_type = fx.get("type", "glint")
            if t_type == "bubble_tip":
                bw, bh = fx.get("width", 300), fx.get("height", 180)
                bx, by = fx["x"] - bw // 2, fx["y"] - bh - 35
                if bx <= rx <= bx + bw and by <= ry <= by + bh:
                    hits.append(i)
                elif math.hypot(rx - fx["x"], ry - fx["y"]) < 15:
                    hits.append(i)
            else:
                if math.hypot(rx - fx["x"], ry - fx["y"]) < 20:
                    hits.append(i)
        return list(reversed(hits))

    def _objs_at(self, rx: float, ry: float) -> list:
        hits = []
        for i, obj in enumerate(self.scene_data.get("objects", [])):
            # Filtro layer visibili e non bloccati
            lid = obj.get("layer", "objects_mid")
            if not getattr(self, "layer_vis", {}).get(lid, True):
                continue
            if getattr(self, "layer_locked", {}).get(lid, False):
                continue
                
            if self._hit_obj(obj, rx, ry):
                hits.append((layer_z(lid), i))
        hits.sort(key=lambda t: -t[0])
        return [i for _, i in hits]

    def _do_box_selection(self):
        """Seleziona gli oggetti il cui centro ricade nel rettangolo marquee."""
        if not getattr(self, "_sel_box_active", False):
            return

        # Calcolo rettangolo in coordinate mondo
        x1, y1 = self._sel_box_start
        x2, y2 = self._sel_box_cur
        sel_rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

        # Ignora marquee troppo piccoli (click accidentali)
        if sel_rect.width < 4 and sel_rect.height < 4:
            return

        mods = pygame.key.get_mods()
        shift = bool(mods & pygame.KMOD_SHIFT)

        # Se non c'è shift, la selezione è già stata pulita in _sel_down
        new_selection = list(self.selected_indices) if shift else []
        objs = self.scene_data.get("objects", [])
        added_count = 0

        for i, obj in enumerate(objs):
            # Filtro per layer visibili e non bloccati
            lid = obj.get("layer", "objects_mid")
            if not self.layer_vis.get(lid, True) or self.layer_locked.get(lid, False):
                continue

            # Calcolo centro oggetto
            dt = obj.get("detection_type", "circle")
            if dt == "circle":
                ox, oy = obj["x"], obj["y"]
            else:
                w, h = obj.get("width", 60), obj.get("height", 60)
                ox, oy = obj["x"] + w / 2, obj["y"] + h / 2

            if sel_rect.collidepoint(ox, oy):
                if i not in new_selection:
                    new_selection.append(i)
                    added_count += 1

        if added_count > 0 or (not shift and len(self.selected_indices) > 0):
            self.selected_indices = new_selection
            if self.selected_indices:
                self.selected_idx = self.selected_indices[-1]
                # Sincronizza layer attivo con l'ultimo selezionato
                self.active_layer = objs[self.selected_idx].get("layer", "objects_mid")
                self.r_tab = TAB_PROPS
            else:
                self.selected_idx = None
            
            self._status(f"Selezione di gruppo: {len(self.selected_indices)} oggetti", ACCENT, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # PIAZZAMENTO / CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def _sel_catalog(self) -> dict:
        if self.catalog_sel is None: return None
        return next((c for c in self.catalog if c["id"] == self.catalog_sel), None)

    def _confirm_circle(self, mx, my):
        cat = self._sel_catalog()
        if not cat: self._cancel_rect(); return
        cx, cy = self._circle_ref_center
        r = self._snap(self._circle_ref_radius)
        if r < 5: self._cancel_rect(); return
        
        # Sanificazione layer di creazione
        lyr = self.active_layer
        if lyr not in ("objects_low", "objects_mid", "objects_high"):
            lyr = "objects_mid"
            self.active_layer = lyr
            self._status("Layer auto-impostato su: MEDIO", WARN_C, 1)
        
        # Forza visibilità se nascosto
        if not self.layer_vis.get(lyr, True):
            self.layer_vis[lyr] = True
            self._status(f"Layer '{lyr}' riattivato per visualizzare nuovo oggetto", ACCENT, 1)

        if self.layer_locked.get(lyr, False):
            self._status(f"Impossibile aggiungere: layer '{lyr}' bloccato!", ERR_C, 2)
            self._cancel_rect(); return

        obj = _default_obj(cat["id"], cx, cy, "circle", radius=r,
                           hint_delay=cat.get("default_hint_delay", 30),
                           layer=lyr)
        self._push_undo()
        self.scene_data.setdefault("objects", []).append(obj)
        new_idx = len(self.scene_data["objects"]) - 1
        self.selected_idx = new_idx
        self.selected_indices = [new_idx]
        self.sel_effect_idx = None
        self._cancel_rect()
        self.mode = MODE_SELECT
        # Harvesting immediato: copia PNG + aggiorna catalog JSON di gioco
        self._harvest_asset(cat["id"])
        # Garantisce che il label_key dell'oggetto esista in tutti i file lingua
        label_key = cat.get("label_key", f"obj_{cat['id']}")
        missing = self._ensure_translation_key(label_key)
        if missing:
            self._status(f"⚠ Traduci '{label_key}' ({', '.join(missing)})", WARN_C, 4)
        else:
            self._status(f"Aggiunto: {cat['id']} (cerchio)", OK_C, 2)

    def _confirm_rect(self, mx, my):
        cat = self._sel_catalog()
        if not cat: self._cancel_rect(); return
        rx1, ry1 = self._rect_ref_start
        rx2, ry2 = self._rect_ref_cur
        x, y = self._snap(min(rx1, rx2)), self._snap(min(ry1, ry2))
        w, h = self._snap(abs(rx2 - rx1)), self._snap(abs(ry2 - ry1))
        if w < 5 or h < 5: self._cancel_rect(); return

        # Sanificazione layer di creazione
        lyr = self.active_layer
        if lyr not in ("objects_low", "objects_mid", "objects_high"):
            lyr = "objects_mid"
            self.active_layer = lyr
            self._status("Layer auto-impostato su: MEDIO", WARN_C, 1)
            
        # Forza visibilità se nascosto
        if not self.layer_vis.get(lyr, True):
            self.layer_vis[lyr] = True
            self._status(f"Layer '{lyr}' riattivato per visualizzare nuovo oggetto", ACCENT, 1)
            
        if self.layer_locked.get(lyr, False):
            self._status(f"Impossibile aggiungere: layer '{lyr}' bloccato!", ERR_C, 2)
            self._cancel_rect(); return

        obj = _default_obj(cat["id"], x, y, "rect", width=max(10, w), height=max(10, h),
                           hint_delay=cat.get("default_hint_delay", 30),
                           layer=lyr)
        self._push_undo()
        self.scene_data.setdefault("objects", []).append(obj)
        self.scene_dirty = True
        new_idx = len(self.scene_data["objects"]) - 1
        self.selected_idx = new_idx
        self.selected_indices = [new_idx]
        self.sel_effect_idx = None
        self._cancel_rect()
        self.mode = MODE_SELECT
        # Harvesting immediato: copia PNG + aggiorna catalog JSON di gioco
        self._harvest_asset(cat["id"])
        # Garantisce che il label_key dell'oggetto esista in tutti i file lingua
        label_key = cat.get("label_key", f"obj_{cat['id']}")
        missing = self._ensure_translation_key(label_key)
        if missing:
            self._status(f"⚠ Traduci '{label_key}' ({', '.join(missing)})", WARN_C, 4)
        else:
            self._status(f"Aggiunto: {cat['id']} (rect)", OK_C, 2)

    def _scatter_click(self, mx, my_raw):
        """Piazza 4 oggetti casuali dal catalogo vicino al cursore."""
        if not self.catalog:
            self._status("Nessun oggetto nel catalogo", ERR_C, 2)
            return

        # --- 1. Analisi Stile Dominante (Intelligenza Contestuale) ---
        scene_objs = self.scene_data.get("objects", [])
        chosen_pool = self.catalog
        if scene_objs:
            # Mappa rapida ID -> Stile
            style_map = {c["id"]: c.get("style", "real") for c in self.catalog}
            scene_styles = [style_map.get(o.get("catalog_id"), "real") for o in scene_objs]
            total = len(scene_styles)
            
            # Se uno stile domina al 90%, restringiamo il pool a quello stile
            real_p = scene_styles.count("real") / total
            la_p = scene_styles.count("line art") / total
            ca_p = scene_styles.count("cartoon") / total
            
            if real_p >= 0.9:
                chosen_pool = [c for c in self.catalog if c.get("style") == "real"]
            elif la_p >= 0.9:
                chosen_pool = [c for c in self.catalog if c.get("style") == "line art"]
            elif ca_p >= 0.9:
                chosen_pool = [c for c in self.catalog if c.get("style") == "cartoon"]
            
            # Fallback se il pool filtrato è vuoto per errore di catalogazione
            if not chosen_pool: chosen_pool = self.catalog

        rx, ry = self._s2r(mx, my_raw)
        self._push_undo()

        # Scegliamo 4 oggetti random dal pool (filtrato o globale)
        count = 4
        if len(chosen_pool) < count:
            chosen_cats = random.choices(chosen_pool, k=count)
        else:
            chosen_cats = random.sample(chosen_pool, count)

        new_indices = []

        # Calcolo fattore di scala basato sulla scena (rif 1280x720)
        sw, sh = (REF_W, REF_H)
        if getattr(self, "bg_surf", None):
            sw, sh = self.bg_surf.get_size()
        
        scale = sw / REF_W
        
        # Offset dinamici scalati
        off_v = 60 * scale
        offsets = [
            (-off_v, -off_v), (off_v, -off_v),
            (-off_v,  off_v), (off_v,  off_v)
        ]

        for i, cat in enumerate(chosen_cats):
            ox_off, oy_off = offsets[i]
            tx, ty = self._snap(rx + ox_off), self._snap(ry + oy_off)
            
            # Sanificazione layer di creazione
            lyr = self.active_layer
            if lyr not in ("objects_low", "objects_mid", "objects_high"):
                lyr = "objects_mid"
                self.active_layer = lyr
                self._status("Layer auto-impostato su: MEDIO", WARN_C, 1)
            
            # Forza visibilità se nascosto
            if not self.layer_vis.get(lyr, True):
                self.layer_vis[lyr] = True
                self._status(f"Layer '{lyr}' riattivato", ACCENT, 1)

            if self.layer_locked.get(lyr, False):
                self._status(f"Scatter interrotto: layer '{lyr}' bloccato!", ERR_C, 2)
                return

            # Determina tipo rilevamento e dimensioni base
            dt = cat.get("default_detection_type", "circle")
            hd = cat.get("default_hint_delay", 30)

            # --- Calcolo scala intelligente (Tag + Jitter casuale) ---
            tags = cat.get("tags", [])
            tag_scale = 1.0
            if "piccolo" in tags:
                tag_scale = 0.7
            elif "grande" in tags:
                tag_scale = 1.5
            
            # Jitter per naturalezza (variazione del 10%)
            jitter = random.uniform(0.9, 1.1)
            f_scale = scale * tag_scale * jitter

            # Jitter posizione per evitare effetto griglia (±15px scalati)
            pjx = random.uniform(-15, 15) * scale
            pjy = random.uniform(-15, 15) * scale
            tx, ty = self._snap(rx + ox_off + pjx), self._snap(ry + oy_off + pjy)

            if dt == "circle":
                r_def = cat.get("default_radius", 30)
                obj = _default_obj(cat["id"], tx, ty, "circle", 
                                   radius=round(r_def * f_scale),
                                   hint_delay=hd,
                                   layer=lyr)
            else:
                w_def = cat.get("default_width", 60)
                h_def = cat.get("default_height", 60)
                nw, nh = round(w_def * f_scale), round(h_def * f_scale)
                obj = _default_obj(cat["id"], tx - nw/2, ty - nh/2, "rect", 
                                   width=nw, height=nh,
                                   hint_delay=hd,
                                   layer=lyr)
            
            self.scene_data.setdefault("objects", []).append(obj)
            new_indices.append(len(self.scene_data["objects"]) - 1)
            # Harvesting immediato per ogni oggetto del cluster
            self._harvest_asset(cat["id"])

        self.scene_dirty = True
        self.selected_indices = new_indices
        self.selected_idx = new_indices[0] if new_indices else None
        self.sel_effect_idx = None
        # Garantisce placeholder traduzione per ogni catalogo usato nel cluster
        seen_keys = set()
        for idx in new_indices:
            cid = self.scene_data["objects"][idx].get("catalog_id")
            cat_entry = next((c for c in self.catalog if c["id"] == cid), None)
            if cat_entry:
                lk = cat_entry.get("label_key", f"obj_{cid}")
                if lk not in seen_keys:
                    seen_keys.add(lk)
                    self._ensure_translation_key(lk)
        self._status(f"Cluster creato: {len(new_indices)} oggetti inseriti", OK_C, 2)

    def _delete_sel(self):
        if not self.selected_indices and self.selected_idx is None: return
        indices = sorted(list(set(self.selected_indices + ([self.selected_idx] if self.selected_idx is not None else []))), reverse=True)
        for idx in indices:
            lid = self.scene_data["objects"][idx].get("layer", "objects_mid")
            if self.layer_locked.get(lid, False):
                self._status(f"Impossibile eliminare: layer '{lid}' bloccato!", ERR_C, 2)
                return
        # Raccoglie i catalog_id da eliminare PRIMA del pop
        deleted_catalog_ids = {self.scene_data["objects"][idx].get("catalog_id") for idx in indices}
        deleted_catalog_ids.discard(None)
        self._push_undo()
        for idx in indices: self.scene_data["objects"].pop(idx)
        self.selected_idx = None
        self.selected_indices = []
        self._ctx_menu = None  # Chiude il menu se aperto sul vecchio indice
        self.scene_dirty = True
        self._status(f"Rimosse {len(indices)} oggetti", WARN_C, 2)
        # Cleanup risorse orfane (traduzioni + PNG game-specific)
        if deleted_catalog_ids:
            self._cleanup_orphaned_assets(deleted_catalog_ids)

    def _cleanup_orphaned_assets(self, deleted_ids: set):
        """
        Per ogni catalog_id eliminato, verifica che NON sia usato in NESSUNA
        altra scena del gioco (né nella scena corrente in memoria).
        Solo se davvero orfano elimina:
          - label_key dai file lingua del gioco
          - PNG da games/{game}/objects/  (MAI dall'engine)
          - entry da games/{game}/objects_catalog.json

        Protezioni aggiuntive contro falsi positivi:
          - Due catalog_id che condividono lo stesso PNG: il PNG viene eliminato
            solo se il nome file non è più referenziato da NESSUN catalog_id
            ancora in uso (not just the deleted one).
          - Stessa protezione per label_key condivise tra più catalog entries.
          - PNG custom (non nell'engine master) non vengono mai eliminati.
        """
        import json as _json
        from editor.core.io import _load_json, _save_json
        if not getattr(self, 'game_path', None) or not deleted_ids:
            return

        # ── 1. Tutti i catalog_id ancora in uso (scena corrente + altre scene) ─
        still_used_ids: set[str] = {
            o.get("catalog_id") for o in self.scene_data.get("objects", [])
        }
        still_used_ids.discard(None)

        current_scene_path = getattr(self, 'scene_path', None)
        for scene_file in self.game_path.rglob("scene.json"):
            if current_scene_path and scene_file.resolve() == current_scene_path.resolve():
                continue  # scena corrente già considerata (in memoria)
            try:
                with open(scene_file, "r", encoding="utf-8") as f:
                    s_data = _json.load(f)
                for obj in s_data.get("objects", []):
                    cid = obj.get("catalog_id")
                    if cid:
                        still_used_ids.add(cid)
            except Exception:
                pass

        truly_orphaned = deleted_ids - still_used_ids
        if not truly_orphaned:
            return  # tutti gli oggetti eliminati sono ancora usati altrove

        catalog_map = {c["id"]: c for c in getattr(self, 'catalog', [])}
        master_assets_p = self.base_path / "engine" / "assets"

        # ── 2. Calcola icon_names e label_keys ancora in uso da catalog_id
        #       RIMASTI in uso (non eliminati). Serve per proteggere PNG e chiavi
        #       condivisi tra più oggetti.
        still_used_icon_names: set[str] = set()
        still_used_label_keys: set[str] = set()
        for cid in still_used_ids:
            cat = catalog_map.get(cid)
            if not cat:
                continue
            icon_rel = cat.get("icon", "")
            if icon_rel:
                still_used_icon_names.add(Path(icon_rel).name)
            lk = cat.get("label_key", f"obj_{cid}")
            if lk:
                still_used_label_keys.add(lk)

        removed_keys, removed_pngs, removed_json_ids = [], [], []

        for cid in truly_orphaned:
            cat = catalog_map.get(cid)
            if not cat:
                continue

            # ── A. Rimuove label_key dai file lingua del gioco ───────────────
            label_key = cat.get("label_key", f"obj_{cid}")
            if label_key and label_key not in still_used_label_keys:
                strings_dir = self.game_path / "strings"
                if strings_dir.exists():
                    for lang in getattr(self, 'LANGS', ['it', 'en', 'de', 'fr', 'es']):
                        lang_file = strings_dir / f"{lang}.json"
                        if lang_file.exists():
                            lang_data = _load_json(lang_file)
                            if label_key in lang_data:
                                del lang_data[label_key]
                                _save_json(lang_file, lang_data)
                                if label_key not in removed_keys:
                                    removed_keys.append(label_key)

            # ── B. Rimuove PNG dalla cartella di gioco (MAI dall'engine) ─────
            icon_rel = cat.get("icon", "")
            if icon_rel:
                icon_path = Path(icon_rel)
                icon_name = icon_path.name
                subfolder = icon_path.parent.name or "objects"
                
                # Protezione: non eliminare se lo stesso file è usato da
                # un altro catalog_id ancora attivo
                if icon_name not in still_used_icon_names:
                    game_png = self.game_path / subfolder / icon_name
                    if game_png.exists():
                        # Ulteriore protezione: elimina solo se esiste nel master
                        # engine (recuperabile). PNG custom rimangono sempre.
                        if (master_assets_p / icon_rel).exists():
                            try:
                                game_png.unlink()
                                removed_pngs.append(f"{subfolder}/{icon_name}")
                            except Exception as e:
                                logging.warning(f"[ASSET] Cleanup PNG fallito '{subfolder}/{icon_name}': {e}")
                        else:
                            logging.info(
                                f"[ASSET] PNG custom '{subfolder}/{icon_name}' mantenuto "
                                f"(non nell'engine master, non eliminabile)."
                            )

            # ── C. Segna entry per rimozione dal catalogo JSON di gioco ──────
            removed_json_ids.append(cid)

        # Aggiorna objects_catalog.json in un'unica scrittura atomica
        if removed_json_ids:
            game_cat_path = self.game_path / "objects_catalog.json"
            if game_cat_path.exists():
                try:
                    with open(game_cat_path, "r", encoding="utf-8") as f:
                        game_cat = _json.load(f)
                    game_cat["objects"] = [
                        o for o in game_cat.get("objects", [])
                        if o.get("id") not in removed_json_ids
                    ]
                    with open(game_cat_path, "w", encoding="utf-8") as f:
                        _json.dump(game_cat, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    logging.warning(f"[ASSET] Cleanup catalog JSON fallito: {e}")

        if removed_keys or removed_pngs:
            n = len(truly_orphaned)
            parts = [f"{n} oggett{'o' if n == 1 else 'i'} orfan{'o' if n == 1 else 'i'}"]
            if removed_keys:
                parts.append(f"{len(removed_keys)} chiav{'e' if len(removed_keys)==1 else 'i'} lingua rimoss{'a' if len(removed_keys)==1 else 'e'}")
            if removed_pngs:
                parts.append(f"{len(removed_pngs)} PNG rimoss{'o' if len(removed_pngs)==1 else 'i'}")
            self._status(" | ".join(parts), WARN_C, 5)

    def _duplicate(self):
        if not self.selected_indices and self.selected_idx is None: return
        indices = list(set(self.selected_indices + ([self.selected_idx] if self.selected_idx is not None else [])))
        for idx in indices:
            lid = self.scene_data["objects"][idx].get("layer", "objects_mid")
            if self.layer_locked.get(lid, False):
                self._status(f"Impossibile duplicare: layer '{lid}' bloccato!", ERR_C, 2)
                return
        self._push_undo()
        new_indices = []
        for idx in sorted(indices):
            obj = copy.deepcopy(self.scene_data["objects"][idx])
            obj["x"] += 20; obj["y"] += 20
            self.scene_data["objects"].append(obj)
            new_indices.append(len(self.scene_data["objects"]) - 1)
        self.selected_indices = new_indices
        self.selected_idx = new_indices[0] if new_indices else None
        self.scene_dirty = True
        self._status(f"Duplicati {len(indices)} oggetti", OK_C, 2)

    def _copy_sel(self):
        if not self.selected_indices and self.selected_idx is None: return
        indices = list(set(self.selected_indices + ([self.selected_idx] if self.selected_idx is not None else [])))
        self.clipboard = [copy.deepcopy(self.scene_data["objects"][i]) for i in indices]
        self._status(f"Copiati {len(self.clipboard)} oggetti", ACCENT, 2)

    def _cut_sel(self):
        if not self.selected_indices and self.selected_idx is None: return
        self._copy_sel()
        self._delete_sel()
        # Nota: _delete_sel fa già _push_undo e setta dirty

    def _paste_sel(self):
        if not self.clipboard: return
        for obj in self.clipboard:
            lid = obj.get("layer", "objects_mid")
            if self.layer_locked.get(lid, False):
                 self._status(f"Incolla negato: layer '{lid}' bloccato!", ERR_C, 2)
                 return
        self._push_undo()
        new_indices = []
        for obj in self.clipboard:
            new_obj = copy.deepcopy(obj)
            new_obj["x"] += 20; new_obj["y"] += 20
            self.scene_data["objects"].append(new_obj)
            new_indices.append(len(self.scene_data["objects"]) - 1)
        self.selected_indices = new_indices
        self.selected_idx = new_indices[0] if new_indices else None
        self.scene_dirty = True
        self._status(f"Incollati {len(self.clipboard)} oggetti", OK_C, 2)

    def _select_all(self):
        objs = self.scene_data.get("objects", [])
        if not objs: return
        self.selected_indices = list(range(len(objs)))
        self.selected_idx = self.selected_indices[-1]
        self._status(f"Selezionati tutti ({len(objs)} oggetti)", ACCENT, 2)

    def _set_layer(self, lid: str):
        self.active_layer = lid
        # Forza sempre visibilità quando si seleziona un layer come attivo
        if lid in ("objects_low", "objects_mid", "objects_high", "overlay"):
            if not self.layer_vis.get(lid, True):
                self.layer_vis[lid] = True
                self._status(f"Visibilità '{lid}' riattivata", ACCENT, 1)
                
        if self.selected_idx is not None:
            old_lid = self.scene_data["objects"][self.selected_idx].get("layer", "objects_mid")
            if self.layer_locked.get(old_lid, False):
                self._status(f"Spostamento negato: layer '{old_lid}' bloccato!", ERR_C, 2)
                return
            if self.layer_locked.get(lid, False):
                self._status(f"Spostamento negato: layer DESTINAZIONE '{lid}' bloccato!", ERR_C, 2)
                return
                
            self._push_undo()
            self.scene_data["objects"][self.selected_idx]["layer"] = lid
            self.scene_dirty = True
        else:
            self._status(f"Layer di creazione impostato: {lid}", ACCENT, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # CONTEXT MENU
    # ─────────────────────────────────────────────────────────────────────────

    def _ctx_open(self, mx: int, my_raw: int):
        rx, ry = self._s2r(mx, my_raw)
        
        # 1. Controllo effetti (testa solo quelli visibili)
        fx_hits = self._effects_at(rx, ry)
        if fx_hits:
            idx = fx_hits[0]
            self.sel_effect_idx = idx
            self.selected_idx = None
            self.selected_indices = []
            self._editing_prop = None  # Reset editing prop quando si cambia oggetto
            self._ctx_menu = {"pos": (mx, my_raw), "idx": idx, "type": "effect"}
            return
            
        # 2. Controllo oggetti (testa solo quelli visibili/non bloccati)
        hits = self._objs_at(rx, ry)
        if hits:
            idx = hits[0]
            self.selected_idx = idx
            self.sel_effect_idx = None
            self._editing_prop = None  # Reset editing prop
            
            # Estrazione palette per suggerimenti rapidi (primi 10 colori)
            palette = []
            if getattr(self, "bg_surf", None):
                try:
                    from editor.ui.color_picker import extract_palette
                    palette = extract_palette(self.bg_surf, 10)
                except Exception:
                    pass
            
            self._ctx_menu = {"pos": (mx, my_raw), "idx": idx, "type": "object", "palette": palette}
            return
            
        self._ctx_menu = None

    def _get_ctx_items(self):
        if not self._ctx_menu: return []
        
        # Catalogo
        if self._ctx_menu.get("type") == "catalog":
            cat_id = self._ctx_menu["cat_id"]
            items = [("edit_png", "Edit PNG (Editor Immagine)"), ("modify_tags", "Modifica Tag..."), ("sep", "---")]
            if self._ctx_menu.get("confirm_delete_cid") == cat_id:
                items.append(("delete_asset", "!! SICURO? (CLICCA ANCORA)"))
            else: items.append(("delete_asset", "ELIMINA RISORSA"))
            return items
            
        # Effetti
        if self._ctx_menu.get("type") == "effect":
            idx = self._ctx_menu["idx"]
            effects = self.scene_data.get("effects", [])
            if idx >= len(effects):
                self._ctx_menu = None
                return []
            fx = effects[idx]
            items = []
            if fx.get("type") == "bubble_tip": items.append(("fx_dupe", "Duplica Fumetto"))
            items += [("sep", "---"), ("fx_delete", "ELIMINA EFFETTO")]
            return items

        # Oggetti Scena
        idx = self._ctx_menu["idx"]
        objs = self.scene_data.get("objects", [])
        if idx >= len(objs):
            self._ctx_menu = None
            return []
        obj = objs[idx]
        is_gs = obj.get("grayscale", False)
        gs_lbl = f"Bianco e Nero: {int(obj.get('grayscale_factor', 1.0) * 100)}%" if is_gs else "Bianco e Nero"
        perc = int(obj.get("alpha", 255) / 255 * 100)
        
        items = [
            ("dupe",     "Duplica Oggetto"),
            ("delete",   "ELIMINA OGGETTO"),
            ("sep",      "---"),
            ("flip_x",   f"{'✓ ' if obj.get('flip_x') else ''}Specchia Orizzontalmente"),
            ("flip_y",   f"{'✓ ' if obj.get('flip_y') else ''}Specchia Verticalmente"),
            ("sep",      "---"),
            ("alpha",    f"Opacità: {perc}%"),
            ("grayscale", gs_lbl),
            ("color",    "Filtro Colore..."),
            ("sep",      "---"),
        ]
        
        # Reset dinamici
        cf = tuple(obj.get("color_filter", (255, 255, 255)))
        coff = obj.get("corners", [[0,0], [0,0], [0,0], [0,0]])
        has_warp = any(c[0] != 0 or c[1] != 0 for c in coff)
        
        if cf != (255, 255, 255) or has_warp:
            if cf != (255, 255, 255): items.append(("color_reset", "× Rimuovi Filtro Colore"))
            if has_warp: items.append(("warp_reset", "× Reset Prospettiva"))
            items.append(("sep", "---"))

        items += [
            ("l_high", "Porta in Primo Piano"),
            ("l_mid",  "Porta nel Mezzo"),
            ("l_low",  "Porta sullo Sfondo"),
            ("sep",      "---"),
            ("modify_tags", "Modifica Tag..."),
        ]
        return items

    def _get_item_h(self, cid: str) -> int:
        """Restituisce l'altezza dinamica per ogni tipo di voce del menu contestuale."""
        if cid in ["alpha", "grayscale"]: return 48
        if cid == "color": return 85 # Spazio per label + 2 righe di chip
        if cid == "sep": return 16
        return 32

    def _get_ctx_menu_info(self, items):
        if not self._ctx_menu: return 0, 0, 0, 0
        mx_orig, my_orig = self._ctx_menu["pos"]
        w_win, h_win = self.screen.get_size()
        
        max_tw = 185 
        total_h = 12 # Padding iniziale
        for cid, lbl in items:
            tw, _ = _text_wh(lbl, "sm")
            if tw > max_tw: max_tw = tw
            total_h += self._get_item_h(cid)
            
        m_w, m_h = max_tw + 60, total_h
        mx_m, my_m = mx_orig, my_orig
        if mx_m + m_w > w_win: mx_m -= m_w
        if my_m + m_h > h_win: my_m -= m_h
        return m_w, m_h, mx_m, my_m

    def _ctx_menu_click(self, mx, my_raw) -> bool:
        if not self._ctx_menu: return False
        items = self._get_ctx_items()
        m_w, m_h, mx_m, my_m = self._get_ctx_menu_info(items)
        
        y_off = my_m + 6
        # Catalogo
        if self._ctx_menu.get("type") == "catalog":
            cat_id = self._ctx_menu["cat_id"]
            for cid, lbl in items:
                ih = self._get_item_h(cid)
                ir = pygame.Rect(mx_m + 4, y_off, m_w - 8, ih - 2)
                if _in_rect((mx, my_raw), ir):
                    if cid == "edit_png": self._img_editor_open(cat_id); return False
                    elif cid == "modify_tags": self._tag_modal_open(cat_id); return False
                    elif cid == "delete_asset":
                        if self._ctx_menu.get("confirm_delete_cid") == cat_id: 
                            self._delete_catalog_asset(cat_id)
                            return False
                        else: 
                            self._ctx_menu["confirm_delete_cid"] = cat_id
                            return True
                y_off += ih
            return False

        # Effetti / Oggetti
        idx = self._ctx_menu["idx"]
        obj = self.scene_data["objects"][idx] if self._ctx_menu.get("type") == "object" else None
        
        for cid, lbl in items:
            ih = self._get_item_h(cid)
            if cid == "sep":
                y_off += ih
                continue
                
            ir = pygame.Rect(mx_m + 4, y_off, m_w - 8, ih - 2)
            if _in_rect((mx, my_raw), ir):
                if   cid == "dupe":   self._duplicate(); return False
                elif cid == "alpha" and obj:  
                    # Allineamento a 54px
                    sw = m_w - 68
                    sx = mx_m + 54
                    
                    # Pulsante toggle a SINISTRA (X=12)
                    btn_toggle_r = pygame.Rect(mx_m + 12, y_off + 10, 32, 24)
                    if _in_rect((mx, my_raw), btn_toggle_r):
                        self._push_undo()
                        # Invertiamo la logica: ON significa "Trasparenza attiva" (alpha < 255).
                        # Spegnere il pulsante (OFF) ora porta l'opacità al 100% (255).
                        # Accendere il pulsante (ON) porta l'opacità all'85% (217).
                        is_now_on = obj.get("alpha", 255) < 255
                        if is_now_on:
                            obj["alpha"] = 255
                        else:
                            obj["alpha"] = 217 # 85% di 255
                        self.scene_dirty = True
                        return True

                    # Slider
                    rel_x = max(0, min(1.0, (mx - sx) / sw))
                    self._push_undo(); obj["alpha"] = int(rel_x * 255); self.scene_dirty = True
                    self._dragging_ctx_slider = {"idx": idx, "key": "alpha", "sx": sx, "sw": sw}
                    return True
                elif cid == "flip_x" and obj:
                    self._push_undo()
                    obj["flip_x"] = not obj.get("flip_x", False)
                    self.scene_dirty = True
                    return True
                elif cid == "flip_y" and obj:
                    self._push_undo()
                    obj["flip_y"] = not obj.get("flip_y", False)
                    self.scene_dirty = True
                    return True
                elif cid == "grayscale" and obj:
                    # Pulsante toggle a SINISTRA (X=12)
                    btn_toggle_r = pygame.Rect(mx_m + 12, y_off + 10, 32, 24)
                    if _in_rect((mx, my_raw), btn_toggle_r):
                        self._push_undo()
                        is_now_on = obj.get("grayscale", False) and obj.get("grayscale_factor", 0.0) > 0
                        if is_now_on:
                            obj["grayscale"] = False
                            obj["grayscale_factor"] = 0.0
                        else:
                            obj["grayscale"] = True
                            obj["grayscale_factor"] = 1.0
                        self.scene_dirty = True
                        return True
                    
                    # Logic Slider Standard - Allineamento a 54px
                    sw = m_w - 68
                    sx = mx_m + 54
                    rel_x = max(0, min(1.0, (mx - sx) / sw))
                    
                    self._push_undo()
                    if rel_x < 0.05:
                        obj["grayscale"] = False
                        obj["grayscale_factor"] = 0.0
                    else:
                        obj["grayscale"] = True
                        obj["grayscale_factor"] = round(rel_x, 2)
                    
                    self.scene_dirty = True
                    self._dragging_ctx_slider = {"idx": idx, "key": "grayscale_factor", "sx": sx, "sw": sw}
                    return True
                elif cid == "color":
                    palette = self._ctx_menu.get("palette", [])
                    if palette:
                        for p_idx, p_col in enumerate(palette):
                            row = p_idx // 5
                            col = p_idx % 5
                            chip_r = pygame.Rect(mx_m + 54 + col*34, y_off + 32 + row*24, 30, 20)
                            if _in_rect((mx, my_raw), chip_r):
                                self._push_undo()
                                obj["color_filter"] = list(p_col)
                                self.scene_dirty = True
                                return False 
                    self._pick_color_for_sel(); return True
                elif cid == "color_reset" and obj: 
                    self._push_undo(); obj["color_filter"] = [255, 255, 255]; 
                    self.scene_dirty = True; return True
                elif cid == "warp_reset" and obj: 
                    self._push_undo(); obj["corners"] = [[0,0],[0,0],[0,0],[0,0]]; 
                    self.scene_dirty = True; return True
                elif cid == "l_high": self._set_layer("objects_high"); return False
                elif cid == "l_mid":  self._set_layer("objects_mid"); return False
                elif cid == "l_low":  self._set_layer("objects_low"); return False
                elif cid == "modify_tags":
                    self._tag_modal_open(obj["catalog_id"])
                    return False
                elif cid == "delete": self._delete_sel(); return False
                elif cid == "fx_dupe":
                    self._push_undo()
                    new_fx = copy.deepcopy(self.scene_data["effects"][idx])
                    self.scene_data["effects"].append(new_fx); self.scene_dirty = True; return False
                elif cid == "fx_delete": self._delete_effect_sel(); return False
                
            y_off += ih
        return False

    def _do_drag_ctx_slider(self, mx, my):
        """Aggiorna il valore dello slider del menu contestuale durante il trascinamento."""
        ds = getattr(self, "_dragging_ctx_slider", None)
        if not ds or self.selected_idx is None: return
        
        idx, key, sx, sw = ds["idx"], ds["key"], ds["sx"], ds["sw"]
        if idx >= len(self.scene_data["objects"]): return
        obj = self.scene_data["objects"][idx]
        
        rel_x = max(0.0, min(1.0, (mx - sx) / sw))
        
        if key == "alpha":
            obj["alpha"] = int(rel_x * 255)
        elif key == "grayscale_factor":
            if rel_x < 0.05:
                obj["grayscale"] = False
                obj["grayscale_factor"] = 0.0
            else:
                obj["grayscale"] = True
                obj["grayscale_factor"] = round(rel_x, 2)
        
        self.scene_dirty = True

    def _r_ctx_menu(self, w_win, h_win):
        if not self._ctx_menu: return
        mx, my_raw = pygame.mouse.get_pos()
        items = self._get_ctx_items()
        m_w, m_h, mx_m, my_m = self._get_ctx_menu_info(items)
        
        obj = None
        if self._ctx_menu.get("type") == "object":
            idx = self._ctx_menu.get("idx")
            if idx is not None and idx < len(self.scene_data.get("objects", [])):
                obj = self.scene_data["objects"][idx]

        rect = pygame.Rect(mx_m, my_m, m_w, m_h)
        _rect(self.screen, (32, 34, 46), rect, radius=12) # Radius aumentato
        _rect(self.screen, (70, 75, 95), rect, 1, radius=12)
        
        y_off = my_m + 6
        for cid, lbl in items:
            ih = self._get_item_h(cid)
            ir  = pygame.Rect(mx_m + 4, y_off, m_w - 8, ih - 2)
            hov = _in_rect((mx, my_raw), ir)
            
            if cid == "sep":
                pygame.draw.line(self.screen, (60, 65, 85), 
                                 (mx_m + 15, ir.centery), (mx_m + m_w - 15, ir.centery))
                y_off += ih
                continue
                
            if hov: 
                _rect(self.screen, (50, 55, 85), ir, radius=8)
            
            tc = TXT_HI
            if cid == "dupe": tc = ACCENT
            elif cid in ["delete", "fx_delete"]: tc = ERR_C
            elif cid in ["alpha", "grayscale", "color"]: tc = WARN_C
            elif cid.endswith("_reset"): tc = TXT_DIM
            elif hov: tc = TXT_HI
            else: tc = TXT
            
            # --- Rendering calibrato con icone/disegno a sinistra (X=12) e contenuti a destra (X=54) ---
            if obj and cid in ["alpha", "grayscale"]:
                val = (obj.get("alpha", 255) / 255.0) if cid == "alpha" else (obj.get("grayscale_factor", 1.0) if obj.get("grayscale") else 0.0)
                
                # Label & Slider allineati a destra
                self.screen.blit(_txt(lbl, "sm", tc), (ir.x + 50, ir.y + 6))
                _slider(self.screen, (ir.x + 50, ir.y + 30, ir.width - 64, 4), val, 0.0, 1.0, color=tc)

                # Toggle switch imponente a sinistra (X=12)
                btn_t_r = pygame.Rect(ir.x + 8, ir.y + 10, 32, 24)
                
                # Logica ON/OFF specifica
                if cid == "grayscale": is_on = obj.get("grayscale", False) and obj.get("grayscale_factor", 0.0) > 0
                else: is_on = obj.get("alpha", 255) < 255
                
                hov_t = _in_rect((mx, my_raw), btn_t_r)
                
                # Disegno Toggle (Track & Dot)
                _rect(self.screen, (ACCENT if is_on else (60, 65, 85)), btn_t_r, radius=12)
                dot_x = btn_t_r.x + (16 if is_on else 4)
                pygame.draw.circle(self.screen, (255, 255, 255), (dot_x + 6, btn_t_r.centery), 8)
                if hov_t: _rect(self.screen, TXT_HI, btn_t_r, 1, radius=12)

            elif obj and cid == "color":
                val_c = tuple(obj.get("color_filter", (255, 255, 255)))
                self.screen.blit(_txt(lbl, "sm", tc), (ir.x + 50, ir.y + 8))
                
                # Preview colore a sinistra
                prev_r = pygame.Rect(ir.x + 10, ir.y + 10, 30, 30)
                _rect(self.screen, val_c, prev_r, radius=6)
                _rect(self.screen, BORDER, prev_r, 1, radius=6)
                
                # Palette (allineata a X=54)
                palette = self._ctx_menu.get("palette", [])
                if palette:
                    for p_idx, p_col in enumerate(palette):
                        row = p_idx // 5
                        col = p_idx % 5
                        chip_r = pygame.Rect(ir.x + 50 + col*34, ir.y + 32 + row*24, 30, 20)
                        hov_c = _in_rect((mx, my_raw), chip_r)
                        _rect(self.screen, p_col, chip_r, radius=4)
                        _rect(self.screen, TXT_HI if hov_c else BORDER, chip_r, 1 if not hov_c else 2, radius=4)
            else:
                ts = _txt(lbl, "sm", tc)
                # Testo semplice allineato a X=54 (o centrato con icona placeholder)
                self.screen.blit(ts, (ir.x + 50, ir.y + (ir.height - ts.get_height()) // 2))
                # Spazio icona placeholder
                if cid != "sep":
                    pygame.draw.circle(self.screen, (55, 60, 80), (ir.x + 24, ir.centery), 3)

            y_off += ih

    def _pick_color_for_sel(self):
        if self.selected_idx is None: return
        obj = self.scene_data["objects"][self.selected_idx]
        try:
            from editor.ui.color_picker import ask_color
            bg_surf = getattr(self, "bg_surf", None)
            init_c = obj.get("color_filter", (255, 255, 255))
            color = ask_color(self.screen, bg_surf, init_c, title="Colore Filtro Oggetto")
            if color:
                self._push_undo(); obj["color_filter"] = [int(x) for x in color]; self.scene_dirty = True
        except Exception: logging.error("Color picker fallito (oggetto)")

    def _pick_color_for_effect(self, idx, key="color", title="Colore Effetto"):
        if idx is None or idx >= len(self.scene_data.get("effects", [])): return
        fx = self.scene_data["effects"][idx]
        try:
            from editor.ui.color_picker import ask_color
            bg_surf = getattr(self, "bg_surf", None)
            init_c = fx.get(key, (255, 215, 60))
            color = ask_color(self.screen, bg_surf, init_c, title=title)
            if color:
                self._push_undo(); fx[key] = [int(x) for x in color]; self.scene_dirty = True
        except Exception: logging.error("Color picker fallito (effetto)")

    def _delete_effect_sel(self):
        idx = getattr(self, "sel_effect_idx", None)
        if idx is not None and idx < len(self.scene_data.get("effects", [])):
            self._push_undo(); self.scene_data["effects"].pop(idx)
            self.sel_effect_idx = None
            self._ctx_menu = None # Chiude il menu
            self.scene_dirty = True
            self._status("Effetto rimosso", WARN_C, 2)

    def _sanitize_effects(self):
        """Assicura l'integrità degli effetti: chiavi univoche e layer condiviso."""
        if not self.scene_data: return
        effects = self.scene_data.get("effects", [])
        
        # 1. Trova tutte le chiavi usate per i fumetti
        used_keys = {} # key -> list of effect dicts
        for fx in effects:
            if fx.get("type") == "bubble_tip":
                k = fx.get("text_key", "NEW_TIP")
                used_keys.setdefault(k, []).append(fx)
        
        changed = False
        for k, fxs in used_keys.items():
            if len(fxs) > 1:
                # Duplicati! Teniamo il primo così com'è, cambiamo gli altri
                for i, fx in enumerate(fxs[1:], start=1):
                    import uuid, re
                    scene_str = str(self.scene_data.get("id", getattr(self.scene_path, "stem", "scene")))
                    scene_str = re.sub(r'[^a-zA-Z0-9]', '', scene_str)
                    uid = uuid.uuid4().hex[:5].upper()
                    new_k = f"TIP_{scene_str}_{uid}"
                    
                    # Copia le traduzioni se la vecchia chiave le aveva
                    self._copy_translations(fx.get("text_key"), new_k)
                    fx["text_key"] = new_k
                    changed = True
        
        # 2. Forza tutti gli effetti sul layer condiviso "effects"
        for fx in effects:
            if fx.get("layer") != "effects":
                fx["layer"] = "effects"
                changed = True
        
        if changed:
            self.scene_dirty = True

    def _copy_translations(self, old_key, new_key):
        """Copia le stringhe da una chiave all'altra in tutte le lingue."""
        if not hasattr(self, "_lang_data") or not self._lang_data:
            self._load_strings()
            
        for lang in self.LANG_IDS if hasattr(self, "LANG_IDS") else ["it", "en", "es", "fr", "de"]:
            if lang in self._lang_data and old_key in self._lang_data[lang]:
                if new_key not in self._lang_data[lang]:
                    self._lang_data[lang][new_key] = self._lang_data[lang][old_key]
                    self._lang_dirty = True

