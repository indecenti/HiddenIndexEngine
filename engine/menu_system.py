"""
engine/menu_system.py

Sistema di menu scalabile con supporto temi grafici.
Il tema viene caricato da games/<game_id>/ui_theme/theme.json (harvestato
dall'editor); se non presente, usa il tema 'default' dell'engine.
"""

import json
import pygame
import math

from engine.utils import get_logger, get_resource_path, is_android_runtime
from engine.menu_theme import MenuTheme, load_theme_for_game
from engine.menu_skins import skin_call


# ── Reference-space chrome layout (everything below is in 1280x720 units) ────
#
# One vertical rhythm for every theme. Before this, each theme.json carried its
# own btn_y_start (200 on kids, 560 on android_std), so switching theme moved
# the whole menu up or down the screen and the scene cards fell off the bottom
# edge. Themes may still override through the layout keys named next to each
# constant, but they no longer have to in order to look right.
# Safe area: nothing a player has to read or hit is placed outside it. Menus
# are also shown on TVs and on phones with rounded corners and cutouts.
SAFE_X = 48
SAFE_TOP = 40
SAFE_BOTTOM = 40

GAME_TITLE_Y = 96          # main state: game wordmark            (game_title_y)
GAME_TITLE_SIZE = 78       # main state: wordmark size            (game_title_font_size)
STATE_TITLE_Y = 66         # other states: compact header         (title_y_offset)
MAIN_ROW_CENTER_Y = 424    # centre of the icon row on main/pause (main_row_center_y)
CARD_ROW_CENTER_Y = 412    # centre of the level/scene cards      (card_row_center_y)
ICON_LABEL_GAP = 14        # icon bottom -> caption top
ICON_LABEL_SIZE = 22       # caption size under an icon button

# The first action of a state (Play, Continue, Resume) is the one the player
# came for: it is drawn larger than its siblings so the eye lands on it.
PRIMARY_SCALE = 1.14
# Accent bar that marks the button under the pointer.
FOCUS_BAR_W = 0.42         # fraction of the button width
FOCUS_BAR_H = 3
FOCUS_BAR_GAP = 9

# Rule under a title, and the soft band that keeps a title legible on any
# background (a photograph can be bright exactly where the words are).
TITLE_RULE_W = 200
TITLE_RULE_H = 3
TITLE_RULE_GAP = 18
TITLE_SCRIM_ALPHA = 120

# Corner radii, one scale for the whole chrome.
RADIUS_PILL = 12
RADIUS_ROW = 18

# Carousel: the row is wider than the screen on purpose (the next card peeks
# in), and the peek reads as a mistake unless the edges fade out.
EDGE_FADE_W = 120

# Version line in the bottom corner of the main state.
FOOTER_SIZE = 17
FOOTER_ALPHA = 130

# Settings list: one row grid shared by sliders and toggles, so the icon, the
# label and the control line up down the column instead of each control type
# placing itself.
SETTINGS_ROW_W = 720
SETTINGS_ROW_H = 72
SETTINGS_ROW_STEP = 82
SETTINGS_ROW_Y = 132       # first group header, under the state header
SETTINGS_PAD = 24          # inner padding of a row
SETTINGS_ICON_BOX = 46     # icon column
SETTINGS_LABEL_X = 88      # label offset from the row left edge
SETTINGS_VALUE_W = 172     # value pill, identical on every toggle row
SETTINGS_VALUE_H = 44
SETTINGS_TRACK_W = 252     # slider track
SETTINGS_TRACK_H = 14
SETTINGS_READOUT_W = 108   # "67%" column at the right edge of a slider row
# Rows are grouped (audio / general / display) under a small header: a flat
# list of five unrelated controls gives the eye nothing to hold on to.
SETTINGS_GROUP_H = 28
SETTINGS_GROUP_GAP = 18    # breathing room before a new group
SETTINGS_GROUP_SIZE = 17

# Confirmation dialog (new game).
DIALOG_W = 680
DIALOG_H = 248
DIALOG_Y = 220
DIALOG_BTN_W = 268
DIALOG_BTN_H = 64
DIALOG_PAD = 30

# Level/scene cards.
CARD_CAPTION_H = 0.34      # caption gradient, as a fraction of the card height
CARD_LOCK_H = 0.30         # padlock badge, as a fraction of the card height
CARD_LOCK_DIM = 130        # extra darkening baked into a locked card


def _jitter_pair(value) -> tuple[float, float]:
    """Normalise the button_jitter return value to a (dx, dy) float pair.

    The hook is skin authored: anything that is not a numeric pair is treated
    as "no jitter" instead of raising inside the per-button draw loop.
    """
    try:
        dx, dy = value
        return (float(dx), float(dy))
    except (TypeError, ValueError):
        return (0.0, 0.0)


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
        # Chrome anchored to a screen corner (back, quit): excluded from the
        # carousel scroll, its zoom and the scroll extent. It used to be
        # inferred from the coordinates, which made the corner quit button
        # extend max_scroll_x and let the main menu drift sideways.
        self.fixed = False

        # Cache dell'immagine scalata (evita smoothscale ad ogni frame)
        self._scaled_img = None
        self._scaled_img_size = None
        # Cache dell'icona scalata (evita smoothscale ad ogni frame su mobile)
        self._scaled_icon = None
        self._scaled_icon_key = None
        # Cache effetti premium (glow morbido + ombra), generati con l'icona
        self._icon_glow = None
        self._icon_shadow = None
        # Cached caption under an icon button (normal / hover / shadow)
        self._label_key = None
        self._label_surfs = None

        # Effetti Premium
        # First action of the state (Play / Continue / Resume): drawn larger.
        self.primary = False
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

        self._android = is_android_runtime()
        # Cache delle immagini di anteprima decodificate (path -> Surface), così
        # navigare avanti/indietro tra le pagine del menu non ridecodifica i JPG.
        self._preview_raw_cache: dict = {}
        self.state = "main"
        self.current_res = "1280x720"
        self.is_fullscreen = False
        self.music_volume = 1.0
        self.sfx_volume = 1.0
        self.vibration_enabled = True

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

        # Active skin: pluggable look & feel selected by ui_theme (fallback default).
        # Every hook goes through skin_call: a broken theme degrades the look,
        # it never crashes the menu (see engine/menu_skins/base.py).
        from engine.menu_skins import get_skin
        self.skin = get_skin(self.theme)

        # Wordmark shown on the main state (the menu had no title at all: the
        # player was left with three unlabelled icons on a photograph).
        self.game_version = ""
        self.game_title = self._resolve_game_title()
        self._settings_groups: list[tuple[str, float]] = []

        self.build_buttons()

    def _resolve_game_title(self) -> str:
        """Localised game title for the main menu.

        Order: `title_key` of game_config.json resolved through the language
        manager, then the raw title, then the game id turned into words - a
        folder called `Malonno_Survivors` must never reach the player as such.
        """
        cfg: dict = {}
        cfg_path = get_resource_path("games", self.game_id, "game_config.json")
        try:
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
        except (OSError, ValueError) as exc:
            self.logger.warning("MenuSystem: game_config.json unreadable: %s", exc)

        key = cfg.get("title_key")
        title = ""
        if key:
            resolved = self.lang.get(key, "")
            if resolved and resolved != key:
                title = resolved
        version = str(cfg.get("version", "")).strip()
        self.game_version = f"v{version}" if version else ""
        title = title or cfg.get("title") or self.game_id or ""
        # A title harvested from the folder name still carries its separators
        # ("Malonno_Survivors"): no underscore ever reaches the player.
        return " ".join(title.replace("_", " ").split())

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
        primary: bool = False,
        icon: str = None,
    ) -> MenuButton:
        """Crea un bottone standard usando il layout del tema, forzando carosello orizzontale."""
        bw, bh = self.theme.btn_size()
        if override_w: bw = override_w
        if override_h: bh = override_h

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
        y = self._row_center_y() - bh / 2

        if primary and self.theme.is_icons_only() and not override_w:
            # Grown around its own centre, so the slot spacing - and with it
            # the carousel scroll - stays uniform.
            grow = float(self.theme.layout("primary_scale", PRIMARY_SCALE))
            cx, cy = rx + bw / 2, y + bh / 2
            bw, bh = bw * grow, bh * grow
            rx, y = cx - bw / 2, cy - bh / 2

        btn = MenuButton(text, action, rx, y, bw, bh, image=image)
        btn.primary = primary
        # Se abbiamo un'anteprima immagine (scene/level), evitiamo l'icona sovrapposta
        if not image:
            btn.icon_surf = self.theme.get_icon(icon or self._icon_for(action))
        self._set_tooltip(btn, action)
        return btn

    @staticmethod
    def _pretty_name(raw: str) -> str:
        """Turn an identifier into a name a player can read.

        Level and scene folders are ids (`welcome_to_malonno`); when a game
        ships no translation for one, the id itself used to be printed on the
        card, underscores and all.
        """
        text = (raw or "").strip()
        if not text:
            return ""
        if "_" in text or text.isupper() or text.islower():
            words = text.replace("_", " ").split()
            return " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize()
                            for w in words)
        return text

    def _caption_bar(self, size: tuple[int, int]) -> pygame.Surface:
        """Bottom-up gradient that carries the card caption.

        A name printed straight onto a photograph is unreadable on half the
        thumbnails; the gradient gives it a ground without hiding the image.
        """
        cache = getattr(self, "_caption_bar_cache", None)
        if cache is None:
            cache = self._caption_bar_cache = {}
        bar = cache.get(size)
        if bar is None:
            w, h = size
            bar = pygame.Surface(size, pygame.SRCALPHA)
            for y in range(h):
                alpha = int(215 * (y / max(1, h - 1)) ** 1.4)
                pygame.draw.line(bar, (0, 0, 0, alpha), (0, y), (w, y))
            if len(cache) > 6:
                cache.popitem()
            cache[size] = bar
        return bar

    def _icon_for(self, action: str) -> str:
        """Icon name for an action, in the context of the current state.

        `goto_levels` is the level list everywhere except on the main menu,
        where it is what the player calls Play: showing the stack-of-levels
        glyph there put the wrong word under the first thing the eye lands on.
        """
        if self.state in ("main", "pause") and action == "goto_levels":
            return "play"
        return action

    def _row_center_y(self) -> float:
        """Vertical centre of the button/card row for the current state.

        Cards (levels/scenes) sit slightly higher than the icon row because
        they are much taller: with one shared value the scene thumbnails were
        clipped by the bottom edge of the screen.
        """
        if self.state in ("levels", "scenes"):
            return float(self.theme.layout("card_row_center_y", CARD_ROW_CENTER_Y))
        return float(self.theme.layout("main_row_center_y", MAIN_ROW_CENTER_Y))

    def _has_icon_labels(self) -> bool:
        """True when icon buttons carry a caption under the glyph."""
        return bool(self.theme.layout("icon_labels", True)) and self.theme.is_icons_only()

    # Mappa azione -> chiave tooltip localizzata (engine/assets/strings)
    _ACTION_TIPS = {
        "goto_levels":  "tip_play",
        "goto_scenes":  "tip_play",
        "play_scene":   "tip_play",
        "goto_settings": "tip_settings",
        "confirm_new":  "tip_new_game",
        "do_new_game":  "tip_new_game",
        "resume_game":  "tip_resume",
        "quit_to_main": "tip_quit_to_main",
        "quit":         "tip_quit",
        "toggle_lang":  "tip_language",
        "toggle_res":   "tip_resolution",
        "toggle_fs":    "tip_fullscreen",
    }

    def _set_tooltip(self, btn: MenuButton, action: str, tip_key: str = None) -> None:
        """Assegna un tooltip localizzato al bottone in base all'azione."""
        key = tip_key or self._ACTION_TIPS.get(action.split(":")[0])
        if key:
            tip = self.lang.get(key, "")
            if tip:
                btn.tooltip_text = tip

    @staticmethod
    def _is_fixed(item) -> bool:
        """True for chrome pinned to a corner (back/quit), never scrolled."""
        return bool(getattr(item, "fixed", False))

    def _quit_btn(self) -> MenuButton:
        """Crea il pulsante di uscita speciale, piccolo e nell'angolo in basso a destra."""
        # Bottom right corner, inside the safe area, with room under it for the
        # caption line: the button used to sit low enough that its label was
        # clipped by the bottom edge of the screen.
        bw, bh = 92, 92
        caption = (ICON_LABEL_GAP + ICON_LABEL_SIZE + 8) if self._has_icon_labels() else 0

        rx = 1280 - bw - SAFE_X
        ry = 720 - SAFE_BOTTOM - caption - bh
        
        lbl = self.lang.get("btn_quit", "QUIT")
        btn = MenuButton(lbl, "quit", rx, ry, bw, bh)
        btn.fixed = True
        btn.icon_surf = self.theme.get_icon("quit")
        self._set_tooltip(btn, "quit")
        return btn

    def _back_btn(self, target_state: str) -> MenuButton:
        """Crea un pulsante BACK professionale, ben visibile e con tooltip dedicato."""
        size = 64 if self.theme.is_icons_only() else 48
        # Top left of the safe area, centred on the header band so it lines up
        # with the title instead of floating at an arbitrary offset.
        top = STATE_TITLE_Y + int(self.theme.layout("title_font_size", 44) * 0.5) - size // 2
        btn = MenuButton("", f"goto_{target_state}", SAFE_X, max(SAFE_TOP, top), size, size)
        btn.fixed = True
        btn.tooltip_text = self.lang.get("tip_back", self.lang.get("btn_back", "Indietro"))
        
        icon = self.theme.get_icon("goto_main") # Usa freccia standard
        if icon:
            btn.icon_surf = icon # Punta giÃ  a sinistra nel file sorgente
        return btn

    def _load_raw_cached(self, path) -> "pygame.Surface | None":
        """Carica e decodifica un'immagine una sola volta (cache per path).
        Lo smoothscale alla dimensione richiesta resta a carico del chiamante."""
        key = str(path)
        surf = self._preview_raw_cache.get(key)
        if surf is None:
            try:
                surf = pygame.image.load(key).convert()
            except Exception:
                return None
            self._preview_raw_cache[key] = surf
        return surf

    def _load_preview_raw(self, scene_dir) -> "pygame.Surface | None":
        """Carica l'immagine di anteprima di una scena per le card del menu.
        Preferisce la thumbnail leggera (_preview.jpg) generata in
        pacchettizzazione: ~80KB vs background full-res fino a 20MB/67MB-RAM.
        Fallback al background full-res quando la thumbnail non esiste
        (es. esecuzione desktop da sorgente non pacchettizzato)."""
        thumb = scene_dir / "_preview.jpg"
        if thumb.exists():
            s = self._load_raw_cached(thumb)
            if s is not None:
                return s
        # Fallback: leggi il nome del background reale da scene.json
        bg_file = "background.png"
        s_cfg_p = scene_dir / "scene.json"
        if s_cfg_p.exists():
            try:
                with open(s_cfg_p, "r", encoding="utf-8") as sf:
                    bg_file = json.load(sf).get("background", "background.png")
            except Exception:
                pass
        bg_p = scene_dir / bg_file
        return self._load_raw_cached(bg_p) if bg_p.exists() else None

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

    def _build_from_view(self, view: dict, has_save: bool) -> None:
        """Costruisce bottoni e slider a partire dalla configurazione dichiarativa JSON."""
        buttons_cfg = view.get("buttons", [])
        
        # Filtra i bottoni (es. `requires_save`)
        filtered_btns = []
        for b in buttons_cfg:
            req_save = b.get("requires_save")
            if req_save is True and not has_save:
                continue
            if req_save is False and has_save:
                continue
            filtered_btns.append(b)
            
        total_std = sum(1 for b in filtered_btns if not b.get("is_back") and not b.get("is_quit") and not b.get("custom_pos"))
        std_idx = 0
        
        for b_cfg in filtered_btns:
            lbl_key = b_cfg.get("text_key", "btn_unknown")
            lbl = self.lang.get(lbl_key, lbl_key)
            act = b_cfg.get("action", "none")
            
            override_w = b_cfg.get("width")
            override_h = b_cfg.get("height")
            
            if b_cfg.get("is_back"):
                target = act.replace("goto_", "")
                self.buttons.append(self._back_btn(target))
                continue
                
            if b_cfg.get("is_quit"):
                self.buttons.append(self._quit_btn())
                continue
                
            if "custom_pos" in b_cfg:
                # Layout custom: x, y espliciti (es: popup)
                cx, cy = b_cfg["custom_pos"]
                bw, bh = override_w or self.theme.btn_size()[0], override_h or self.theme.btn_size()[1]
                rx = cx - bw / 2
                btn = MenuButton(lbl, act, rx, cy, bw, bh)
                self.buttons.append(btn)
                continue
                
            # Bottone standard del carosello
            btn = self._std_btn(lbl, act, std_idx, total_std, override_w=override_w,
                                override_h=override_h, primary=(std_idx == 0))
            tip_key = b_cfg.get("tip_key")
            if tip_key:
                self._set_tooltip(btn, act, tip_key=tip_key)
            self.buttons.append(btn)
            std_idx += 1

        sliders_cfg = view.get("sliders", [])
        for s_cfg in sliders_cfg:
            lbl_key = s_cfg.get("text_key", "slider_unknown")
            lbl = self.lang.get(lbl_key, lbl_key)
            act = s_cfg.get("action", "none")
            
            override_w = s_cfg.get("width", 400)
            override_h = s_cfg.get("height", 20)
            
            if "custom_pos" in s_cfg:
                cx, cy = s_cfg["custom_pos"]
                s_val = self.music_volume if "music" in act else self.sfx_volume
                rx = cx - override_w / 2
                self.sliders.append(MenuSlider(lbl, act, rx, cy, override_w, override_h, s_val))

    def build_buttons(self, has_save: bool = False) -> None:
        """Ricalcola bottoni e slider in base allo stato corrente del menu."""
        self.buttons.clear()
        self.sliders.clear()

        view = self.theme.get_view(self.state)
        if view:
            self._build_from_view(view, has_save)
            return

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
                btn = self._std_btn(lbl, act, i, total, primary=(i == 0))
                # Con salvataggio il primo pulsante è "Continua": tooltip dedicato
                if has_save and i == 0 and act == "goto_levels":
                    self._set_tooltip(btn, act, tip_key="tip_continue")
                self.buttons.append(btn)
            
            # Aggiunta del pulsante QUIT in posizione dedicata (basso a destra)
            self.buttons.append(self._quit_btn())

        elif self.state == "confirm_new":
            # A destructive choice deserves a dialog, not two lines of text
            # floating over the background. The message used to be built as a
            # locked button, which is why it rendered in the disabled colour.
            cx = self.theme.btn_center_x()
            card = pygame.Rect(int(cx - DIALOG_W / 2), DIALOG_Y, DIALOG_W, DIALOG_H)
            self._dialog_rect = card
            self._dialog_text = self.lang.get(
                "msg_confirm_new_game",
                "Starting a new game erases your progress. Continue?")

            y = card.bottom - DIALOG_BTN_H - DIALOG_PAD
            gap = 24
            self.buttons = [
                MenuButton(self.lang.get("btn_confirm_new_game", "Start a new game"),
                           "do_new_game", card.centerx - DIALOG_BTN_W - gap / 2, y,
                           DIALOG_BTN_W, DIALOG_BTN_H),
                MenuButton(self.lang.get("btn_cancel", "Cancel"),
                           "goto_main", card.centerx + gap / 2, y,
                           DIALOG_BTN_W, DIALOG_BTN_H),
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
                                raw = self._load_preview_raw(ld / first_scene_id)
                                if raw is not None:
                                    preview = pygame.transform.smoothscale(raw, (bw, bh))
                        except Exception: pass

                    is_unlocked = level_id in unlocked_lvls
                    if is_unlocked: focus_idx = i

                    # The card shows the name and nothing else: the lock state
                    # is drawn as a badge, it is not spelled into the label
                    # ("- WELCOME_TO_MALONNO - (LOCKED)" used to reach players).
                    display_text = self._pretty_name(level_name)
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
                                name = self._pretty_name(self.lang.get(f"{scene_id}_name", scene_id))
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
            # (group, label key, action, value): the group is what turns five
            # unrelated controls into a list the eye can scan.
            items = [
                ("audio", "label_music_volume", "set_music_volume", "slider_music"),
                ("audio", "label_sfx_volume", "set_sfx_volume", "slider_sfx"),
                ("general", "label_language", "toggle_lang",
                 self.lang.current_language.upper()),
            ]
            # Su Android la risoluzione NON è modificabile: si adatta sempre al
            # dispositivo. Niente toggle risoluzione/fullscreen (sempre fullscreen).
            # Il feedback aptico (vibrazione) ha senso solo su touch/Android.
            if is_android_runtime():
                items.append(("general", "opt_vibration", "toggle_vibration",
                              "ON" if self.vibration_enabled else "OFF"))
            else:
                items.append(("display", "label_resolution", "toggle_res", self.current_res))
                items.append(("display", "label_fullscreen", "toggle_fs",
                              "ON" if self.is_fullscreen else "OFF"))
            
            row_w = SETTINGS_ROW_W
            start_x = (1280 - row_w) / 2
            self._settings_groups = []
            group_titles = {
                "audio": self.lang.get("settings_group_audio", "AUDIO"),
                "general": self.lang.get("settings_group_general", "GENERAL"),
                "display": self.lang.get("settings_group_display", "DISPLAY"),
            }

            ry = SETTINGS_ROW_Y
            open_group = None
            for group, lang_key, act, val in items:
                if group != open_group:
                    if open_group is not None:
                        ry += SETTINGS_GROUP_GAP
                    self._settings_groups.append(
                        (group_titles.get(group, group.upper()), ry))
                    ry += SETTINGS_GROUP_H + 8
                    open_group = group

                lbl = self.lang.get(lang_key, lang_key)
                rx = start_x
                row = pygame.Rect(rx, ry, row_w, SETTINGS_ROW_H)

                if "slider" in val:
                    s_val = self.music_volume if "music" in val else self.sfx_volume
                    track_x = row.right - SETTINGS_PAD - SETTINGS_READOUT_W - SETTINGS_TRACK_W
                    track_y = row.centery - SETTINGS_TRACK_H / 2
                    slider = MenuSlider(lbl, act, track_x, track_y,
                                        SETTINGS_TRACK_W, SETTINGS_TRACK_H, s_val)
                    # The row is what the player reads (icon, label, readout);
                    # ref_rect stays the track so dragging keeps its precision.
                    slider.row_ref = row
                    self.sliders.append(slider)
                else:
                    btn = MenuButton(val, act, rx, ry, row_w, SETTINGS_ROW_H)
                    btn.label_text = lbl
                    btn.icon_surf = self.theme.get_icon(act)
                    tip = self.lang.get(self._ACTION_TIPS.get(act, ""), "")
                    btn.tooltip_text = f"{tip} ({val})" if tip else f"{lbl}: {val}"
                    self.buttons.append(btn)

                ry += SETTINGS_ROW_STEP

        elif self.state == "pause":
            labels_actions = [
                (self.lang.get("btn_resume", "Riprendi"), "resume_game"),
                (self.lang.get("btn_settings", "Impostazioni"), "goto_settings"),
                (self.lang.get("btn_quit_to_main", "Menu"), "quit_to_main"),
            ]
            total = len(labels_actions)
            for i, (lbl, act) in enumerate(labels_actions):
                self.buttons.append(self._std_btn(lbl, act, i, total, primary=(i == 0)))

        # The skin may recompose the layout (kids arc, horror sparse) before the
        # scroll/focus computation. It only acts on vertical offsets.
        skin_call(self.skin, "arrange", self)

        # --- Calcolo scroll carosello + auto-focus su ultimo sbloccato ---
        
        # Calcolo max_scroll_x/y per il carosello
        if self.buttons or self.sliders:
            # Corner chrome (back/quit) must not extend the scroll range.
            scrollable_b = [b for b in self.buttons if not self._is_fixed(b)]
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

    
    def _draw_flashlight(self, screen: pygame.Surface, sw: int, sh: int,
                         f_pos: tuple[int, int], f_radius: int) -> None:
        """Velo scuro con foro a torcia (semitrasparente per natura: non opacizzabile).

        PERF: la versione originale, OGNI frame, allocava una Surface SRCALPHA
        fullscreen, la riempiva e ridisegnava ~140 cerchi in un loop Python, poi
        la blittava intera. Su pygame ARM/swiftshader questo e' un killer.

        Qui:
          - il GRADIENTE del foro (l'output del loop di cerchi) e' una piccola
            Surface SRCALPHA (2*raggio) cachata e ricostruita solo se cambia il
            raggio: e' l'unica parte costosa, ora fatta una volta sola.
          - il velo fullscreen e' una Surface persistente: invece di riallocarla
            e ridisegnarla ogni frame, si ripristina a (0,0,0,250) SOLO la regione
            precedentemente forata, poi si "punzona" il nuovo foro con
            BLEND_RGBA_MIN (prende l'alpha minima -> identico al disegnare cerchi
            neri ad alpha decrescente sopra un fondo pieno a 250).
        I pixel risultanti sono IDENTICI all'originale su entrambe le piattaforme.
        """
        # (Ri)costruzione del foro-gradiente in cache (solo se cambia il raggio)
        if getattr(self, "_flash_hole_radius", None) != f_radius and f_radius > 0:
            d = f_radius * 2
            hole = pygame.Surface((d, d), pygame.SRCALPHA)
            hole.fill((0, 0, 0, 250))
            c = (f_radius, f_radius)
            for r in range(f_radius, 0, -2):
                alpha = int(250 * (r / f_radius) ** 1.2)
                pygame.draw.circle(hole, (0, 0, 0, alpha), c, r)
            self._flash_hole = hole
            self._flash_hole_radius = f_radius

        # (Ri)costruzione del velo fullscreen persistente (solo su resize)
        if getattr(self, "_flash_ov_size", None) != (sw, sh):
            ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 250))
            self._flash_ov = ov
            self._flash_ov_size = (sw, sh)
            self._flash_prev_rect = None

        ov = self._flash_ov
        hole = getattr(self, "_flash_hole", None)
        if ov is None or hole is None:
            return

        # Ripristina al buio pieno solo la zona forata nel frame precedente
        prev = getattr(self, "_flash_prev_rect", None)
        if prev is not None:
            ov.fill((0, 0, 0, 250), prev)

        # Punzona il nuovo foro (BLEND_RGBA_MIN == minimo per-pixel dell'alpha)
        d = f_radius * 2
        dst = pygame.Rect(f_pos[0] - f_radius, f_pos[1] - f_radius, d, d)
        ov.blit(hole, dst, special_flags=pygame.BLEND_RGBA_MIN)
        self._flash_prev_rect = dst

        screen.blit(ov, (0, 0))

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
        is_fixed = self._is_fixed(item)
        
        # 2. Applica scroll
        rect = item.ref_rect.copy()
        if not is_fixed:
            rect.x -= self.scroll_x
            rect.y -= self.scroll_y
            
        # 3. Coerenza con Zoom Carosello (Solo per stati carosello e bottoni non fissi)
        if not is_slider and self.state in ("main", "levels", "scenes", "pause") and not is_fixed:
            # Calcolo basato sul centro dello schermo (1280/2 = 640)
            dist_center = abs(rect.centerx - 640)
            zoom = 1.0 + max(0, (1.0 - dist_center / 640)) * self.skin.carousel_zoom
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
        skin_call(self.skin, "update", self, dt)
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
            
            # 3. Floating Animation (Re-enabled for dynamic premium feel)
            # Oscilla dolcemente. Si riduce se il cursore Ã¨ sopra il bottone (hover_time).
            f_amp = self.skin.float_amp
            if self.skin.reduced(self) and self.theme.motion_disabled("float"):
                f_amp = 0.0
            b.float_offset = math.sin(tick * 3.0 + i) * f_amp * (1.0 - b.hover_time * 0.8)
            
            # 4. Magnetic Effect (Sottile interazione)
            if not hasattr(b, "angle"): b.angle = 0.0
            b.angle = 0.0  # Tilt ancora disattivato per via delle Surface opache scalate
            if not hasattr(b, "mag_offset"): b.mag_offset = [0.0, 0.0]
            
            if b.hovered and self.skin.magnetic:
                dx = rx - b.ref_rect.centerx
                dy = ry - b.ref_rect.centery
                # Limitiamo il pull massimo a 6 pixel
                target_mag_x = (dx / max(1, b.ref_rect.w / 2.0)) * 6.0
                target_mag_y = (dy / max(1, b.ref_rect.h / 2.0)) * 6.0
                b.mag_offset[0] += (target_mag_x - b.mag_offset[0]) * dt * 10.0
                b.mag_offset[1] += (target_mag_y - b.mag_offset[1]) * dt * 10.0
            else:
                b.mag_offset[0] += (0.0 - b.mag_offset[0]) * dt * 10.0
                b.mag_offset[1] += (0.0 - b.mag_offset[1]) * dt * 10.0

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

        # Per-skin background atmosphere (aurora/fog/sky) over the core bg.
        skin_call(self.skin, "draw_background_pre", self, screen, sw, sh)

        # ââ 1. Effetto Torcia (Flashlight)
        if theme.has_flashlight():
            f_pos = theme.flashlight_pos(sw, sh)
            f_radius = sm.scale_value(theme.fx("flashlight_radius", 280))
            self._draw_flashlight(screen, sw, sh, f_pos, f_radius)

        # ── 1.5 Header: scrim, title (skin), accent rule
        self._draw_title_scrim(screen, sw, sm)
        skin_call(self.skin, "draw_title", self, screen)
        self._draw_title_rule(screen, sm)
        self._draw_state_subtitle(screen, sm)
        if self.state == "settings":
            self._draw_group_headers(screen, sm)

        # The confirmation card is painted before the buttons on it.
        if self.state == "confirm_new":
            self._draw_dialog(screen, sm)

        # ââ 2. Render Bottoni (Con supporto Carosello)
        for b in self.buttons:
            rect = sm.scale_rect(b.ref_rect.x, b.ref_rect.y, b.ref_rect.w, b.ref_rect.h)

            # Chrome pinned to a corner never scrolls with the carousel.
            is_fixed = self._is_fixed(b)
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
                zoom_factor = 1.0 + max(0, (1.0 - dist_center / max_dist)) * self.skin.carousel_zoom
            
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

            # Skin hooks: positional jitter + decoration BEHIND the button.
            # A skin returning a malformed jitter must not break the draw pass.
            jdx, jdy = _jitter_pair(skin_call(self.skin, "button_jitter", self, b))
            if jdx or jdy:
                draw_rect.x += int(sm.scale_value(jdx))
                draw_rect.y += int(sm.scale_value(jdy))
            # Skins decorate BUTTONS, not list rows: the kids card-and-shadow
            # behind every settings row framed it a second time, and only the
            # toggle rows (which are buttons) got it, so half the list looked
            # different from the other half.
            if self.state != "settings":
                skin_call(self.skin, "behind_button", self, screen, b, draw_rect, is_locked)

            if b.image:
                # Bottone Scena/Anteprima. PERF: smoothscale + overlay seppia/scurente
                # vengono BAKED una volta nell'immagine cacheata (opaca), così per
                # frame si fa un solo blit OPACO (i blit SRCALPHA per-card erano
                # lentissimi su pygame ARM e rallentavano la selezione scena).
                # Dimensione QUANTIZZATA (step 6px): lo zoom carosello + lo scroll
                # variano draw_rect.w/h di pochi pixel ogni frame; senza quantizzazione
                # la preview veniva RI-SMOOTHSCALATA (immagine grande) OGNI frame -> il
                # collo di bottiglia del menu scene (~15ms/card). Quantizzando, a riposo
                # e' un cache-hit; lo scarto (<=3px, immagine centrata) e' impercettibile.
                size = (max(8, round(draw_rect.w / 6) * 6), max(8, round(draw_rect.h / 6) * 6))
                if b._scaled_img is None or b._scaled_img_size != size:
                    base = pygame.transform.smoothscale(b.image, size).convert()
                    ov_col = theme.color("scene_overlay_normal")
                    ov = pygame.Surface(size, pygame.SRCALPHA)
                    ov.fill(ov_col[:4] if len(ov_col) == 4 else (*ov_col, 120))
                    base.blit(ov, (0, 0))
                    if theme.has_sepia():
                        sa = int(theme._effects.get("sepia_alpha", 30))
                        sp = pygame.Surface(size, pygame.SRCALPHA)
                        sp.fill((120, 80, 20, sa))
                        base.blit(sp, (0, 0))

                    # Caption ground, baked with the rest: it never animates.
                    cap_h = max(24, int(size[1] * CARD_CAPTION_H))
                    base.blit(self._caption_bar((size[0], cap_h)), (0, size[1] - cap_h))

                    if is_locked:
                        # A locked card is dimmed and carries a padlock badge.
                        # The red "[LOCKED]" caption that used to sit across the
                        # middle also duplicated the text of the label itself.
                        dim = pygame.Surface(size, pygame.SRCALPHA)
                        dim.fill((6, 8, 14, CARD_LOCK_DIM))
                        base.blit(dim, (0, 0))
                        lock_icon = theme.get_icon("lock")
                        if lock_icon is not None:
                            side = max(16, int(size[1] * CARD_LOCK_H))
                            badge = pygame.transform.smoothscale(lock_icon, (side, side))
                            base.blit(badge, badge.get_rect(
                                center=(size[0] // 2, int(size[1] * 0.42))))

                    radius = theme.border_radius()
                    pygame.draw.rect(base, theme.color3("scene_border_normal"),
                                     (0, 0, size[0], size[1]), width=2, border_radius=radius)
                    if radius > 0 and not self._android:
                        # Round the photograph itself, otherwise its square
                        # corners poke out of the rounded frame. Desktop only:
                        # the per-pixel alpha blit this costs is the one the
                        # mobile path deliberately avoids.
                        mask = pygame.Surface(size, pygame.SRCALPHA)
                        pygame.draw.rect(mask, (255, 255, 255, 255),
                                         (0, 0, size[0], size[1]), border_radius=radius)
                        base = base.convert_alpha()
                        base.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    if self._android:
                        # ETICHETTA bakata nella preview (testo statico): il blit
                        # per-pixel-alpha delle surface di testo OGNI frame era il costo
                        # residuo del menu scena su GPU mobile (~12ms). Bakandola, per
                        # frame resta un SOLO blit opaco. Hover-color trascurabile su touch.
                        nf = theme.get_font(theme.font_size_scene(), sm)
                        ncol = theme.caption_text(is_locked)
                        cx = size[0] // 2
                        if theme.has_text_shadow():
                            sc = theme._effects.get("text_shadow_color", [0, 0, 0, 120])
                            shs = nf.render(b.text, True, (sc[0], sc[1], sc[2]))
                            sr = shs.get_rect(midbottom=(cx, size[1] - 14)); sr.x += 1; sr.y += 1
                            base.blit(shs, sr)
                        nsurf = nf.render(b.text, True, ncol)
                        base.blit(nsurf, nsurf.get_rect(midbottom=(cx, size[1] - 14)))
                    b._scaled_img = base
                    b._scaled_img_size = size
                screen.blit(b._scaled_img, b._scaled_img.get_rect(center=draw_rect.center))
                if b.hovered:
                    pygame.draw.rect(screen, theme.color3("scene_border_hover"), draw_rect,
                                     width=2, border_radius=theme.border_radius())

                if not self._android:
                    # Desktop: live label, so it can take the hover colour.
                    if b.icon_surf:
                        ico_scaled = self._scale_icon_cached(b, draw_rect, sm)
                        screen.blit(ico_scaled, ico_scaled.get_rect(center=draw_rect.center))
                    else:
                        label_rect = draw_rect.copy()
                        label_rect.height -= sm.scale_value(10)
                        font = theme.get_auto_font(b.text, theme.font_size_scene(),
                                                   b.ref_rect.w - 32, sm)
                        # The caption sits on the gradient baked into the card,
                        # not on the theme surface: it takes a colour picked for
                        # that, or a dark-text theme prints black on black.
                        col = theme.caption_text(is_locked)
                        shadow = theme.render_cached(font, b.text, (6, 6, 10))
                        label = theme.render_cached(font, b.text, col)
                        pos = label.get_rect(midbottom=(label_rect.centerx,
                                                        label_rect.bottom))
                        screen.blit(shadow, (pos.x + 1, pos.y + 1))
                        screen.blit(label, pos)
                elif b.icon_surf:
                    # Android: card con icona (caso raro) -> blit icona dal vivo.
                    ico_scaled = self._scale_icon_cached(b, draw_rect, sm)
                    screen.blit(ico_scaled, ico_scaled.get_rect(center=draw_rect.center))
            else:
                # Bottone Standard/Icona. In the settings list the row surface
                # IS the plate: drawing the themed button background under it
                # framed every toggle row twice (visible on kids).
                if self.state != "settings":
                    theme.draw_btn_bg(screen, draw_rect, b.hovered, is_locked,
                                      hover_t=b.hover_time)
                
                # Ripple
                if b.ripple_pos and b.ripple_time > 0:
                    r_rad = int((1.0 - b.ripple_time) * draw_rect.w * 0.8)
                    r_surf = pygame.Surface((draw_rect.w, draw_rect.h), pygame.SRCALPHA)
                    pygame.draw.circle(r_surf, (255, 255, 255, int(b.ripple_time * 100)), b.ripple_pos, r_rad)
                    screen.blit(r_surf, draw_rect, special_flags=pygame.BLEND_RGBA_ADD)

                if b.icon_surf or self.state == "settings":
                    if self.state == "settings":
                        self._draw_settings_row(screen, b, draw_rect, sm)
                    else:
                        ico_scaled, _glow, _shadow = self._icon_fx(b, draw_rect, sm)
                        # L'icona ottenuta è CONDIVISA (in cache): qualunque effetto
                        # che la modifica in-place (es. riflesso BLEND_ADD) deve prima
                        # lavorare su una copia, altrimenti l'effetto si accumula e
                        # l'icona diventa progressivamente bianca.
                        ico_owned = False

                        if theme.is_icons_only() and not self._android:
                            # Effetti Professionali per Pure Icons
                            # Ombra soffusa (profondita') + glow morbido a forma
                            # d'icona. Superfici sfocate in cache: a runtime solo
                            # un blit con alpha modulata (riposo + hover + respiro).
                            breath = (math.sin(theme._tick * 3.2) + 1.0) * 0.5
                            if _shadow is not None:
                                _sh = _shadow.copy()
                                _sh.fill((255, 255, 255, int(70 + 55 * b.hover_time)),
                                         special_flags=pygame.BLEND_RGBA_MULT)
                                _off = max(3, int(draw_rect.h * 0.05))
                                screen.blit(_sh, _sh.get_rect(center=(draw_rect.centerx, draw_rect.centery + _off)))
                            if _glow is not None:
                                _g = _glow.copy()
                                _gk = int(34 + 165 * b.hover_time + 22 * breath * (0.4 + b.hover_time))
                                _g.fill((255, 255, 255, max(0, min(255, _gk))),
                                        special_flags=pygame.BLEND_RGBA_MULT)
                                screen.blit(_g, _g.get_rect(center=draw_rect.center))
                            
                            # Scale + Rotate (Tilt) - Disabilitati in settings per stabilitÃ 
                            s = 1.0
                            if self.state != "settings":
                                s = 1.0 + max(theme.pulse_scale() - 1.0, 0.12) * b.hover_time
                                
                            if s != 1.0:
                                ico_scaled = pygame.transform.smoothscale(ico_scaled, (int(ico_scaled.get_width()*s), int(ico_scaled.get_height()*s)))
                                ico_owned = True
                            if hasattr(b, "angle") and abs(b.angle) > 0.1 and self.state != "settings":
                                ico_scaled = pygame.transform.rotozoom(ico_scaled, b.angle, 1.0)
                                ico_owned = True
                            
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
                                # Mai modificare la surface in cache: lavora su copia.
                                if not ico_owned:
                                    ico_scaled = ico_scaled.copy()
                                    ico_owned = True
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

                        if self._android:
                            # Blit OPACO: l'icona viene composta UNA volta su un chip
                            # del colore ESATTO del fondo bottone (android_btn_fill).
                            # Il blit per-pixel-alpha dell'icona era ~9ms/bottone su GPU
                            # mobile (costo dominante del menu); opaco e' ~10x piu' veloce
                            # e visivamente identico (il chip ha lo stesso colore del fondo).
                            fill = theme.android_btn_fill(is_locked, b.hover_time)
                            okey = (ico_scaled.get_width(), ico_scaled.get_height(), tuple(fill))
                            if getattr(b, "_op_icon_key", None) != okey:
                                _chip = pygame.Surface(ico_scaled.get_size())
                                _chip.fill(fill)
                                _chip.blit(ico_scaled, (0, 0))
                                b._op_icon = _chip.convert()
                                b._op_icon_key = okey
                            screen.blit(b._op_icon, b._op_icon.get_rect(center=draw_rect.center))
                        else:
                            screen.blit(ico_scaled, ico_scaled.get_rect(center=draw_rect.center))

                        if self._has_icon_labels() and self.state in ("main", "pause"):
                            self._draw_icon_label(screen, b, draw_rect, sm)
                        self._draw_focus_bar(screen, b, draw_rect, sm)

                    # Tooltip Pop-in: Differito alla fine per Z-index perfetto
                    tt_text = getattr(b, "tooltip_text", b.text)
                    show_tt = False
                    if b.hovered:
                        if self.state == "settings":
                            # In the settings list the tooltip belongs to the
                            # icon/label column, not to the control on the right.
                            icon_area_w = sm.scale_value(SETTINGS_LABEL_X)
                            if self.mouse_pos[0] < draw_rect.left + icon_area_w:
                                show_tt = True
                        else:
                            # With a caption under the icon the tooltip is extra
                            # detail, not the only label: it waits for a real
                            # hover instead of firing the moment the pointer
                            # crosses the button.
                            delay = 0.6 if self._has_icon_labels() else 0.1
                            if theme.is_icons_only() or b.hover_time > 0.6:
                                show_tt = b.hover_time > delay
                    
                    if show_tt:
                        anchor = draw_rect.copy()
                        if self.state != "settings":
                            bottom = self._caption_bottom(b, draw_rect, sm)
                            anchor.height = max(anchor.height, bottom - anchor.top
                                                + sm.scale_value(FOCUS_BAR_GAP + FOCUS_BAR_H))
                        tooltip_queue.append((tt_text, anchor, b.hover_time))
                else:
                    if self.state == "confirm_new":
                        self._draw_dialog_button(screen, draw_rect,
                                                 b.action == "do_new_game",
                                                 b.hover_time, sm)
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
            track = sm.scale_rect(s.ref_rect.x, s.ref_rect.y, s.ref_rect.w, s.ref_rect.h)
            track.y -= int(sm.scale_value(self.scroll_y))

            row = None
            row_ref = getattr(s, "row_ref", None)
            if row_ref is not None:
                row = sm.scale_rect(row_ref.x, row_ref.y, row_ref.w, row_ref.h)
                row.y -= int(sm.scale_value(self.scroll_y))

            bounds = row if row is not None else track
            if bounds.bottom < 0 or bounds.top > sh:
                continue

            if row is not None:
                # Same grid as the toggle rows: plate, icon column, label.
                self._draw_row_base(screen, s, row, theme.get_icon(s.action),
                                    s.label, s.hover_time, sm)

            # Track
            radius = max(1, track.h // 2)
            pygame.draw.rect(screen, theme.color3("slider_bg"), track, border_radius=radius)
            pygame.draw.rect(screen, (*theme.color3("btn_border_normal")[:3], 100), track,
                             width=1, border_radius=radius)

            fill_col = theme.color3("slider_fill")
            if s.value > 0:
                prog = pygame.Rect(track.x, track.y, int(track.w * s.value), track.h)
                pygame.draw.rect(screen, fill_col, prog, border_radius=radius)

            # Handle: one disc with a themed core, growing slightly on hover.
            handle_x = track.x + int(track.w * s.value)
            h_rad = int(track.h * (0.90 + 0.25 * s.hover_time))
            pygame.draw.circle(screen, theme.color3("slider_handle"),
                               (handle_x, track.centery), h_rad)
            pygame.draw.circle(screen, fill_col, (handle_x, track.centery),
                               max(2, int(h_rad * 0.45)))

            if row is not None:
                # Percentage readout: the volume used to be legible only by
                # hovering the slider and reading its tooltip.
                pct = f"{int(round(s.value * 100))}%"
                font = theme.get_font_role("body", theme.font_size_label(), sm)
                col = theme.lerp_color(theme.color3("text_normal"),
                                       theme.color3("text_hover"), s.hover_time)
                readout = theme.render_cached(font, pct, col)
                screen.blit(readout, readout.get_rect(
                    midright=(row.right - sm.scale_value(SETTINGS_PAD), row.centery)))

            if s.hovered:
                tip_text = self.lang(f"tip_{s.action.replace('set_', '')}", None)
                if not tip_text:
                    tip_text = self.lang(
                        f"ui_{s.action.replace('set_', '').replace('_volume', '')}", s.label)
                tooltip_queue.append((f"{tip_text}: {int(s.value * 100)}%",
                                      row if row is not None else track, 1.0))

        # --- EFFETTO LENTE D'INGRANDIMENTO (Mystery HUD) ---
        # Posizionata qui per ingrandire anche i bottoni e le voci di menu.
        # Su Android (touch) NON va mostrata: seguirebbe il punto di tocco
        # lasciando un cerchio fisso a schermo (nessun puntatore deve comparire).
        # Framing: the carousel edges fade out, the build line sits in the corner.
        self._draw_edge_fade(screen, sw, sh)
        self._draw_footer(screen, sm)

        # Per-skin front decoration (grain/confetti) over the contents.
        skin_call(self.skin, "draw_overlay", self, screen, sw, sh)

        if theme.has_magnifier() and not is_android_runtime():
            self._draw_magnifier(screen)
        # ── 4. Render Tooltips differiti (Massima prioritÃ  Z-Index)
        # Su Android (touch) i tooltip non hanno senso e sporcano lo schermo.
        if not self._android:
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
        """Load a scene preview (None when it is missing or unreadable).

        Typed exceptions only: a bare `except` here used to swallow
        KeyboardInterrupt and real bugs together with the expected
        missing/corrupt file.
        """
        try:
            raw = self._load_preview_raw(lvl_path / scene_id)
            if raw is None:
                return None
            preview = pygame.transform.smoothscale(raw, (w, h))
            if not is_unlocked:
                try:
                    preview = pygame.transform.grayscale(preview)
                except (pygame.error, AttributeError):
                    pass  # grayscale missing on old SDL builds: keep the colour preview
            return preview
        except (pygame.error, OSError, ValueError) as e:
            self.logger.warning("Scene preview '%s' not loadable: %s", scene_id, e)
            return None

    def _state_title_text(self) -> str:
        """Title of the current state ("" when the state has none).

        Public to the skins: each renders it with its own typography, so the
        game wordmark shown on the main state travels through here too.
        """
        titles = {
            "main": self.game_title,
            "pause": self.lang.get("menu_title_pause", "PAUSED"),
            "levels": self.lang.get("menu_title_levels", "LEVEL SELECTION"),
            "scenes": self.lang.get("menu_title_scenes", "SCENE SELECTION"),
            "settings": self.lang.get("menu_title_settings", "ENGINE SETTINGS"),
            "confirm_new": self.lang.get("menu_title_confirm", "WARNING"),
        }
        return titles.get(self.state, "")

    def _state_subtitle_text(self) -> str:
        """Second line under the header: where the player currently is.

        The scene list is reached from one specific level, and without its name
        the screen could belong to any of them.
        """
        if self.state == "scenes" and self.selected_level:
            return self._pretty_name(
                self.lang.get(f"{self.selected_level}_name", self.selected_level))
        return ""

    def _draw_state_subtitle(self, screen: pygame.Surface, sm) -> None:
        """Draw the breadcrumb line, under the accent rule."""
        text = self._state_subtitle_text()
        if not text:
            return
        theme = self.theme
        font = theme.get_font_role("body", theme.font_size_label() + 2, sm)
        surf = theme.render_spaced(font, text.upper(), theme.color3("text_normal"),
                                   sm.scale_value(3)).copy()
        surf.set_alpha(170)
        y = sm.scale_value(int(self._state_title_y() + self._state_title_size() * 1.12
                               + TITLE_RULE_GAP + 18))
        screen.blit(surf, surf.get_rect(midtop=(screen.get_width() // 2, y)))

    def _state_title_size(self) -> int:
        """Reference font size of the current title.

        The wordmark on the main state is the top of the type hierarchy; the
        header of the inner states stays one step below it.
        """
        if self.state == "main":
            return int(self.theme.layout("game_title_font_size", GAME_TITLE_SIZE))
        return int(self.theme.layout("title_font_size", 44))

    def _state_title_y(self) -> int:
        """Reference Y of the current title."""
        if self.state == "main":
            return int(self.theme.layout("game_title_y", GAME_TITLE_Y))
        return int(self.theme.layout("title_y_offset", STATE_TITLE_Y))

    def _draw_state_title(self, screen: pygame.Surface) -> None:
        """Draw the title of the current state (neutral core look).

        Composed once and cached: the text only changes with the state, the
        language or the resolution, while this runs 60 times a second.
        """
        title_text = self._state_title_text()
        if not title_text:
            return

        sm = self.scaling_manager
        theme = self.theme
        size = self._state_title_size()
        color = theme.color3("text_normal")
        key = (title_text, sm.scale_value(size), color)

        if getattr(self, "_title_cache_key", None) != key:
            font = theme.get_font_role("title", size, sm)
            surf = font.render(title_text.upper(), True, color)
            shadow = font.render(title_text.upper(), True, (10, 10, 15))
            shadow.set_alpha(180)
            self._title_cache = (surf, shadow)
            self._title_cache_key = key

        title_surf, shadow_surf = self._title_cache
        tx = (screen.get_width() - title_surf.get_width()) // 2
        ty = sm.scale_value(self._state_title_y())
        off = max(2, sm.scale_value(3))
        screen.blit(shadow_surf, (tx + off, ty + off))
        screen.blit(title_surf, (tx, ty))

    def _draw_icon_label(self, screen: pygame.Surface, b: "MenuButton",
                         draw_rect: pygame.Rect, sm) -> None:
        """Caption under an icon button.

        An icons-only menu asked the player to recognise a glyph with no word
        attached; the caption is what makes the main menu readable cold. Both
        colour variants are composed once and cached on the button - the hover
        one is blended on top by alpha, so hovering never rebuilds the text.
        """
        text = (b.text or "").strip()
        if not text:
            return
        theme = self.theme
        size = int(theme.layout("icon_label_size", ICON_LABEL_SIZE))
        key = (text, sm.scale_value(size))
        if b._label_key != key or b._label_surfs is None:
            font = theme.get_font_role("body", size, sm)
            spacing = sm.scale_value(2)
            b._label_surfs = (
                theme.render_spaced(font, text.upper(), theme.color3("text_normal"), spacing),
                theme.render_spaced(font, text.upper(), theme.color3("text_hover"), spacing),
                theme.render_spaced(font, text.upper(), (8, 8, 12), spacing),
            )
            b._label_key = key

        normal, hover, shadow = b._label_surfs
        gap = sm.scale_value(int(theme.layout("icon_label_gap", ICON_LABEL_GAP)))
        if self._is_fixed(b):
            top = draw_rect.bottom + gap        # corner chrome: follows its own box
        else:
            top = self._icon_label_baseline(sm)  # carousel: one shared baseline
        pos = normal.get_rect(midtop=(draw_rect.centerx, top))
        off = max(1, sm.scale_value(2))
        shadow.set_alpha(160)
        screen.blit(shadow, (pos.x + off, pos.y + off))
        screen.blit(normal, pos)
        if b.hover_time > 0.01:
            hover.set_alpha(int(255 * min(1.0, b.hover_time)))
            screen.blit(hover, pos)

    # ── Settings list ────────────────────────────────────────

    def _row_hover_plate(self, size: tuple[int, int]) -> pygame.Surface:
        """Cached highlight blended over a hovered settings row."""
        cache = getattr(self, "_row_hover_cache", None)
        if cache is None:
            cache = self._row_hover_cache = {}
        plate = cache.get(size)
        if plate is None:
            w, h = size
            radius = max(6, int(h * 0.28))
            accent = self.theme.accent()
            plate = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(plate, (*accent, 40), (0, 0, w, h), border_radius=radius)
            pygame.draw.rect(plate, (*accent, 190), (0, 0, w, h), width=2, border_radius=radius)
            if len(cache) > 4:
                cache.popitem()
            cache[size] = plate
        return plate

    def _row_surface(self, item, rect: pygame.Rect, icon: "pygame.Surface | None",
                     label: str, sm) -> pygame.Surface:
        """Everything static in a settings row, composed once per item.

        Plate, icon and label never change while the row is on screen, so they
        are drawn into one surface and the frame only pays a single blit. On
        Android that surface is OPAQUE: per-pixel-alpha blits are the dominant
        cost of this screen on a mobile GPU (the previous code went as far as
        compositing each icon onto an opaque chip for the same reason), and the
        settings background is already darkened enough for a solid row to look
        the same.
        """
        theme = self.theme
        # Colons come and go across the string catalogues; the column reads as
        # one list only when the punctuation is uniform.
        label = (label or "").strip().rstrip(":").strip()
        key = (rect.w, rect.h, id(icon), label, self._android)
        if getattr(item, "_row_key", None) == key and getattr(item, "_row_surf", None):
            return item._row_surf

        w, h = rect.w, rect.h
        radius = max(6, int(h * 0.28))
        accent = theme.accent()
        row_bg = theme.row_bg()
        if self._android:
            surf = pygame.Surface((w, h))
            surf.fill(row_bg[:3])
            pygame.draw.rect(surf, row_bg[:3], (0, 0, w, h), border_radius=radius)
        else:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(surf, row_bg, (0, 0, w, h), border_radius=radius)
        pygame.draw.rect(surf, (*accent, 45), (0, 0, w, h), width=1, border_radius=radius)

        if icon is not None:
            box = int(sm.scale_value(SETTINGS_ICON_BOX))
            glyph = pygame.transform.smoothscale(icon, (box, box))
            surf.blit(glyph, glyph.get_rect(midleft=(sm.scale_value(SETTINGS_PAD), h // 2)))

        if label:
            font = theme.get_font_role("body", theme.font_size_label() + 2, sm)
            text = font.render(label, True, theme.color3("text_normal"))
            pos = text.get_rect(midleft=(sm.scale_value(SETTINGS_LABEL_X), h // 2))
            shadow = font.render(label, True, (8, 8, 12))
            shadow.set_alpha(150)
            surf.blit(shadow, (pos.x + 1, pos.y + 1))
            surf.blit(text, pos)

        item._row_surf = surf.convert() if self._android else surf.convert_alpha()
        item._row_key = key
        return item._row_surf

    def _draw_row_base(self, screen: pygame.Surface, item, rect: pygame.Rect,
                       icon: "pygame.Surface | None", label: str, hover_t: float,
                       sm) -> None:
        """Blit the composed row and, on hover, its highlight."""
        screen.blit(self._row_surface(item, rect, icon, label, sm), rect.topleft)
        if hover_t > 0.01:
            plate = self._row_hover_plate((rect.w, rect.h))
            plate.set_alpha(int(255 * min(1.0, hover_t)))
            screen.blit(plate, rect.topleft)

    def _draw_settings_row(self, screen: pygame.Surface, b: "MenuButton",
                           rect: pygame.Rect, sm) -> None:
        """A toggle row: plate, icon, label and the value in a fixed pill.

        The pill has one width on every row, so ON / 1280x720 / EN line up in a
        column instead of each row sizing its own box.
        """
        theme = self.theme
        self._draw_row_base(screen, b, rect, b.icon_surf,
                            getattr(b, "label_text", ""), b.hover_time, sm)

        if not b.text:
            return
        pill = pygame.Rect(0, 0, sm.scale_value(SETTINGS_VALUE_W),
                           sm.scale_value(SETTINGS_VALUE_H))
        pill.midright = (rect.right - sm.scale_value(SETTINGS_PAD), rect.centery)

        accent = theme.accent()
        radius = sm.scale_value(10)
        pygame.draw.rect(screen, theme.row_value_bg(), pill, border_radius=radius)
        pygame.draw.rect(screen, accent, pill, width=max(1, sm.scale_value(2)),
                         border_radius=radius)

        font = theme.get_auto_font(b.text, theme.font_size_label() + 6,
                                   SETTINGS_VALUE_W - 24, sm)
        col = theme.lerp_color(theme.color3("text_normal"),
                               theme.color3("text_hover"), b.hover_time)
        val = theme.render_cached(font, b.text, col)
        screen.blit(val, val.get_rect(center=pill.center))

    def _icon_label_baseline(self, sm) -> int:
        """Shared top edge of the captions under the carousel icons.

        Skins float, bounce and arc the buttons, and the carousel zooms the
        centred one: hanging each caption off its own button made the words
        stagger by tens of pixels. The icons keep moving, the words stay on one
        line, computed to clear the largest (zoomed) icon.
        """
        size = float(self.theme.icon_btn_size())
        size *= float(self.theme.layout("primary_scale", PRIMARY_SCALE))
        half = size * (1.0 + max(0.0, self.skin.carousel_zoom)) / 2.0
        gap = int(self.theme.layout("icon_label_gap", ICON_LABEL_GAP))
        return sm.scale_value(self._row_center_y() + half + gap)

    @staticmethod
    def _wrap_text(text: str, font, max_w: int) -> list[str]:
        """Break `text` into lines that fit `max_w` pixels."""
        lines, current = [], ""
        for word in text.split():
            probe = f"{current} {word}".strip()
            if current and font.size(probe)[0] > max_w:
                lines.append(current)
                current = word
            else:
                current = probe
        if current:
            lines.append(current)
        return lines

    def _draw_dialog(self, screen: pygame.Surface, sm) -> None:
        """Card behind the confirmation buttons, with the wrapped message."""
        ref = getattr(self, "_dialog_rect", None)
        if ref is None:
            return
        theme = self.theme
        card = sm.scale_rect(ref.x, ref.y, ref.w, ref.h)
        radius = max(8, sm.scale_value(18))
        r, g, b, alpha = theme.row_bg()
        accent = theme.accent()

        shadow = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 120), (0, 0, card.w, card.h), border_radius=radius)
        screen.blit(shadow, (card.x + sm.scale_value(4), card.y + sm.scale_value(6)))

        panel = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (r, g, b, min(255, alpha + 45)),
                         (0, 0, card.w, card.h), border_radius=radius)
        pygame.draw.rect(panel, (*accent, 190), (0, 0, card.w, card.h),
                         width=max(1, sm.scale_value(2)), border_radius=radius)
        screen.blit(panel, card.topleft)

        text = getattr(self, "_dialog_text", "")
        if not text:
            return
        font = theme.get_font_role("body", theme.font_size_label() + 6, sm)
        lines = self._wrap_text(text, font, card.w - sm.scale_value(DIALOG_PAD * 2))
        line_h = font.get_height() + sm.scale_value(6)
        top = card.y + sm.scale_value(DIALOG_PAD + 14)
        for i, line in enumerate(lines):
            surf = theme.render_cached(font, line, theme.color3("text_normal"))
            screen.blit(surf, surf.get_rect(midtop=(card.centerx, top + i * line_h)))

    def _draw_dialog_button(self, screen: pygame.Surface, rect: pygame.Rect,
                            primary: bool, hover_t: float, sm) -> None:
        """Plate under a dialog button.

        Most themes set `no_btn_bg` because their buttons are icons; on a
        dialog that leaves the two labels floating on the card with nothing to
        click, so the plate is drawn here regardless.
        """
        theme = self.theme
        radius = max(6, sm.scale_value(12))
        accent = theme.accent()
        fill = theme.row_value_bg()
        if primary:
            # The confirming button takes the theme accent (`slider_fill` is the
            # only saturated colour every theme defines), so the destructive
            # choice is not the same grey as the way out of the dialog.
            base = theme.color3("slider_fill")
            fill = tuple(theme.lerp_color(base, theme.color3("text_hover"),
                                          0.18 * hover_t)[:3])
        pygame.draw.rect(screen, fill, rect, border_radius=radius)
        width = max(1, sm.scale_value(2 if primary else 1))
        pygame.draw.rect(screen, accent, rect, width=width, border_radius=radius)

    # ── Header, focus and framing ────────────────────────────────

    def _draw_title_scrim(self, screen: pygame.Surface, sw: int, sm) -> None:
        """Soft band behind the title.

        The menu sits on whatever screenshot the game ships, and a title only
        needs one bright cloud behind it to become unreadable. The band is
        cached per size: it is a gradient, not something that animates.
        """
        if not self._state_title_text():
            return
        top = sm.scale_value(max(0, self._state_title_y() - 34))
        height = sm.scale_value(self._state_title_size() + 96)
        raw = self.theme.color("background_overlay")
        tint = (raw[0], raw[1], raw[2])
        # Strength follows the theme scrim: a bright theme (kids) gets a haze of
        # its own sky colour instead of a black band across the sun.
        peak = int(TITLE_SCRIM_ALPHA * (raw[3] if len(raw) > 3 else 220) / 255)
        key = (sw, height, tint, peak)
        cache = getattr(self, "_scrim_cache", None)
        if cache is None:
            cache = self._scrim_cache = {}
        band = cache.get(key)
        if band is None:
            band = pygame.Surface((sw, height), pygame.SRCALPHA)
            for y in range(height):
                # Strongest just behind the words, gone at the top and bottom.
                v = abs((y / max(1, height - 1)) - 0.42) * 2.0
                alpha = int(peak * max(0.0, 1.0 - v) ** 1.6)
                if alpha <= 0:
                    continue
                # ... and gone at the left and right edges too, so it reads as a
                # glow behind the title rather than a bar across the screen.
                for x0, x1, mult in self._scrim_columns(sw):
                    a = int(alpha * mult)
                    if a > 0:
                        pygame.draw.line(band, (*tint, a), (x0, y), (x1, y))
            if len(cache) > 3:
                cache.popitem()
            cache[key] = band
        screen.blit(band, (0, top))

    @staticmethod
    def _scrim_columns(sw: int, steps: int = 48):
        """Horizontal falloff of the title scrim, as (x0, x1, multiplier)."""
        out = []
        step = max(1, sw // steps)
        for x in range(0, sw, step):
            t = abs((x + step / 2) / max(1, sw) - 0.5) * 2.0     # 0 centre, 1 edge
            mult = max(0.0, 1.0 - t ** 1.6)
            out.append((x, min(sw, x + step), mult))
        return out

    def _draw_title_rule(self, screen: pygame.Surface, sm) -> None:
        """Accent rule under the title: it closes the header band."""
        if not self._state_title_text():
            return
        theme = self.theme
        width = sm.scale_value(TITLE_RULE_W)
        height = max(1, sm.scale_value(TITLE_RULE_H))
        y = sm.scale_value(int(self._state_title_y() + self._state_title_size() * 1.12
                               + TITLE_RULE_GAP))
        rect = pygame.Rect(0, 0, width, height)
        rect.midtop = (screen.get_width() // 2, y)
        accent = theme.accent_on(theme.scrim_color())
        bar = pygame.Surface((width, height), pygame.SRCALPHA)
        for x in range(width):
            # Fades out at both ends instead of stopping dead.
            t = 1.0 - abs((x / max(1, width - 1)) - 0.5) * 2.0
            pygame.draw.line(bar, (*accent, int(235 * t ** 0.7)), (x, 0), (x, height))
        screen.blit(bar, rect.topleft)

    def _draw_focus_bar(self, screen: pygame.Surface, b: "MenuButton",
                        draw_rect: pygame.Rect, sm) -> None:
        """Accent bar under the caption of the button being pointed at."""
        if b.hover_time <= 0.02:
            return
        theme = self.theme
        width = int(draw_rect.w * FOCUS_BAR_W * min(1.0, b.hover_time))
        if width < 2:
            return
        height = max(1, sm.scale_value(FOCUS_BAR_H))
        top = self._caption_bottom(b, draw_rect, sm) + sm.scale_value(FOCUS_BAR_GAP)
        rect = pygame.Rect(0, 0, width, height)
        rect.midtop = (draw_rect.centerx, top)
        pygame.draw.rect(screen, theme.accent_on(theme.scrim_color()), rect,
                         border_radius=height // 2)

    def _caption_bottom(self, b: "MenuButton", draw_rect: pygame.Rect, sm) -> int:
        """Bottom edge of the caption drawn under an icon button."""
        if not self._has_icon_labels() or not (b.text or "").strip():
            return draw_rect.bottom
        surfs = getattr(b, "_label_surfs", None)
        height = surfs[0].get_height() if surfs else sm.scale_value(ICON_LABEL_SIZE)
        gap = sm.scale_value(int(self.theme.layout("icon_label_gap", ICON_LABEL_GAP)))
        top = draw_rect.bottom + gap if self._is_fixed(b) else self._icon_label_baseline(sm)
        return top + height

    def _draw_edge_fade(self, screen: pygame.Surface, sw: int, sh: int) -> None:
        """Fade the two screen edges when the carousel runs past them.

        The next card peeking in is intentional; a card sliced by the screen
        edge is not, and the difference is entirely in this gradient.
        """
        if self.max_scroll_x <= 0:
            return
        # Only the side that actually has more content behind it: fading the
        # left edge while the first card sits against it would just dim the card.
        left_on = self.scroll_x > 4
        right_on = self.scroll_x < self.max_scroll_x - 4
        if not (left_on or right_on):
            return
        width = int(sw * EDGE_FADE_W / 1280)
        key = (width, sh)
        cache = getattr(self, "_edge_fade_cache", None)
        if cache is None:
            cache = self._edge_fade_cache = {}
        fade = cache.get(key)
        if fade is None:
            raw = self.theme.color("background_overlay")
            base = (raw[0], raw[1], raw[2])
            peak = raw[3] if len(raw) > 3 else 220
            peak = int(peak * 0.8)
            fade = pygame.Surface((width, sh), pygame.SRCALPHA)
            for x in range(width):
                alpha = int(peak * (1.0 - x / max(1, width - 1)) ** 1.5)
                if alpha:
                    pygame.draw.line(fade, (*base, alpha), (x, 0), (x, sh))
            if len(cache) > 2:
                cache.popitem()
            cache[key] = fade
        if left_on:
            screen.blit(fade, (0, 0))
        if right_on:
            screen.blit(pygame.transform.flip(fade, True, False), (sw - width, 0))

    def _draw_footer(self, screen: pygame.Surface, sm) -> None:
        """Build line in the bottom corner of the main state."""
        text = getattr(self, "game_version", "")
        if not text or self.state != "main":
            return
        theme = self.theme
        font = theme.get_font_role("body", FOOTER_SIZE, sm)
        surf = theme.render_cached(font, text, theme.color3("text_normal")).copy()
        surf.set_alpha(FOOTER_ALPHA)
        screen.blit(surf, surf.get_rect(bottomleft=(sm.scale_value(SAFE_X),
                                                    sm.scale_value(720 - SAFE_BOTTOM))))

    def _draw_group_headers(self, screen: pygame.Surface, sm) -> None:
        """Section headers of the settings list."""
        groups = getattr(self, "_settings_groups", None)
        if not groups:
            return
        theme = self.theme
        font = theme.get_font_role("body", SETTINGS_GROUP_SIZE, sm)
        accent = theme.accent_on(theme.scrim_color())
        left = sm.scale_value((1280 - SETTINGS_ROW_W) / 2 + 6)
        for text, ref_y in groups:
            y = sm.scale_value(ref_y) - int(sm.scale_value(self.scroll_y))
            if y < -sm.scale_value(SETTINGS_GROUP_H) or y > screen.get_height():
                continue
            surf = theme.render_spaced(font, text.upper(), accent, sm.scale_value(3))
            screen.blit(surf, (left, y))

    def _draw_tooltip(self, screen: pygame.Surface, text: str, rect: pygame.Rect, sm, t: float):
        """Disegna un tooltip professionale che segue il mouse con effetto pop-in elastico."""
        theme = self.theme
        start_threshold = 0.05 if theme.is_icons_only() else 0.5
        if t < start_threshold:
            return

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
        t_rect = pygame.Rect(0, 0, tw + pad * 2, th + pad * 2)

        # Anchored under the element it describes, not to the pointer: a tip
        # that follows the cursor covers the button next to the one being read,
        # and on a touch screen there is no cursor to follow at all.
        sw, sh = screen.get_size()
        gap = sm.scale_value(14)
        anim = sm.scale_value(14 * (1.0 - elastic))
        t_rect.midtop = (rect.centerx, rect.bottom + gap + anim)
        if t_rect.bottom > sh - sm.scale_value(SAFE_BOTTOM):
            t_rect.midbottom = (rect.centerx, rect.top - gap - anim)

        margin = sm.scale_value(SAFE_X)
        t_rect.x = max(margin, min(t_rect.x, sw - margin - t_rect.w))
        t_rect.y = max(sm.scale_value(SAFE_TOP), min(t_rect.y, sh - t_rect.h))
        
        # Sfondo con Effetto Glassmorfismo e Ombra Morbida
        bg_surf = pygame.Surface((t_rect.w, t_rect.h), pygame.SRCALPHA)
        
        # Ombra sfumata (simulata con 2 rect)
        pygame.draw.rect(bg_surf, (0, 0, 0, int(60 * prog)), (4, 4, t_rect.w-4, t_rect.h-4), border_radius=10)
        
        # Sfondo principale (Sempre semi-trasparente per profonditÃ )
        bg_col = (*theme.color3("background_overlay")[:3], int(220 * prog))
        pygame.draw.rect(bg_surf, bg_col, (0, 0, t_rect.w, t_rect.h), border_radius=10)
        
        # Bordo Premium
        accent = theme.accent()
        pygame.draw.rect(bg_surf, (*accent, int(200 * prog)), (0, 0, t_rect.w, t_rect.h), width=2, border_radius=10)
        
        # Riflesso superiore per effetto vetro
        pygame.draw.line(bg_surf, (255, 255, 255, int(80 * prog)), (10, 2), (t_rect.w - 10, 2), 1)
        
        screen.blit(bg_surf, t_rect.topleft)
        screen.blit(txt_surf, (t_rect.x + pad, t_rect.y + pad))

    def _scale_icon(self, icon: pygame.Surface, rect: pygame.Rect, sm) -> pygame.Surface:
        """Scala l'icona mantenendo l'aspect ratio, garantendo che stia nel box."""
        factor = 1.0 if self.theme.is_icons_only() else 0.72
        max_w = rect.w * factor
        max_h = rect.h * factor

        iw, ih = icon.get_size()
        if iw == 0 or ih == 0: return icon

        scale = min(max_w / iw, max_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)

        scaled = pygame.transform.smoothscale(icon, (new_w, new_h))
        # convert_alpha(): l'icona scalata viene blittata OGNI frame. Senza conversione
        # al formato display il blit per-pixel-alpha e' molto piu' lento su GPU mobile
        # (era ~9ms/bottone, il costo dominante del menu su Android). Pixel identici.
        try:
            scaled = scaled.convert_alpha()
        except Exception:
            pass
        return scaled

    @staticmethod
    def _icon_key(rect: pygame.Rect) -> tuple:
        """Chiave di cache icona quantizzata (step 4px). Lo zoom carosello e lo
        scroll variano di continuo draw_rect.w/h di pochi pixel: senza quantizzazione
        la cache mancava OGNI frame e si ri-eseguiva lo smoothscale (e glow/ombra)
        per ogni bottone -> crollo FPS. Quantizzando, durante il movimento si ha
        quasi sempre cache-hit; lo scarto di scala (<=4px, icona centrata) e' impercettibile."""
        return ((rect.w // 4) * 4, (rect.h // 4) * 4)

    def _scale_icon_cached(self, b: "MenuButton", rect: pygame.Rect, sm) -> pygame.Surface:
        """Come _scale_icon ma memorizza il risultato sul bottone: evita lo
        smoothscale ad ogni frame (costoso su pygame ARM). La chiave (quantizzata)
        fa ri-scalare solo a cambio dimensione reale, non per l'oscillazione zoom."""
        key = self._icon_key(rect)
        if b._scaled_icon is None or b._scaled_icon_key != key:
            b._scaled_icon = self._scale_icon(b.icon_surf, rect, sm)
            b._scaled_icon_key = key
        return b._scaled_icon

    def _icon_fx(self, b: "MenuButton", rect: pygame.Rect, sm):
        """Ritorna (icona, glow, ombra) in cache per la dimensione del box.
        Glow/ombra (superfici sfocate, 2 smoothscale ciascuna) si costruiscono SOLO
        su desktop: su Android non vengono mai disegnate (vedi gate not self._android
        nel chiamante), quindi costruirle sarebbe lavoro sprecato per ogni bottone."""
        key = self._icon_key(rect)
        if b._scaled_icon is None or b._scaled_icon_key != key:
            b._scaled_icon = self._scale_icon(b.icon_surf, rect, sm)
            b._scaled_icon_key = key
            b._icon_glow = None
            b._icon_shadow = None
        if not self._android and b._icon_glow is None and b._scaled_icon is not None:
            try:
                gc = self.theme.color3("btn_glow_color") if "btn_glow_color" in self.theme._colors else (255, 235, 180)
                b._icon_glow = MenuTheme.make_glow(b._scaled_icon, gc)
                b._icon_shadow = MenuTheme.make_shadow(b._scaled_icon)
            except Exception:
                b._icon_glow = b._icon_shadow = None
        return b._scaled_icon, b._icon_glow, b._icon_shadow

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