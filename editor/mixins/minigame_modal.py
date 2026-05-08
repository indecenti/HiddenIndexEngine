"""
editor/mixins/minigame_modal.py

Gestisce la modale di selezione del minigioco da associare a un oggetto.
Scansiona dynamicamente la cartella engine/minigames/ per trovare i manifest.
"""

import json
import pygame
from pathlib import Path
from editor.constants import (
    PANEL, BORDER, BTN, BTN_AC, BTN_HO, ACCENT,
    TXT, TXT_HI, TXT_DIM, OK_C, ERR_C
)
from editor.ui.draw import (
    _rect, _txt, _draw_text, _button, _in_rect, _scrollbar, _clamp
)

class MinigameModalMixin:
    def _minigame_open(self):
        """Inizializza la modale scansionando i minigiochi disponibili."""
        self._minigame_modal = True
        self._available_minigames = []
        self._minigame_scroll = 0
        
        # Scansione directory engine/minigames/ (usiamo base_path per sicurezza)
        minigames_path = self.base_path / "engine" / "minigames"
        if minigames_path.exists():
            for p in minigames_path.iterdir():
                if p.is_dir():
                    manifest_file = p / "manifest.json"
                    if manifest_file.exists():
                        try:
                            with open(manifest_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                data["path"] = p
                                
                                # Carica descrizione localizzata
                                lang = getattr(self, "current_lang", "it")
                                strings_file = p / "strings" / f"{lang}.json"
                                if not strings_file.exists():
                                    strings_file = p / "strings" / "en.json"
                                
                                if strings_file.exists():
                                    try:
                                        with open(strings_file, "r", encoding="utf-8") as sf:
                                            sdata = json.load(sf)
                                            # Priorità: mg_description -> description (dal manifest)
                                            data["description"] = sdata.get("mg_description", data.get("description", ""))
                                            # Priorità: mg_title -> nome (dal manifest)
                                            data["name"] = sdata.get("mg_title", data.get("name", data["id"]))
                                    except:
                                        pass
                                        
                                self._available_minigames.append(data)
                        except Exception as e:
                            print(f"Errore caricamento manifest {p.name}: {e}")

    def _r_minigame_modal(self, w, h):
        """Rendering della modale di selezione minigioco."""
        mw, mh = 800, 600
        mx0, my0 = (w - mw) // 2, (h - mh) // 2
        
        # Overlay scuro
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        # Box modale
        _rect(self.screen, PANEL, (mx0, my0, mw, mh), radius=10)
        _rect(self.screen, BORDER, (mx0, my0, mw, mh), 2, radius=10)
        
        # Titolo
        _draw_text(self.screen, self._TR("mg_modal_title"), "lg", ACCENT, mx0 + 25, my0 + 20)
        pygame.draw.line(self.screen, BORDER, (mx0 + 20, my0 + 55), (mx0 + mw - 20, my0 + 55))
        
        # Area lista
        list_r = pygame.Rect(mx0 + 20, my0 + 70, mw - 40, mh - 130)
        _rect(self.screen, (20, 20, 25), list_r, radius=6)
        
        mx, my_raw = pygame.mouse.get_pos()
        self._minigame_hitboxes = []
        self._minigame_play_hitboxes = []
        
        if not self._available_minigames:
            _draw_text(self.screen, self._TR("mg_modal_empty"), "sm", ERR_C, list_r.x + 20, list_r.y + 20)
        else:
            # Clipping per lo scrolling
            old_clip = self.screen.get_clip()
            self.screen.set_clip(list_r)
            
            row_h = 70
            curr_y = list_r.y - (self._minigame_scroll * row_h)
            
            for mg in self._available_minigames:
                has_scroll = len(self._available_minigames) > 7
                row_w = list_r.w - 10 - (15 if has_scroll else 0)
                row_r = pygame.Rect(list_r.x + 5, curr_y, row_w, row_h - 5)
                
                # Renderizza solo se visibile
                if row_r.bottom > list_r.top and row_r.top < list_r.bottom:
                    hov = _in_rect((mx, my_raw), row_r)
                    
                    obj = self.scene_data["objects"][self.selected_idx]
                    is_cur = obj.get("minigame_trigger", {}).get("minigame_id") == mg["id"]
                    
                    bg_c = BTN_AC if is_cur else (BTN_HO if hov else BTN)
                    _rect(self.screen, bg_c, row_r, radius=6)
                    _rect(self.screen, ACCENT if is_cur else BORDER, row_r, 2 if is_cur else 1, radius=6)
                    
                    # Icona con Proporzioni (Aspect Fit)
                    icon_name = mg.get("icon")
                    off_x = 15
                    if icon_name:
                        ip = mg["path"] / icon_name
                        if ip.exists():
                            try:
                                # Usiamo una superficie temporanea per il ratio (veloce se già in memoria)
                                tmp = pygame.image.load(str(ip))
                                tw, th = tmp.get_size()
                                ratio = tw / th
                                
                                # Box 110x50
                                mw_icon, mh_icon = 110, 50
                                sw, sh = mw_icon, int(mw_icon / ratio)
                                if sh > mh_icon:
                                    sh = mh_icon
                                    sw = int(mh_icon * ratio)
                                
                                ic = self._load_img(ip, (sw, sh))
                                if ic:
                                    # Center in side the 110x50 area
                                    ix = row_r.x + 10 + (mw_icon - sw) // 2
                                    iy = row_r.y + (row_h - 5 - sh) // 2
                                    self.screen.blit(ic, (ix, iy))
                                    off_x = 135
                            except Exception:
                                off_x = 15

                    # Info
                    mg_name = mg.get("name", mg["id"])
                    max_w = row_r.w - 110 - off_x
                    _draw_text(self.screen, mg_name, "md", TXT_HI, row_r.x + off_x, row_r.y + 12, max_w=max_w)
                    _draw_text(self.screen, mg.get("description", ""), "sm", TXT_DIM, row_r.x + off_x, row_r.y + 36, max_w=max_w)
                    
                    # Tasto PLAY rapido a destra
                    play_r = pygame.Rect(row_r.right - 100, row_r.y + (row_r.h - 30)//2, 80, 30)
                    play_hov = _in_rect((mx, my_raw), play_r)
                    _button(self.screen, play_r, self._TR("mg_btn_start"), play_hov, custom_bg=(45, 170, 95))
                    
                    self._minigame_hitboxes.append((mg["id"], row_r))
                    self._minigame_play_hitboxes.append((mg["id"], play_r))
                
                curr_y += row_h

            self.screen.set_clip(old_clip)
            
            visible_rows = list_r.h // row_h
            _scrollbar(
                self.screen, list_r.right - 10, list_r.y + 5, 6, list_r.h - 10,
                self._minigame_scroll, len(self._available_minigames), visible_rows
            )

        # Tasto Chiudi
        close_r = pygame.Rect(mx0 + mw - 120, my0 + mh - 45, 100, 32)
        if _button(self.screen, close_r, self._TR("mg_btn_close"), _in_rect((mx, my_raw), close_r)):
            pass 
        self._minigame_close_rect = close_r

    def _minigame_click(self, mx, my):
        """Gestione click nella modale minigiochi."""
        if _in_rect((mx, my), getattr(self, "_minigame_close_rect", pygame.Rect(0,0,0,0))):
            self._minigame_modal = False
            return
            
        # Check su tasti PLAY
        for mg_id, r in getattr(self, "_minigame_play_hitboxes", []):
            if _in_rect((mx, my), r):
                self._test_minigame(mg_id)
                return

        # Check su selezione riga
        for mg_id, r in getattr(self, "_minigame_hitboxes", []):
            if _in_rect((mx, my), r):
                self._push_undo()
                obj = self.scene_data["objects"][self.selected_idx]
                if "minigame_trigger" not in obj:
                    obj["minigame_trigger"] = {"minigame_id": mg_id}
                else:
                    obj["minigame_trigger"]["minigame_id"] = mg_id
                
                self.scene_dirty = True
                self._status(self._TR("mg_status_linked").format(mg_id), OK_C, 2)
                self._minigame_modal = False
                return

    def _minigame_wheel(self, dy):
        """Gestisce lo scroll della modale."""
        curr_len = len(self._available_minigames)
        row_h = 70
        mw, mh = 800, 600
        list_h = mh - 130
        visible_rows = list_h // row_h
        max_scr = max(0, curr_len - visible_rows)
        self._minigame_scroll = _clamp(self._minigame_scroll - dy, 0, max_scr)

    def _test_minigame(self, mg_id):
        """Avvia il minigioco in modalità test separata."""
        import subprocess
        import sys
        
        self._status(self._TR("mg_status_testing").format(mg_id), ACCENT, 2)
        
        # Determiniamo il comando per avviare il gioco con il flag --minigame
        # Passiamo la lingua corrente dell'editor per coerenza
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, "--game", self.game_name, "--minigame", mg_id, "--lang", self.current_lang]
        else:
            cmd = [sys.executable, "main.py", "--game", self.game_name, "--minigame", mg_id, "--lang", self.current_lang]
        
        try:
            # Avviamo come processo asincrono per non bloccare l'editor
            proc = subprocess.Popen(cmd, cwd=self.base_path)
            self._build_processes.append(proc)
        except Exception as e:
            self._status(f"Errore avvio test: {e}", ERR_C, 3)
