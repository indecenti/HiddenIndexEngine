"""
engine/menu_system.py

Sistema di menu scalabile con supporto temi grafici.
Il tema viene caricato da games/<game_id>/ui_theme/theme.json (harvestato
dall'editor); se non presente, usa il tema 'default' dell'engine.
"""

import json
import pygame
import math

from engine.utils import get_logger, get_resource_path
from engine.menu_theme import MenuTheme, load_theme_for_game


class MenuButton:
    """Contenitore bottone scalabile con supporto icone/anteprime."""

    def __init__(
        self,
        text: str,
        action: str,
        rx: float,
        ry: float,
        rw: float,
        rh: float,
        image: pygame.Surface = None,
    ) -> None:
        self.text = text
        self.action = action
        self.ref_rect = pygame.Rect(rx, ry, rw, rh)  # Coordinate @ 1280x720
        self.hovered = False
        self.hover_time = 0.0  # 0.0 -> 1.0 per transizioni fluide
        self.image = image
        self.icon_surf = None # Icona tematica (opzionale)
        
        # Effetti Premium
        self.ripple_pos = None
        self.ripple_time = 0.0
        self.float_offset = 0.0


class MenuSlider:
    """Controllo range di valori (es: volume)."""

    def __init__(
        self,
        label: str,
        action: str,
        rx: float,
        ry: float,
        rw: float,
        rh: float,
        value: float,
    ) -> None:
        self.label = label
        self.action = action
        self.ref_rect = pygame.Rect(rx, ry, rw, rh)
        self.value = value
        self.hovered = False
        self.hover_time = 0.0
        self.dragging = False


class MenuSystem:
    def __init__(
        self,
        scaling_manager,
        lang_manager,
        game_id: str,
        save_manager=None,
    ) -> None:
        self.logger = get_logger(__name__)
        self.scaling_manager = scaling_manager
        self.lang = lang_manager
        self.game_id = game_id
        self.save_manager = save_manager

        self.state = "main"
        self.current_res = "1280x720"
        self.is_fullscreen = False
        self.music_volume = 1.0
        self.sfx_volume = 1.0

        self.buttons: list[MenuButton] = []
        self.sliders: list[MenuSlider] = []
        self.selected_level: str | None = None
        
        # Logica Carosello
        self.scroll_x = 0.0
        self.target_scroll_x = 0.0
        self.max_scroll_x = 0.0
        
        self.scroll_y = 0.0
        self.target_scroll_y = 0.0
        self.max_scroll_y = 0.0

        # Caricamento tema dal gioco
        self.theme: MenuTheme = load_theme_for_game(game_id)

        self.build_buttons()

    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # Layout helper centralizzato per bottoni standard
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def _std_btn(
        self,
        text: str,
        action: str,
        idx: int,
        total: int,
        override_y: float = None,
        override_w: float = None,
        override_h: float = None,
        image: pygame.Surface = None,
    ) -> MenuButton:
        """Crea un bottone standard usando il layout del tema, forzando carosello orizzontale."""
        bw, bh = self.theme.btn_size()
        if override_w: bw = override_w
        if override_h: bh = override_h
        
        y_start = self.theme.btn_y_start()
        
        if self.theme.is_icons_only() and not override_w:
            size = self.theme.icon_btn_size()
            bw = bh = size
        
        # Layout Carosello Orizzontale (Centrato) con Spacing Costante
        gap = 60
        spacing = bw + gap
        total_width = (total - 1) * spacing + bw
        
        margin = 100
        if total_width < (1280 - margin * 2):
            start_x = (1280 - total_width) / 2
        else:
            start_x = margin
            
        rx = start_x + idx * spacing
        y = y_start if y_start > 100 else (720 - bh) / 2
        
        btn = MenuButton(text, action, rx, y, bw, bh, image=image)
        # Se abbiamo un'anteprima immagine (scene/level), evitiamo l'icona sovrapposta
        if not image:
            btn.icon_surf = self.theme.get_icon(action)
        return btn

    def _quit_btn(self) -> MenuButton:
        """Crea il pulsante di uscita speciale, piccolo e nell'angolo in basso a destra."""
        sm = self.scaling_manager
        # Dimensioni ridotte per l'angolo (100x100 virtuali)
        bw, bh = 100, 100
        margin = 40
        
        rx = 1280 - bw - margin
        ry = 720 - bh - margin
        
        lbl = self.lang.get("btn_quit", "QUIT")
        btn = MenuButton(lbl, "quit", rx, ry, bw, bh)
        btn.icon_surf = self.theme.get_icon("quit")
        return btn

    def _back_btn(self, target_state: str) -> MenuButton:
        """Crea un pulsante BACK professionale, ben visibile e con tooltip dedicato."""
        size = 64 if self.theme.is_icons_only() else 48
        # Riposizionato a 60, 60 per evitare crop su schermi con bordi arrotondati
        btn = MenuButton("", f"goto_{target_state}", 60, 60, size, size)
        btn.tooltip_text = self.lang.get("btn_back", "Indietro")
        
        icon = self.theme.get_icon("goto_main") # Usa freccia standard
        if icon:
            btn.icon_surf = icon # Punta giÃ  a sinistra nel file sorgente
        return btn

    def change_state(self, new_state: str, **kwargs) -> None:
        """Cambia lo stato del menu e rigenera i componenti (bottoni/slider)."""
        self.state = new_state
        has_save = kwargs.get("has_save", False)
        extra_data = kwargs.get("extra_data")

        # Reset scroll quando si cambia pagina (carosello)
        self.target_scroll_x = 0.0
        self.target_scroll_y = 0.0

        if new_state == "scenes" and extra_data:
            self.selected_level = extra_data

        self.build_buttons(has_save=has_save)
        self.logger.info(f"MenuState -> {self.state} (extra: {extra_data})")

    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # Build buttons
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def build_buttons(self, has_save: bool = False) -> None:
        """Ricalcola bottoni e slider in base allo stato corrente del menu."""
        self.buttons.clear()
        self.sliders.clear()

        if self.state == "main":
            if has_save:
                labels_actions = [
                    (self.lang.get("btn_continue", "Continua"), "goto_levels"),
                    (self.lang.get("btn_new_game", "Pulisci File"), "confirm_new"),
                    (self.lang.get("btn_settings"), "goto_settings"),
                    (self.lang.get("btn_quit"), "quit"),
                ]
            else:
                labels_actions = [
                    (self.lang.get("btn_play"), "goto_levels"),
                    (self.lang.get("btn_settings"), "goto_settings"),
                    (self.lang.get("btn_quit"), "quit"),
                ]
            
            # --- Raffinamento UX: Separiamo il pulsante QUIT dal carosello centrale ---
            main_actions = [(l, a) for l, a in labels_actions if a != "quit"]
            total = len(main_actions)
            for i, (lbl, act) in enumerate(main_actions):
                self.buttons.append(self._std_btn(lbl, act, i, total))
            
            # Aggiunta del pulsante QUIT in posizione dedicata (basso a destra)
            self.buttons.append(self._quit_btn())

        elif self.state == "confirm_new":
            bw, bh = self.theme.btn_size()
            cx = self.theme.btn_center_x()
            rx = cx - bw / 2
            warn_w = bw + 120
            warn_rx = cx - warn_w / 2
            self.buttons = [
                MenuButton(
                    self.lang.get("msg_confirm_new_game", "ATTENZIONE: Perderai i progressi!"),
                    "none", warn_rx, 250, warn_w, 40,
                ),
                MenuButton(
                    self.lang.get("btn_confirm_new_game", "SÃ¬, Inizia Nuovo Gioco"),
                    "do_new_game", warn_rx, 310, warn_w, bh,
                ),
            ]
            self.buttons.append(self._back_btn("main"))

        elif self.state == "levels":
            levels_path = get_resource_path("games", self.game_id, "levels")
            
            unlocked_lvls: list[str] = []
            if self.save_manager:
                unlocked_lvls = self.save_manager.get_progress("unlocked_levels", [])

            if levels_path.exists():
                lvl_dirs = sorted([d for d in levels_path.iterdir() if d.is_dir()])
                
                # Layout Premium per Livelli: Card ampie e leggibili
                bw, bh = 640, 160
                total = len(lvl_dirs)
                focus_idx = 0
                
                for i, ld in enumerate(lvl_dirs):
                    level_id = ld.name
                    level_name = level_id
                    
                    cfg_p = ld / "level_config.json"
                    preview: pygame.Surface | None = None
                    
                    if cfg_p.exists():
                        try:
                            with open(cfg_p, "r", encoding="utf-8") as f:
                                cfg = json.load(f)
                            nk = cfg.get("name_key")
                            if nk: level_name = self.lang.get(nk, level_id)
                            
                            # Tenta di caricare anteprima dalla prima scena per la Level Card
                            scenes = cfg.get("scenes", [])
                            if scenes:
                                first_scene_id = scenes[0].get("id")
                                bg_p = ld / first_scene_id / "background.png"
                                if bg_p.exists():
                                    raw = pygame.image.load(str(bg_p))
                                    preview = pygame.transform.smoothscale(raw, (bw, bh))
                        except Exception: pass

                    is_unlocked = level_id in unlocked_lvls
                    if is_unlocked: focus_idx = i
                    
                    display_text = level_name if is_unlocked else f"- {level_name.upper()} - (LOCKED)"
                    btn_action = f"goto_scenes:{level_id}" if is_unlocked else "none"
                    
                    btn = self._std_btn(display_text, btn_action, i, total, override_w=bw, override_h=bh, image=preview)
                    self.buttons.append(btn)
                
                # Salva per focus finale
                self._last_focus_data = (focus_idx, total, bw, 60)

            self.buttons.append(self._back_btn("main"))

        elif self.state == "scenes":
            if self.selected_level:
                lvl_path = get_resource_path(
                    "games", self.game_id, "levels", self.selected_level
                )
                cfg_p = lvl_path / "level_config.json"
                if cfg_p.exists():
                    try:
                        with open(cfg_p, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        scenes = cfg.get("scenes", [])
                        
                        y_start = 140
                        thumb_w = self.theme.layout("scene_thumb_w", 320)
                        thumb_h = self.theme.layout("scene_thumb_h", 180)
                        
                        # In modalità icons_only usiamo carosello orizzontale uniforme
                        if self.theme.is_icons_only():
                            focus_idx = 0
                            total_s = len(scenes)
                            for i, s in enumerate(scenes):
                                scene_id = s.get("id")
                                is_unlocked = True
                                if self.save_manager:
                                    is_unlocked = self.save_manager.is_scene_unlocked(self.selected_level, i)
                                if is_unlocked: focus_idx = i
                                
                                preview = self._load_scene_preview(lvl_path, scene_id, thumb_w, thumb_h, is_unlocked)
                                name = self.lang.get(f"{scene_id}_name", scene_id)
                                btn_action = f"play_scene:{self.selected_level}:{scene_id}" if is_unlocked else "none"
                                
                                self.buttons.append(self._std_btn(name, btn_action, i, total_s, 
                                                                 override_w=thumb_w, override_h=thumb_h, image=preview))
                            
                            self._last_focus_data = (focus_idx, total_s, thumb_w, 60)
                        else:
                            # Grid standard per temi non-icons
                            cols = self.theme.layout("scene_grid_cols", 3)
                            # ... (rest of grid logic remains same)
                    except Exception as e:
                        self.logger.error(
                            "MenuSystem: Errore caricamento scene per %s: %s", self.selected_level, e
                        )

            self.buttons.append(self._back_btn("levels"))

        elif self.state == "settings":
            self.buttons.append(self._back_btn("main"))

            # Dati per la lista unificata (Label, Action, Value/Type)
            # Questo garantisce che tutti i temi abbiano un menu impostazioni coerente e scrollabile
            items = [
                ("label_music_volume", "set_music_volume", "slider_music"),
                ("label_sfx_volume", "set_sfx_volume", "slider_sfx"),
                ("label_language", "toggle_lang", self.lang.current_language.upper()),
                ("label_resolution", "toggle_res", self.current_res),
                ("label_fullscreen", "toggle_fs", "ON" if self.is_fullscreen else "OFF"),
            ]
            
            y_start = 80 # Ulteriormente alzato per bilanciamento perfetto
            y_step = 100
            
            # Larghezza riga unificata per centraggio perfetto
            row_w = 600
            start_x = (1280 - row_w) / 2
            icon_col_w = 120 # Spazio dedicato all'icona a sinistra
            
            for i, (lang_key, act, val) in enumerate(items):
                lbl = self.lang.get(lang_key, lang_key)
                rx, ry = start_x, y_start + i * y_step
                
                icon_surf = self.theme.get_icon(act)
                
                if "slider" in val:
                    s_val = self.music_volume if "music" in val else self.sfx_volume
                    # Lo slider occupa la parte destra della riga (row_w - icon_col_w)
                    s_w = row_w - icon_col_w
                    s_x = rx + icon_col_w
                    self.sliders.append(MenuSlider(lbl, act, s_x, ry + 30, s_w, 20, s_val))
                else:
                    # Riga pulsante per valori testuali
                    btn = MenuButton(val, act, rx, ry, row_w, 80)
                    btn.icon_surf = icon_surf
                    btn.tooltip_text = f"{lbl}: {val}"
                    self.buttons.append(btn)

        elif self.state == "pause":
            labels_actions = [
                (self.lang.get("btn_resume", "Riprendi"), "resume_game"),
                (self.lang.get("btn_settings", "Impostazioni"), "goto_settings"),
                (self.lang.get("btn_quit_to_main", "Menu"), "quit_to_main"),
            ]
            total = len(labels_actions)
            for i, (lbl, act) in enumerate(labels_actions):
                self.buttons.append(self._std_btn(lbl, act, i, total))

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ        self.build_buttons(has_save=has_save)
        
        # Calcolo max_scroll_x/y per il carosello
        if self.buttons or self.sliders:
            # Filtriamo i bottoni fissi (Back) dal calcolo
            scrollable_b = [b for b in self.buttons if b.ref_rect.x >= 100 or b.ref_rect.y >= 120]
            scrollable_s = [s for s in self.sliders]
            
            if self.state == "settings":
                # Scroll Verticale
                all_items = scrollable_b + scrollable_s
                if all_items:
                    last_y = max(i.ref_rect.bottom for i in all_items)
                    self.max_scroll_y = max(0, last_y + 100 - 720)
            else:
                # Scroll Orizzontale
                if scrollable_b:
                    last_x = max(b.ref_rect.right for b in scrollable_b)
                    self.max_scroll_x = max(0, last_x + 100 - 1280)

            # --- AUTO-FOCUS SU ULTIMO SBLOCCATO ---
            if hasattr(self, "_last_focus_data"):
                idx, tot, bw, gap = self._last_focus_data
                self._focus_on_index(idx, tot, bw, gap)
                delattr(self, "_last_focus_data")

    
    def _draw_magnifier(self, screen: pygame.Surface) -> None:
        """Effetto Lente d'Ingrandimento professionale per temi Mystery/Investigativi."""
        try:
            import pygame
            mx, my = self.mouse_pos
            sm = self.scaling_manager
            radius = self.theme.magnifier_radius(sm)
            zoom = self.theme.magnifier_zoom()
            
            # 1. Cattura l'area sotto il mouse (gestendo i bordi schermo)
            cap_side = int(radius * 2 / zoom)
            cap_rect = pygame.Rect(0, 0, cap_side, cap_side)
            cap_rect.center = (mx, my)
            
            # Creiamo una superficie di cattura completa per mantenere l'allineamento
            full_cap = pygame.Surface((cap_side, cap_side))
            full_cap.fill((20, 20, 25)) # Sfondo neutro per aree fuori schermo
            
            scr_rect = screen.get_rect()
            visible_rect = cap_rect.clip(scr_rect)
            
            if visible_rect.width > 0 and visible_rect.height > 0:
                sub = screen.subsurface(visible_rect).copy()
                # Blit della porzione visibile nella posizione relativa corretta
                rel_x = visible_rect.x - cap_rect.x
                rel_y = visible_rect.y - cap_rect.y
                full_cap.blit(sub, (rel_x, rel_y))
            
            # 2. Zoom con Smoothscale (dimensione finale fissa pari alla lente)
            zoomed = pygame.transform.smoothscale(full_cap, (radius * 2, radius * 2))
            
            # 3. Creazione Maschera Circolare
            lens_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(lens_surf, (255, 255, 255, 255), (radius, radius), radius)
            
            # Ritaglio circolare tramite BLEND_RGBA_MULT
            content_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            content_surf.blit(zoomed, zoomed.get_rect(center=(radius, radius)))
            content_surf.blit(lens_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            # 4. Render finale e Cornice "Investigativa"
            screen.blit(content_surf, (mx - radius, my - radius))
            
            # Cornice in ottone/ottica con riflesso
            pygame.draw.circle(screen, (180, 160, 120), (mx, my), radius, width=sm.scale_value(4))
            pygame.draw.circle(screen, (40, 30, 20), (mx, my), radius + sm.scale_value(1), width=sm.scale_value(1))
            
            # Riflesso sulla lente (arco trasparente)
            pygame.draw.arc(screen, (255, 255, 255, 100), (mx-radius+10, my-radius+10, radius*2-20, radius*2-20), 0.5, 2.1, 3)
        except Exception:
            pass

    def _get_hitbox(self, item, is_slider: bool = False) -> pygame.Rect:
        """Calcola la hitbox reale di un elemento, considerando scroll, zoom ed ergonomia."""
        # 1. Determina se Ã¨ fisso (es. tasto Back)
        is_fixed = (item.ref_rect.x < 100 and item.ref_rect.y < 120)
        
        # 2. Applica scroll
        rect = item.ref_rect.copy()
        if not is_fixed:
            rect.x -= self.scroll_x
            rect.y -= self.scroll_y
            
        # 3. Coerenza con Zoom Carosello (Solo per stati carosello e bottoni non fissi)
        if not is_slider and self.state in ("main", "levels", "scenes", "pause") and not is_fixed:
            # Calcolo basato sul centro dello schermo (1280/2 = 640)
            dist_center = abs(rect.centerx - 640)
            zoom = 1.0 + max(0, (1.0 - dist_center / 640)) * 0.25
            if zoom > 1.0:
                orig_center = rect.center
                rect.width = int(rect.width * zoom)
                rect.height = int(rect.height * zoom)
                rect.center = orig_center

        # 4. Inflazione Ergonomica (Dimensioni dinamiche)
        if is_slider:
            # Slider molto piÃ¹ facili da cliccare verticalmente (hitbox di 70px)
            return rect.inflate(0, 50)
        else:
            # Per bottoni piccoli (icone), inflazione generosa. 
            # Per righe larghe (Settings), inflazione minima per evitare sovrapposizioni.
            inf_x = rect.w * 0.05 if rect.w > 300 else rect.w * 0.2
            inf_y = rect.h * 0.1 if rect.h > 60 else rect.h * 0.3
            return rect.inflate(inf_x, inf_y)

    def update(self, dt: float, mouse_x: int, mouse_y: int) -> None:
        """Aggiorna hover, slider e animazioni tema."""
        self.mouse_pos = (mouse_x, mouse_y)
        self.theme.update(dt)
        tick = self.theme._tick

        # Update Scroll (Carosello fluido)
        self.scroll_x += (self.target_scroll_x - self.scroll_x) * dt * 10.0
        self.scroll_y += (self.target_scroll_y - self.scroll_y) * dt * 10.0

        rx, ry = self.scaling_manager.screen_to_ref(mouse_x, mouse_y)
        
        # VelocitÃ  di transizione (secondi)
        trans_speed = 8.0 
        
        for i, b in enumerate(self.buttons):
            hitbox = self._get_hitbox(b)
            b.hovered = hitbox.collidepoint(rx, ry)
            
            # 1. Hover LERP
            if b.hovered:
                b.hover_time = min(1.0, b.hover_time + dt * trans_speed)
            else:
                b.hover_time = max(0.0, b.hover_time - dt * trans_speed)
            
            # 2. Ripple Update
            if b.ripple_time > 0:
                b.ripple_time = max(0.0, b.ripple_time - dt * 2.0)
            
            # 3. Floating Animation (Disattivata come richiesto)
            b.float_offset = 0.0
            
            # 4. Tilt & Magnetic Effect (Disattivati per stabilitÃ Ã )
            if not hasattr(b, "angle"): b.angle = 0.0
            b.angle = 0.0
            if not hasattr(b, "mag_offset"): b.mag_offset = [0.0, 0.0]
            b.mag_offset = [0.0, 0.0]

        for s in self.sliders:
            hitbox = self._get_hitbox(s, is_slider=True)
            s.hovered = hitbox.collidepoint(rx, ry)
            
            if s.hovered:
                s.hover_time = min(1.0, s.hover_time + dt * trans_speed)
            else:
                s.hover_time = max(0.0, s.hover_time - dt * trans_speed)

            if s.dragging:
                # Applichiamo lo scroll Y alla coordinata mouse relativa
                rel_x = max(0, min(rx - s.ref_rect.x, s.ref_rect.w))
                s.value = rel_x / s.ref_rect.w
                if s.action == "set_music_volume":
                    self.music_volume = s.value
                elif s.action == "set_sfx_volume":
                    self.sfx_volume = s.value
            if b.hovered:
                b.hover_time = min(1.0, b.hover_time + dt * trans_speed)
            else:
                b.hover_time = max(0.0, b.hover_time - dt * trans_speed)
            
            # 2. Ripple Update
            if b.ripple_time > 0:
                b.ripple_time = max(0.0, b.ripple_time - dt * 2.0)
            
            # 3. Floating Animation (Disattivata come richiesto)
            b.float_offset = 0.0
            
            # 4. Tilt & Magnetic Effect (Tilt disattivato come richiesto)
            target_angle = 0.0
            if not hasattr(b, "angle"): b.angle = 0.0
            b.angle += (target_angle - b.angle) * dt * 10.0
            
            if not hasattr(b, "mag_offset"): b.mag_offset = [0.0, 0.0]
            # Magnetic Offset disattivato per stabilitÃ  totale
            b.mag_offset[0] = 0.0
            b.mag_offset[1] = 0.0

        for s in self.sliders:
            hitbox = self._get_hitbox(s, is_slider=True)
            s.hovered = hitbox.collidepoint(rx, ry)
            
            if s.hovered:
                s.hover_time = min(1.0, s.hover_time + dt * trans_speed)
            else:
                s.hover_time = max(0.0, s.hover_time - dt * trans_speed)

            if s.dragging:
                # Applichiamo lo scroll Y alla coordinata mouse relativa
                rel_x = max(0, min(rx - s.ref_rect.x, s.ref_rect.w))
                s.value = rel_x / s.ref_rect.w
                if s.action == "set_music_volume":
                    self.music_volume = s.value
                elif s.action == "set_sfx_volume":
                    self.sfx_volume = s.value

    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # Draw
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def draw(self, screen: pygame.Surface) -> None:
        """Dipingimento fisico di bottoni e slider usando il tema attivo."""
        sm = self.scaling_manager
        theme = self.theme

        
        sw, sh = screen.get_size()
        
        # Lista differita per i tooltips (per gestire correttamente lo Z-index)
        tooltip_queue = []

        # ââ 1. Effetto Torcia (Flashlight)
        if theme.has_flashlight():
            dark_ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
            dark_ov.fill((0, 0, 0, 250))
            f_pos = theme.flashlight_pos(sw, sh)
            f_radius = sm.scale_value(theme.fx("flashlight_radius", 280))
            for r in range(f_radius, 0, -2):
                alpha = int(250 * (r / f_radius)**1.2)
                pygame.draw.circle(dark_ov, (0, 0, 0, alpha), f_pos, r)
            screen.blit(dark_ov, (0, 0))

        # ── 1.5 Titolo dello Stato
        self._draw_state_title(screen)

        # ââ 2. Render Bottoni (Con supporto Carosello)
        for b in self.buttons:
            rect = sm.scale_rect(b.ref_rect.x, b.ref_rect.y, b.ref_rect.w, b.ref_rect.h)
            
            # Se il bottone non Ã¨ fisso (es. Back), applichiamo lo scroll
            is_fixed = (b.ref_rect.x < 100 and b.ref_rect.y < 120)
            if not is_fixed:
                rect.x -= int(sm.scale_value(self.scroll_x))
                rect.y -= int(sm.scale_value(self.scroll_y))

            # Ottimizzazione Culling: non disegnare se fuori schermo
            if rect.right < 0 or rect.left > sw: continue

            # Effetto Carosello Premium: Zoom al centro (Solo per stati carosello, non Settings)
            is_carousel = self.state in ("main", "levels", "scenes", "pause")
            dist_center = abs(rect.centerx - sw / 2)
            max_dist = sw / 2
            zoom_factor = 1.0
            if is_carousel:
                zoom_factor = 1.0 + max(0, (1.0 - dist_center / max_dist)) * 0.25 # Fino a 1.25x al centro
            
            is_locked = (b.action == "none")
            draw_rect = rect.copy()
            
            # Applichiamo lo zoom alla dimensione finale del rettangolo di disegno
            orig_center = draw_rect.center
            draw_rect.width = int(draw_rect.width * zoom_factor)
            draw_rect.height = int(draw_rect.height * zoom_factor)
            draw_rect.center = orig_center

            # Animazioni: Floating + Magnetic
            draw_rect.y += int(sm.scale_value(b.float_offset))
            if hasattr(b, "mag_offset"):
                draw_rect.x += int(sm.scale_value(b.mag_offset[0]))
                draw_rect.y += int(sm.scale_value(b.mag_offset[1]))

            if b.image:
                # Bottone Scena/Anteprima
                img_scaled = pygame.transform.smoothscale(b.image, (draw_rect.w, draw_rect.h))
                screen.blit(img_scaled, draw_rect)
                ov_col = theme.color("scene_overlay_hover") if b.hovered else theme.color("scene_overlay_normal")
                ov = pygame.Surface((draw_rect.w, draw_rect.h), pygame.SRCALPHA)
                ov.fill(ov_col[:4] if len(ov_col) == 4 else (*ov_col, 120))
                screen.blit(ov, draw_rect)
                theme.draw_sepia_overlay(screen, draw_rect)
                bc = theme.color3("scene_border_hover") if b.hovered else theme.color3("scene_border_normal")
                pygame.draw.rect(screen, bc, draw_rect, width=2, border_radius=theme.border_radius())
                
                if is_locked:
                    lock_font = theme.get_font(theme.font_size_lock(), sm)
                    lock_surf = lock_font.render("[LOCKED]", True, theme.color3("lock_text"))
                    screen.blit(lock_surf, lock_surf.get_rect(center=draw_rect.center))
                
                if b.icon_surf:
                    ico_scaled = self._scale_icon(b.icon_surf, draw_rect, sm)
                    screen.blit(ico_scaled, ico_scaled.get_rect(center=draw_rect.center))
                else:
                    font = theme.get_font(theme.font_size_scene(), sm)
                    theme.draw_text(screen, b.text, font, draw_rect, b.hovered, is_locked, anchor="midbottom", hover_t=b.hover_time)
            else:
                # Bottone Standard/Icona
                theme.draw_btn_bg(screen, draw_rect, b.hovered, is_locked, hover_t=b.hover_time)
                
                # Ripple
                if b.ripple_pos and b.ripple_time > 0:
                    r_rad = int((1.0 - b.ripple_time) * draw_rect.w * 0.8)
                    r_surf = pygame.Surface((draw_rect.w, draw_rect.h), pygame.SRCALPHA)
                    pygame.draw.circle(r_surf, (255, 255, 255, int(b.ripple_time * 100)), b.ripple_pos, r_rad)
                    screen.blit(r_surf, draw_rect, special_flags=pygame.BLEND_RGBA_ADD)

                if b.icon_surf:
                    if self.state == "settings":
                        # Layout Unificato Premium: Icona a sinistra (colonna dedicata), Valore a destra
                        ico_scaled = self._scale_icon(b.icon_surf, draw_rect, sm)
                        # Allineamento dell'icona all'interno della prima colonna (120px)
                        screen.blit(ico_scaled, ico_scaled.get_rect(midleft=(draw_rect.left + sm.scale_value(20), draw_rect.centery)))
                        
                        # Valore testuale allineato a destra del blocco riga
                        # Valore testuale allineato a destra con "Pillola" ad alto contrasto (Solo se c'Ã¨ testo)
                        if b.text:
                            val_font = theme.get_font(theme.font_size_label() + 10, sm)
                            val_surf = val_font.render(b.text, True, theme.color3("text_normal"))
                            
                            # Calcolo centro della colonna destra (area valori)
                            right_col_x = draw_rect.left + sm.scale_value(120) 
                            right_col_w = draw_rect.width - sm.scale_value(120)
                            center_val_x = right_col_x + right_col_w / 2
                            
                            # Rettangolo del testo centrato nell'area destra
                            v_rect = val_surf.get_rect(center=(center_val_x, draw_rect.centery))
                            
                            # Background "Pill" - Meno stondato (radius ridotto)
                            pill_rect = v_rect.inflate(sm.scale_value(40), sm.scale_value(16))
                            # Ombra pillola
                            pygame.draw.rect(screen, (0, 0, 0, 150), pill_rect.move(2, 2), border_radius=sm.scale_value(8))
                            # Fondo pillola
                            pygame.draw.rect(screen, (15, 18, 25, 200), pill_rect, border_radius=sm.scale_value(8))
                            # Bordo pillola (accento del tema)
                            accent_col = theme.color3("btn_border_hover")
                            pygame.draw.rect(screen, (*accent_col, 120), pill_rect, width=2, border_radius=sm.scale_value(8))
                            
                            # Blit finale del testo (centrato perfettamente nella pillola)
                            screen.blit(val_surf, v_rect)
                    else:
                        ico_scaled = self._scale_icon(b.icon_surf, draw_rect, sm)
                        
                        if theme.is_icons_only():
                            # Effetti Professionali per Pure Icons
                            if b.hover_time > 0:
                                # Breathing Glow
                                gc = theme.color3("btn_glow_color") if "btn_glow_color" in theme._colors else (255, 235, 180)
                                breath = (math.sin(theme._tick * 5.0) + 1.0) * 0.5
                                alpha = int((90 + 50 * breath) * b.hover_time)
                                g_size = int(draw_rect.w * (1.1 + 0.1 * breath))
                                glow_surf = pygame.Surface((g_size, g_size), pygame.SRCALPHA)
                                
                                if theme.fx("glow_type") == "square":
                                    # Glow quadrato piÃ¹ compatto
                                    pygame.draw.rect(glow_surf, (*gc, alpha), (0, 0, g_size, g_size), 
                                                     border_radius=theme.border_radius() + 4)
                                else:
                                    # Glow tondo standard
                                    pygame.draw.circle(glow_surf, (*gc, alpha), (g_size // 2, g_size // 2), g_size // 2)
                                
                                screen.blit(glow_surf, glow_surf.get_rect(center=draw_rect.center), special_flags=pygame.BLEND_RGBA_ADD)
                            
                            # Scale + Rotate (Tilt) - Disabilitati in settings per stabilitÃ 
                            s = 1.0
                            if self.state != "settings":
                                s = 1.0 + (theme.pulse_scale() - 1.0) * b.hover_time
                                
                            if s != 1.0:
                                ico_scaled = pygame.transform.smoothscale(ico_scaled, (int(ico_scaled.get_width()*s), int(ico_scaled.get_height()*s)))
                            if hasattr(b, "angle") and abs(b.angle) > 0.1 and self.state != "settings":
                                ico_scaled = pygame.transform.rotozoom(ico_scaled, b.angle, 1.0)
                            
                            # Glossy Reflection (Premium Version: Trasparenza e Dettagli)
                            # Ciclo organico con pausa (4s totali, 1.2s di movimento)
                            total_dur = 4.0
                            sweep_dur = 1.2
                            t_in_cycle = theme._tick % total_dur
                            
                            refl_t = -1.0
                            if t_in_cycle < sweep_dur:
                                refl_t = t_in_cycle / sweep_dur
                                # Smoothstep per un'animazione fluida senza scatti
                                refl_t = refl_t * refl_t * (3 - 2 * refl_t)
                            
                            # Attivazione: sweep ciclico o hover costante
                            if b.hover_time > 0.01 or refl_t >= 0.0:
                                iw, ih = ico_scaled.get_size()
                                # Tecnica Robusta: Superficie nera + BLEND_ADD per un effetto luce reale
                                # Invece di una superficie con alpha, usiamo il nero (0,0,0) come base neutra per l'ADD
                                refl_surf = pygame.Surface((iw, ih))
                                refl_surf.fill((0, 0, 0))
                                
                                if refl_t < 0:
                                    cur_t = 0.5
                                    alpha_mult = 0.2 * b.hover_time
                                else:
                                    cur_t = refl_t
                                    alpha_mult = 0.4 + (b.hover_time * 0.4)
                                
                                sweep_x = int((cur_t * 3.0 - 1.0) * iw)
                                
                                # Forza della luce (più alto = più brillante, qui manteniamo un valore elegante)
                                light_val = int(80 * alpha_mult)
                                col = (light_val, light_val, light_val)
                                
                                if light_val > 0:
                                    points = [
                                        (sweep_x, 0), 
                                        (sweep_x + 12, 0), 
                                        (sweep_x + 12 - iw // 3, ih), 
                                        (sweep_x - iw // 3, ih)
                                    ]
                                    # Disegniamo sulla superficie nera: il bianco diventerà luce pura in ADD
                                    pygame.draw.polygon(refl_surf, col, points)
                                    
                                    # Halo (sfumatura laterale)
                                    halo_val = int(light_val * 0.4)
                                    pygame.draw.polygon(refl_surf, (halo_val, halo_val, halo_val), [
                                        (sweep_x - 15, 0), (sweep_x + 27, 0), 
                                        (sweep_x + 27 - iw // 3, ih), (sweep_x - 15 - iw // 3, ih)
                                    ])
                                
                                # Blit con BLEND_ADD: somma solo i canali RGB, preservando l'icona sottostante
                                ico_scaled.blit(refl_surf, (0, 0), special_flags=pygame.BLEND_ADD)

                        screen.blit(ico_scaled, ico_scaled.get_rect(center=draw_rect.center))
                    
                    # Tooltip Pop-in: Differito alla fine per Z-index perfetto
                    tt_text = getattr(b, "tooltip_text", b.text)
                    show_tt = False
                    if b.hovered:
                        if self.state == "settings":
                            # Nelle impostazioni, compare solo se il mouse Ã¨ sopra l'area icona (sinistra)
                            icon_area_w = sm.scale_value(120)
                            if self.mouse_pos[0] < draw_rect.left + icon_area_w:
                                show_tt = True
                        else:
                            # Nei menu icone, compare su tutto il bottone dopo un breve delay o istantaneo se icons_only
                            if (theme.is_icons_only() or b.hover_time > 0.6) and b.hover_time > 0.1:
                                show_tt = True
                    
                    if show_tt:
                        tooltip_queue.append((tt_text, draw_rect, b.hover_time))
                else:
                    font = theme.get_auto_font(b.text, theme.font_size_btn(), b.ref_rect.w, sm)
                    theme.draw_text(screen, b.text, font, draw_rect, b.hovered, is_locked, anchor="center", hover_t=b.hover_time)

        # ââ 3. Render Slider Professionali (Senza pannello/box grigio come richiesto)
        if self.state == "settings" and self.theme.fx("settings_panel", False):
            # Pannello dinamico (disabilitato di default per Malonno)
            n_items = len(self.buttons) - 1
            panel_h = max(420, 80 + n_items * theme.btn_y_step())
            panel_r = sm.scale_rect(150, 150, 980, panel_h)
            
            _rect_surf = pygame.Surface((panel_r.w, panel_r.h), pygame.SRCALPHA)
            _rect_surf.fill((0, 0, 0, 140))
            screen.blit(_rect_surf, panel_r)
            
            accent = theme.color3("accent") if "accent" in theme._colors else theme.color3("btn_border_normal")
            pygame.draw.rect(screen, accent, panel_r, width=2, border_radius=15)

        for s in self.sliders:
            rect = sm.scale_rect(s.ref_rect.x, s.ref_rect.y, s.ref_rect.w, s.ref_rect.h)
            rect.y -= int(sm.scale_value(self.scroll_y))

            # Ottimizzazione Culling
            if rect.bottom < 0 or rect.top > sh: continue

            # Icona a sinistra dello slider (Perfettamente allineata alla colonna icone)
            ico_surf = theme.get_icon(s.action)
            if ico_surf:
                ih = 80 if theme.is_icons_only() else int(rect.h * 1.5)
                ico_scaled = pygame.transform.smoothscale(ico_surf, (ih, ih))
                # Allineamento dell'icona all'interno della prima colonna (offset 100px rispetto allo slider)
                screen.blit(ico_scaled, ico_scaled.get_rect(midleft=(rect.left - sm.scale_value(100), rect.centery)))

            # Track
            pygame.draw.rect(screen, theme.color3("slider_bg") if "slider_bg" in theme._colors else (40, 40, 40), rect, border_radius=rect.h // 2)
            pygame.draw.rect(screen, (*theme.color3("btn_border_normal")[:3], 100), rect, width=1, border_radius=rect.h // 2)

            # Fill + Knob Professionale
            if s.value > 0:
                prog_w = int(rect.w * s.value)
                prog_rect = pygame.Rect(rect.x, rect.y, prog_w, rect.h)
                fill_col = theme.color3("slider_fill")
                pygame.draw.rect(screen, fill_col, prog_rect, border_radius=rect.h // 2)
                
                # Knob Professionale (Glow / White Circle)
                knob_x = rect.x + prog_w
                pygame.draw.circle(screen, (255, 255, 255), (knob_x, rect.centery), rect.h // 1.1)
                pygame.draw.circle(screen, fill_col, (knob_x, rect.centery), rect.h // 1.6)

            # Handle dinamico
            handle_x = rect.x + int(rect.w * s.value)
            h_rad = int(rect.h * (0.8 + 0.2 * s.hover_time))
            pygame.draw.circle(screen, theme.color3("slider_handle"), (handle_x, rect.centery), h_rad)
            pygame.draw.circle(screen, (255, 255, 255, 180), (handle_x, rect.centery), h_rad, width=2)
            
            if s.hovered:
                # Recupero label localizzato per il tooltip (senza sporcare lo schermo)
                lang_key = f"ui_{s.action.replace('set_', '').replace('_volume', '')}"
                # Supporto per tooltip descrittivi localizzati (tip_music_volume, tip_sfx_volume)
                tip_key = "tip_" + s.action.replace("set_", "")
                tip_text = self.lang(tip_key, None)
                
                if tip_text:
                    full_text = f"{tip_text}: {int(s.value * 100)}%"
                else:
                    label_text = self.lang(lang_key, s.label)
                    full_text = f"{label_text}: {int(s.value * 100)}%"
                
                tooltip_queue.append((full_text, rect, 1.0))

        
        # --- EFFETTO LENTE D'INGRANDIMENTO (Mystery HUD) ---
        # Posizionata qui per ingrandire anche i bottoni e le voci di menu
        if theme.has_magnifier():
            self._draw_magnifier(screen)
        # ── 4. Render Tooltips differiti (Massima prioritÃ  Z-Index)
        for tt_text, tt_rect, tt_time in tooltip_queue:
            self._draw_tooltip(screen, tt_text, tt_rect, sm, tt_time)

    def _focus_on_index(self, index: int, total: int, bw: float, gap: float) -> None:
        """Calcola e imposta lo scroll target per centrare un elemento specifico."""
        spacing = bw + gap
        total_width = (total - 1) * spacing + bw
        
        margin = 100
        if total_width < (1280 - margin * 2):
            start_x = (1280 - total_width) / 2
        else:
            start_x = margin
            
        item_rx = start_x + index * spacing
        self.target_scroll_x = max(0, min(self.max_scroll_x, item_rx - 640 + (bw / 2)))
        if self.scroll_x == 0:
            self.scroll_x = self.target_scroll_x

    def _load_scene_preview(self, lvl_path, scene_id, w, h, is_unlocked) -> pygame.Surface | None:
        try:
            scene_dir = lvl_path / scene_id
            s_cfg_p = scene_dir / "scene.json"
            if s_cfg_p.exists():
                with open(s_cfg_p, "r", encoding="utf-8") as sf:
                    s_cfg = json.load(sf)
                bg_file = s_cfg.get("background", "background.png")
                bg_full_path = scene_dir / bg_file
                if bg_full_path.exists():
                    raw = pygame.image.load(str(bg_full_path))
                    preview = pygame.transform.smoothscale(raw, (w, h))
                    if not is_unlocked:
                        try: preview = pygame.transform.grayscale(preview)
                        except: pass
                    return preview
        except: pass
        return None

    
    def _focus_on_index(self, index: int, total: int, bw: float, gap: float) -> None:
        """Calcola e imposta lo scroll target per centrare un elemento specifico."""
        spacing = bw + gap
        total_width = (total - 1) * spacing + bw
        margin = 100
        if total_width < (1280 - margin * 2):
            start_x = (1280 - total_width) / 2
        else:
            start_x = margin
        item_rx = start_x + index * spacing
        self.target_scroll_x = max(0, min(self.max_scroll_x, item_rx - 640 + (bw / 2)))
        if self.scroll_x == 0:
            self.scroll_x = self.target_scroll_x

    def _load_scene_preview(self, lvl_path, scene_id, w, h, is_unlocked) -> pygame.Surface | None:
        """Helper per caricare l'anteprima di una scena."""
        try:
            import pygame
            scene_dir = lvl_path / scene_id
            s_cfg_p = scene_dir / "scene.json"
            if s_cfg_p.exists():
                with open(s_cfg_p, "r", encoding="utf-8") as sf:
                    s_cfg = json.load(sf)
                bg_file = s_cfg.get("background", "background.png")
                bg_full_path = scene_dir / bg_file
                if bg_full_path.exists():
                    raw = pygame.image.load(str(bg_full_path))
                    preview = pygame.transform.smoothscale(raw, (w, h))
                    if not is_unlocked:
                        try: preview = pygame.transform.grayscale(preview)
                        except: pass
                    return preview
        except: pass
        return None

    def _draw_state_title(self, screen: pygame.Surface) -> None:
        """Disegna il titolo dello stato corrente (es: 'SELEZIONA LIVELLO') con estetica premium."""
        titles = {
            "levels": self.lang.get("menu_title_levels", "LEVEL SELECTION"),
            "scenes": self.lang.get("menu_title_scenes", "SCENE SELECTION"),
            "settings": self.lang.get("menu_title_settings", "ENGINE SETTINGS"),
            "confirm_new": self.lang.get("menu_title_confirm", "WARNING"),
        }
        title_text = titles.get(self.state)
        if not title_text: return
        
        sm = self.scaling_manager
        theme = self.theme
        
        # Font premium (grande, spaziato, con ombra)
        font_size = theme.layout("title_font_size", 44)
        font = theme.get_font(font_size, sm)
        
        # Render con shadow per massima leggibilità
        color = theme.color3("text_normal")
        title_surf = font.render(title_text.upper(), True, color)
        
        # Posizionamento: In alto al centro con margine
        tx = (screen.get_width() - title_surf.get_width()) // 2
        ty = sm.scale_value(theme.layout("title_y_offset", 110))
        
        # Shadow per leggibilità su sfondi sporchi (horror/mystery)
        shadow_surf = font.render(title_text.upper(), True, (10, 10, 15))
        shadow_surf.set_alpha(180)
        screen.blit(shadow_surf, (tx + 3, ty + 3))
        
        screen.blit(title_surf, (tx, ty))

    def _draw_tooltip(self, screen: pygame.Surface, text: str, rect: pygame.Rect, sm, t: float):
        """Disegna un tooltip professionale che segue il mouse con effetto pop-in elastico."""
        theme = self.theme
        start_threshold = 0.05 if theme.is_icons_only() else 0.5
        if t < start_threshold: return
        
        # Recupero posizione mouse (giÃ  scalata o da scalare?)
        # self.mouse_pos Ã¨ in coordinate schermo reali.
        mx, my = getattr(self, "mouse_pos", (640, 360))
        
        prog = min(1.0, (t - start_threshold) * 6.0)
        x = prog - 1
        elastic = 1 + 2.70158 * (x**3) + 1.70158 * (x**2)
        
        alpha = int(prog * 255)
        font_size = theme.font_size_label() + 4
        font = theme.get_font(font_size, sm)
        txt_surf = font.render(text, True, theme.color3("text_normal"))
        txt_surf.set_alpha(alpha)
        
        tw, th = txt_surf.get_size()
        pad = sm.scale_value(14)
        t_rect = pygame.Rect(0, 0, tw + pad*2, th + pad*2)
        
        # Posizionamento vicino al mouse con offset
        off_x = sm.scale_value(25)
        off_y = sm.scale_value(25)
        
        # Animazione di "salita" o pop-in verso il mouse
        anim_y = sm.scale_value(20 * (1.0 - elastic))
        
        t_rect.x = mx + off_x
        t_rect.y = my + off_y + anim_y
        
        # Prevenzione uscita dai bordi dello schermo
        sw, sh = screen.get_size()
        if t_rect.right > sw - 20: t_rect.right = mx - off_x
        if t_rect.bottom > sh - 20: t_rect.bottom = my - off_y
        
        # Sfondo con Effetto Glassmorfismo e Ombra Morbida
        bg_surf = pygame.Surface((t_rect.w, t_rect.h), pygame.SRCALPHA)
        
        # Ombra sfumata (simulata con 2 rect)
        pygame.draw.rect(bg_surf, (0, 0, 0, int(60 * prog)), (4, 4, t_rect.w-4, t_rect.h-4), border_radius=10)
        
        # Sfondo principale (Sempre semi-trasparente per profonditÃ )
        bg_col = (*theme.color3("background_overlay")[:3], int(220 * prog))
        pygame.draw.rect(bg_surf, bg_col, (0, 0, t_rect.w, t_rect.h), border_radius=10)
        
        # Bordo Premium
        accent = theme.color3("btn_border_hover")
        pygame.draw.rect(bg_surf, (*accent, int(200 * prog)), (0, 0, t_rect.w, t_rect.h), width=2, border_radius=10)
        
        # Riflesso superiore per effetto vetro
        pygame.draw.line(bg_surf, (255, 255, 255, int(80 * prog)), (10, 2), (t_rect.w - 10, 2), 1)
        
        screen.blit(bg_surf, t_rect.topleft)
        screen.blit(txt_surf, (t_rect.x + pad, t_rect.y + pad))

    def _scale_icon(self, icon: pygame.Surface, rect: pygame.Rect, sm) -> pygame.Surface:
        """Scala l'icona mantenendo l'aspect ratio, garantendo che stia nel box."""
        factor = 0.95 if self.theme.is_icons_only() else 0.7
        max_w = rect.w * factor
        max_h = rect.h * factor
        
        iw, ih = icon.get_size()
        if iw == 0 or ih == 0: return icon
        
        scale = min(max_w / iw, max_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        
        return pygame.transform.smoothscale(icon, (new_w, new_h))

    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # Input
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def process_click(self, mouse_x: int, mouse_y: int) -> str | None:
        """Gestione click sui bottoni e slider con hitbox consistenti."""
        rx, ry = self.scaling_manager.screen_to_ref(mouse_x, mouse_y)
        sm = self.scaling_manager
        
        for b in self.buttons:
            # Usiamo la stessa logica di hitbox dell'update per coerenza totale
            if self._get_hitbox(b).collidepoint(rx, ry):
                rect = sm.scale_rect(b.ref_rect.x, b.ref_rect.y, b.ref_rect.w, b.ref_rect.h)
                b.ripple_pos = (mouse_x - rect.x, mouse_y - rect.y)
                b.ripple_time = 1.0
                return b.action

        for s in self.sliders:
            if self._get_hitbox(s, is_slider=True).collidepoint(rx, ry):
                s.dragging = True
                return f"{s.action}:{s.value}"
        return None

    def handle_scroll(self, dy: int) -> None:
        """Gestisce lo scroll della rotellina (carosello orizzontale o verticale)."""
        # SensibilitÃ  scroll professionale
        scroll_amount = 150.0
        
        if self.state == "settings":
            self.target_scroll_y = max(0, min(self.max_scroll_y, self.target_scroll_y - dy * scroll_amount))
        else:
            self.target_scroll_x = max(0, min(self.max_scroll_x, self.target_scroll_x - dy * scroll_amount))

    def release_click(self) -> None:
        for s in self.sliders:
            s.dragging = False

    def get_slider_value(self, action: str) -> float | None:
        for s in self.sliders:
            if s.action == action: return s.value
        return None