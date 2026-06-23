"""
engine/menu_theme.py

Gestione del tema grafico per il MenuSystem.
Carica theme.json dal gioco (ui_theme/) con fallback all'engine default.

Struttura di ricerca (priorità decrescente):
  1. games/<game_id>/ui_theme/theme.json   ← harvested dall'editor
  2. engine/assets/themes/default/theme.json ← fallback garantito
"""

import json
import math
import logging
from pathlib import Path
from typing import Any

import pygame

from engine.utils import get_resource_path, get_logger, is_android_runtime

# Su Android ombre/glow dei bottoni (Surface SRCALPHA per bottone per frame) sono
# disattivati: costo per-frame inutile su GPU/CPU mobile, impatto estetico minimo.
_ANDROID = is_android_runtime()

logger = get_logger(__name__)

# Temi disponibili (Rilevati dinamicamente)
class ThemeManager:
    """Gestore centralizzato per la scoperta e il caricamento dei temi."""
    
    _cached_themes: dict[str, dict] = {}

    @classmethod
    def discover_themes(cls) -> list[dict]:
        """Scansiona l'engine alla ricerca di temi validi."""
        cls._cached_themes = {}
        themes_dir = get_resource_path("engine", "assets", "themes")
        if not themes_dir.exists():
            return []
            
        found = []
        for d in themes_dir.iterdir():
            if d.is_dir():
                json_path = d / "theme.json"
                if json_path.exists():
                    data = _load_theme_data(json_path)
                    if data:
                        t_id = data.get("id", d.name)
                        cls._cached_themes[t_id] = data
                        
                        # Cerca anteprima (preview.png)
                        preview_p = d / "preview.png"
                        
                        found.append({
                            "id": t_id,
                            "name": data.get("display_name", t_id.capitalize()),
                            "category": data.get("category", "desktop"),
                            "path": str(json_path),
                            "preview_path": str(preview_p) if preview_p.exists() else None
                        })
        return sorted(found, key=lambda x: x["name"])

    @classmethod
    def get_theme(cls, theme_id: str, game_id: str = None) -> "MenuTheme":
        """Carica un tema specifico per nome con fallback a default."""
        if not cls._cached_themes:
            cls.discover_themes()
            
        data = cls._cached_themes.get(theme_id)
        if not data:
            # Fallback a default se il tema richiesto non esiste
            default_path = get_resource_path("engine", "assets", "themes", "default", "theme.json")
            data = _load_theme_data(default_path)
            logger.warning(f"ThemeManager: tema '{theme_id}' non trovato. Uso fallback 'default'.")
            
        return MenuTheme(data if data else {}, game_id=game_id)

# Valore sentinella per colori invalidi
_FALLBACK_COLOR: tuple[int, int, int] = (128, 128, 128)


class MenuTheme:
    """
    Wrapper attorno ai dati di theme.json.
    Espone helper per colori, layout e font già scalati.
    """

    def __init__(self, data: dict[str, Any], game_id: str = None) -> None:
        self._data = data
        self._colors: dict[str, Any] = data.get("colors", {})
        self._layout: dict[str, Any] = data.get("layout", {})
        self._font_cfg: dict[str, Any] = data.get("font", {})
        self._effects: dict[str, Any] = data.get("effects", {})
        self._views: dict[str, Any] = data.get("views", {})

        # Estensione skin (tutte OPZIONALI; se assenti lo skin usa i default).
        self._motion: dict[str, Any] = data.get("motion", {})
        self._background: dict[str, Any] = data.get("background", {})
        self._particles: dict[str, Any] = data.get("particles", {})
        self._typography: dict[str, Any] = data.get("typography", {})
        self._decor: dict[str, Any] = data.get("decor", {})
        self._audio_feel: dict[str, Any] = data.get("audio_feel", {})
        self._layout_profile: dict[str, Any] = data.get("layout_profile", {})

        # Cache font per dimensione — evita re-allocazioni ogni frame
        self._font_cache: dict[int, pygame.font.Font] = {}
        self._role_font_cache: dict = {}

        # Ticker interno per effetti animati (incrementato da update())
        self._tick: float = 0.0

        self.theme_id: str = data.get("id", "default")
        self.game_id: str = game_id
        
        # Cache icone: Sistema (Base) + Tema (Override) + Gioco (Override Max).
        # Le icone sono artwork PNG a colori e vengono usate così come sono.
        self._icons: dict[str, pygame.Surface] = {}
        self._load_system_icons()
        self._load_theme_icons()
        self._load_game_icons()

    def _load_system_icons(self) -> None:
        """Carica il set universale di icone di sistema."""
        sys_path = get_resource_path("engine", "assets", "icons", "system")
        if sys_path.exists():
            for p in sys_path.glob("*.png"):
                try:
                    self._icons[p.stem] = pygame.image.load(str(p)).convert_alpha()
                except Exception as e:
                    logger.debug("MenuTheme: errore icona sistema '%s': %s", p.name, e)

    def _load_theme_icons(self) -> None:
        """Carica le icone specifiche del tema (sovrascrivono quelle di sistema)."""
        theme_path = get_resource_path("engine", "assets", "themes", self.theme_id, "icons")
        if theme_path.exists():
            for p in theme_path.glob("*.png"):
                try:
                    self._icons[p.stem] = pygame.image.load(str(p)).convert_alpha()
                except Exception as e:
                    logger.warning("MenuTheme: errore icona tema '%s': %s", p.name, e)

    def _load_game_icons(self) -> None:
        """Carica icone specifiche iniettate direttamente nel gioco (massima priorità)."""
        if not self.game_id:
            return
        game_icons_path = get_resource_path("games", self.game_id, "ui_theme", "icons")
        if game_icons_path.exists():
            for p in game_icons_path.glob("*.png"):
                try:
                    self._icons[p.stem] = pygame.image.load(str(p)).convert_alpha()
                except Exception as e:
                    logger.warning("MenuTheme: errore icona gioco '%s': %s", p.name, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Colori
    # ─────────────────────────────────────────────────────────────────────────

    def color(self, key: str) -> tuple[int, ...]:
        """Restituisce il colore come tuple RGBA o RGB."""
        raw = self._colors.get(key)
        if raw is None:
            logger.debug("MenuTheme: colore '%s' non trovato, uso fallback.", key)
            return _FALLBACK_COLOR
        return tuple(raw)

    def color3(self, key: str) -> tuple[int, int, int]:
        """Restituisce i primi 3 canali (RGB) del colore."""
        c = self.color(key)
        return (c[0], c[1], c[2])

    def lerp_color(self, c1: tuple, c2: tuple, t: float) -> tuple:
        """Interpola tra due colori RGBA/RGB."""
        # Assicura che entrambi siano della stessa lunghezza (3 o 4)
        size = min(len(c1), len(c2))
        res = []
        for i in range(size):
            res.append(int(c1[i] + (c2[i] - c1[i]) * t))
        
        # Se uno ha alpha e l'altro no, gestiamo
        if size == 3 and len(c1) == 4: res.append(c1[3])
        elif size == 3 and len(c2) == 4: res.append(c2[3])
        
        return tuple(res)

    # ─────────────────────────────────────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────────────────────────────────────

    def layout(self, key: str, default: Any = 0) -> Any:
        # Cerca prima in _layout, poi alla radice dei dati originali
        val = self._layout.get(key)
        if val is None:
            val = self._data.get(key, default)
        return val

    def border_radius(self) -> int:
        return int(self.layout("btn_border_radius", 6))

    def border_width(self) -> int:
        return int(self.layout("btn_border_width", 1))

    def btn_size(self) -> tuple[int, int]:
        return (
            int(self.layout("btn_width", 280)),
            int(self.layout("btn_height", 50)),
        )

    def btn_center_x(self) -> float:
        return float(self.layout("btn_center_x", 640))

    def btn_y_start(self) -> float:
        return float(self.layout("btn_y_start", 300))

    def btn_y_step(self) -> float:
        return float(self.layout("btn_y_step", 80))

    def btn_layout(self) -> str:
        return str(self.layout("btn_layout", "centered"))

    def layout_val(self, key: str, default: Any = 0) -> Any:
        return self.layout(key, default)

    def is_icons_only(self) -> bool:
        return bool(self.layout("icons_only", False))

    def icon_btn_size(self) -> int:
        return int(self.layout("icon_btn_size", 120))

    def slider_height(self) -> int:
        return int(self._layout.get("slider_height", 20))

    def get_view(self, view_name: str) -> dict[str, Any]:
        """Restituisce la configurazione della vista richiesta, se presente."""
        return self._views.get(view_name, {})

    # ─────────────────────────────────────────────────────────────────────────
    # Estensione skin: motion / background / particles / decor / audio / layout
    # Tutti gli accessor sono tolleranti: sezione assente -> default fornito.
    # ─────────────────────────────────────────────────────────────────────────

    def motion(self, key: str, default: Any = None) -> Any:
        v = self._motion.get(key)
        return default if v is None else v

    def background(self, key: str, default: Any = None) -> Any:
        v = self._background.get(key)
        return default if v is None else v

    def particles_cfg(self, key: str = None, default: Any = None) -> Any:
        if key is None:
            return self._particles
        v = self._particles.get(key)
        return default if v is None else v

    def decor(self, key: str, default: Any = None) -> Any:
        v = self._decor.get(key)
        return default if v is None else v

    def audio_feel(self, key: str, default: Any = None) -> Any:
        v = self._audio_feel.get(key)
        return default if v is None else v

    def layout_profile_type(self) -> str:
        return str(self._layout_profile.get("type", "carousel"))

    def motion_disabled(self, feature: str) -> bool:
        """True se 'feature' è elencata in motion.reduced_motion.disable."""
        rm = self._motion.get("reduced_motion") or {}
        return feature in (rm.get("disable") or [])

    # ─────────────────────────────────────────────────────────────────────────
    # Font
    # ─────────────────────────────────────────────────────────────────────────

    def get_font(self, ref_size: int, scaling_manager) -> pygame.font.Font:
        """
        Restituisce un font scalato. Usa la cache per evitare allocazioni per frame.
        ref_size: dimensione in coordinate di riferimento (1280x720).
        """
        scaled_size = max(10, scaling_manager.scale_value(ref_size))
        if scaled_size in self._font_cache:
            return self._font_cache[scaled_size]

        font_family = self._font_cfg.get("family")
        try:
            if font_family:
                font_path = Path(font_family)
                if font_path.exists():
                    f = pygame.font.Font(str(font_path), scaled_size)
                else:
                    f = pygame.font.SysFont(font_family, scaled_size,
                                            bold=self._font_cfg.get("bold", False))
            else:
                f = pygame.font.SysFont(None, scaled_size,
                                        bold=self._font_cfg.get("bold", False))
        except Exception as e:
            logger.warning("MenuTheme: errore caricamento font '%s': %s", font_family, e)
            f = pygame.font.SysFont(None, scaled_size)

        self._font_cache[scaled_size] = f
        return f

    def get_auto_font(self, text: str, ref_size: int, max_w: int, sm) -> pygame.font.Font:
        """
        Restituisce un font scalato, riducendone la dimensione se il testo eccede max_w.
        """
        current_size = ref_size
        font = self.get_font(current_size, sm)
        
        # Prova a ridurre fino a un minimo di 12px (ref)
        while current_size > 12:
            t_w, _ = font.size(text)
            if t_w <= sm.scale_value(max_w - 20): # Padding 20
                break
            current_size -= 2
            font = self.get_font(current_size, sm)

        return font

    def get_font_role(self, role: str, ref_size: int, sm) -> pygame.font.Font:
        """
        Font per ruolo (display/title/body/mono) dalla sezione 'typography'.
        'family' può contenere nomi di sistema o percorsi a .ttf/.otf bundlati.
        Fallback trasparente a get_font() se il ruolo non è definito.
        """
        cfg = self._typography.get(role) if isinstance(self._typography, dict) else None
        if not cfg:
            return self.get_font(ref_size, sm)

        scaled = max(10, sm.scale_value(ref_size))
        bold = bool(cfg.get("bold", self._font_cfg.get("bold", False)))
        cache_key = (role, scaled, bold)
        cached = self._role_font_cache.get(cache_key)
        if cached is not None:
            return cached

        # 0) Font BUNDLATO per-tema: 'file' relativo a engine/assets/themes/<id>/.
        file_rel = cfg.get("file")
        if file_rel:
            try:
                fp = (Path(__file__).resolve().parent / "assets" / "themes"
                      / str(getattr(self, "theme_id", "default")) / str(file_rel))
                if fp.exists():
                    fb = pygame.font.Font(str(fp), scaled)
                    self._role_font_cache[cache_key] = fb
                    return fb
            except Exception as e:
                logger.debug("MenuTheme: font bundlato '%s' fallback: %s", file_rel, e)

        fam = cfg.get("family")
        names = fam if isinstance(fam, list) else ([fam] if fam else [])
        f: pygame.font.Font | None = None
        try:
            # 1) font file bundlato (percorso .ttf/.otf esistente)
            for nm in names:
                p = Path(str(nm))
                if p.suffix.lower() in (".ttf", ".otf") and p.exists():
                    f = pygame.font.Font(str(p), scaled)
                    break
            # 2) font di sistema per nome (SysFont accetta lista separata da virgole)
            if f is None and names:
                f = pygame.font.SysFont(",".join(str(n) for n in names), scaled, bold=bold)
        except Exception as e:
            logger.debug("MenuTheme: font ruolo '%s' fallback: %s", role, e)

        if f is None:
            f = self.get_font(ref_size, sm)

        self._role_font_cache[cache_key] = f
        return f

    def render_spaced(self, font: pygame.font.Font, text: str,
                      color: tuple, spacing: int) -> pygame.Surface:
        """Renderizza testo con spaziatura extra tra le lettere (per titoli a tema)."""
        if not spacing or spacing <= 0:
            return font.render(text, True, color)
        surfs = [font.render(ch, True, color) for ch in text]
        sp = int(spacing)
        w = sum(s.get_width() for s in surfs) + sp * max(0, len(surfs) - 1)
        h = max((s.get_height() for s in surfs), default=font.get_height())
        out = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        x = 0
        for s in surfs:
            out.blit(s, (x, 0))
            x += s.get_width() + sp
        return out

    # ─────────────────────────────────────────────────────────────────────────
    # Helper grafici "premium": glow morbido a forma d'icona + ombra soffusa.
    # Tecnica: silhouette colorata -> sfocatura via downscale+smoothscale (blur
    # gaussiano approssimato). Risultato cacheabile dal chiamante (vedi
    # MenuSystem._icon_fx), quindi a runtime resta un semplice blit.
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def tint_silhouette(icon: pygame.Surface, color) -> pygame.Surface:
        """Silhouette dell'icona riempita di 'color', preservando l'alpha."""
        s = icon.copy()
        s.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)   # rgb -> 0, alpha invariato
        s.fill((int(color[0]), int(color[1]), int(color[2]), 0), special_flags=pygame.BLEND_RGBA_ADD)
        return s

    @staticmethod
    def blur(surf: pygame.Surface, factor: float = 0.18) -> pygame.Surface:
        """Sfocatura economica: downscale -> upscale con smoothscale."""
        w, h = surf.get_size()
        sw, sh = max(1, int(w * factor)), max(1, int(h * factor))
        small = pygame.transform.smoothscale(surf, (sw, sh))
        return pygame.transform.smoothscale(small, (w, h))

    @classmethod
    def make_glow(cls, icon: pygame.Surface, color, grow: float = 0.42,
                  blur: float = 0.16) -> "pygame.Surface | None":
        """Alone morbido nella forma dell'icona (per il glow degli skin)."""
        iw, ih = icon.get_size()
        if iw == 0 or ih == 0:
            return None
        pad = int(max(iw, ih) * grow)
        base = pygame.Surface((iw + pad * 2, ih + pad * 2), pygame.SRCALPHA)
        base.blit(cls.tint_silhouette(icon, color), (pad, pad))
        return cls.blur(base, blur)

    @classmethod
    def make_shadow(cls, icon: pygame.Surface, blur: float = 0.22) -> "pygame.Surface | None":
        """Ombra soffusa nella forma dell'icona (per profondità)."""
        iw, ih = icon.get_size()
        if iw == 0 or ih == 0:
            return None
        pad = int(max(iw, ih) * 0.16)
        base = pygame.Surface((iw + pad * 2, ih + pad * 2), pygame.SRCALPHA)
        base.blit(cls.tint_silhouette(icon, (0, 0, 0)), (pad, pad))
        return cls.blur(base, blur)

    def font_size_btn(self) -> int:
        return int(self._font_cfg.get("size_btn", 28))

    def font_size_label(self) -> int:
        return int(self._font_cfg.get("size_label", 22))

    def font_size_scene(self) -> int:
        return int(self._font_cfg.get("size_scene", 24))

    def font_size_lock(self) -> int:
        return int(self._font_cfg.get("size_lock", 40))

    # ─────────────────────────────────────────────────────────────────────────
    # Effetti
    # ─────────────────────────────────────────────────────────────────────────

    def fx(self, key: str, default: Any = False) -> Any:
        """Restituisce un flag di effetto, cercando in _effects o alla radice."""
        val = self._effects.get(key)
        if val is None:
            val = self._data.get(key, default)
        return val


    def has_shadow(self) -> bool:
        return bool(self._effects.get("btn_shadow", False))

    def has_glow(self) -> bool:
        return bool(self._effects.get("btn_glow", False))

    def has_text_shadow(self) -> bool:
        return bool(self._effects.get("text_shadow", False))

    def has_pulse(self) -> bool:
        return bool(self._effects.get("pulse_hover", False))

    def has_flicker(self) -> bool:
        return bool(self._effects.get("flicker", False))

    def has_flashlight(self) -> bool:
        return bool(self._effects.get("flashlight_fx", False))

    def no_btn_bg(self) -> bool:
        """Restituisce True se non deve essere disegnato lo sfondo del bottone."""
        # Se è icons_only, di default non vogliamo background marroni/solidi
        # Ma diamo priorità alla flag esplicita nel layout
        val = self._layout.get("no_btn_bg")
        if val is not None:
            return bool(val)
        return self.is_icons_only()

    def has_inner_border(self) -> bool:
        return bool(self._layout.get("btn_inner_border", False))

    def has_sepia(self) -> bool:
        return bool(self._effects.get("sepia_overlay", False))

    def is_glass(self) -> bool:
        return bool(self._effects.get("glass_effect", False))

    def has_magnifier(self) -> bool:
        """Restituisce True se l'effetto lente d'ingrandimento è attivo."""
        return bool(self._effects.get("magnifier_fx", False))

    def magnifier_radius(self, sm) -> int:
        """Raggio della lente scalato."""
        return sm.scale_value(self._effects.get("magnifier_radius", 140))

    def magnifier_zoom(self) -> float:
        """Livello di zoom della lente (es: 1.5)."""
        return float(self._effects.get("magnifier_zoom", 1.4))

    def get_icon(self, action: str) -> pygame.Surface | None:
        """Restituisce l'icona associata a un'azione, se presente."""
        base_action = action.split(":")[0]
        map_alias = {
            "goto_levels": "levels",
            "goto_settings": "settings",
            "goto_main": "back",
            "quit": "quit",
            "play_scene": "play",
            "resume_game": "play",
            "do_new_game": "new_game",
            "confirm_new": "new_game",
            "set_music_volume": "audio",
            "set_sfx_volume": "audio",
            "toggle_lang": "language",
            "toggle_res": "fullscreen",
            "toggle_fs": "fullscreen",
            "quit_to_main": "back"
        }
        key = map_alias.get(base_action, base_action)
        return self._icons.get(key)

    def flashlight_pos(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        """Calcola la posizione della torcia con movimento automatico organico."""
        # Mix di sinusoidi a frequenze diverse per evitare loop troppo evidenti
        t = self._tick
        # Movimento ad 'otto' (Lissajous) asimmetrico
        off_x = math.sin(t * 0.7) * (screen_w * 0.28) + math.sin(t * 1.5) * 30
        off_y = math.cos(t * 0.45) * (screen_h * 0.22) + math.cos(t * 2.1) * 20
        
        # Jitter della torcia (tremolio della mano)
        jitter_x = math.sin(t * 30.0) * 4
        jitter_y = math.cos(t * 25.0) * 4
        
        return (screen_w // 2 + int(off_x + jitter_x), 
                screen_h // 2 + int(off_y + jitter_y))

    # ─────────────────────────────────────────────────────────────────────────
    # Tick interno per animazioni
    # ─────────────────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._tick += dt

    def pulse_scale(self) -> float:
        """Fattore di scala per effetto bounce sul hover (tema kids)."""
        if not self.has_pulse():
            return 1.0
        scale = float(self._effects.get("pulse_scale", 1.06))
        t = (math.sin(self._tick * 8.0) + 1.0) * 0.5  # 0..1
        return 1.0 + (scale - 1.0) * t

    def flicker_alpha_mod(self) -> float:
        """Modulazione alpha 0..1 per effetto flicker (tema horror)."""
        if not self.has_flicker():
            return 1.0
        
        # Flicker più nervoso e meno prevedibile
        intensity = float(self._effects.get("flicker_intensity", 0.1))
        speed = float(self._effects.get("flicker_speed", 20.0))
        t = self._tick * speed
        
        # Somma di 3 onde per jitter realistico
        noise = (math.sin(t) * 0.5 + 
                 math.sin(t * 2.3) * 0.3 + 
                 math.sin(t * 0.5) * 0.2)
        
        # Picchi di buio improvviso (dropouts)
        dropout = 0.0
        if math.sin(t * 0.1) > 0.98: # Drop ogni tanto
            dropout = 0.5
            
        return max(0.1, 1.0 - (noise * intensity) - dropout)

    # ─────────────────────────────────────────────────────────────────────────
    # Rendering helpers
    # ─────────────────────────────────────────────────────────────────────────

    def render_cached(self, font: pygame.font.Font, text: str, color) -> pygame.Surface:
        """font.render cacheato per (font, testo, colore). font.render e' una delle
        op piu' care su ARM/GPU-software ed era richiamata OGNI frame per ogni label
        di bottone/card (es. menu scene: ~8 render/frame). A riposo (testo/colore
        invariati) e' un cache-hit -> niente render per-frame. Pixel identici."""
        c = getattr(self, "_txt_render_cache", None)
        if c is None:
            c = self._txt_render_cache = {}
        key = (id(font), text, tuple(color) if not isinstance(color, (tuple, list)) else tuple(color))
        surf = c.get(key)
        if surf is None:
            if len(c) > 256:
                c.clear()
            surf = font.render(text, True, color)
            c[key] = surf
        return surf

    def android_btn_fill(self, locked: bool, hover_t: float):
        """Colore OPACO di fondo bottone su Android (no glassmorphism SRCALPHA).
        Esposto cosi' che il chip opaco dell'icona (menu_system) usi lo STESSO colore
        del fondo bottone: il riquadro icona resta invisibile sul fondo dello stesso
        colore, ma il blit dell'icona diventa opaco (molto piu' veloce su GPU mobile)."""
        if self.is_glass():
            if locked:
                return (22, 24, 30)
            return self.lerp_color((30, 34, 44), (54, 62, 82), round(hover_t, 2))
        if locked:
            return self.color3("btn_locked")
        return self.lerp_color(self.color3("btn_normal"), self.color3("btn_hover"), hover_t)

    def draw_btn_bg(self, screen: pygame.Surface, rect: pygame.Rect,
                    hovered: bool, locked: bool, hover_t: float = 0.0) -> None:
        """Disegna il background di un bottone con supporto per bordi e no-fill."""
        no_bg = self.no_btn_bg()
        if no_bg:
            return

        radius = self.border_radius()
        border_w = self.border_width()
        glass = self.is_glass()

        # Scala pulse per tema kids/horror se configurato
        if hover_t > 0 and self.has_pulse():
            s = 1.0 + (self.pulse_scale() - 1.0) * hover_t
            pw = int(rect.w * s)
            ph = int(rect.h * s)
            rect = pygame.Rect(
                rect.centerx - pw // 2,
                rect.centery - ph // 2,
                pw, ph
            )

        # Ombra (saltata su Android: Surface SRCALPHA per bottone/frame).
        # La Surface SRCALPHA resta semitrasparente (overlay vero, NON puo'
        # diventare opaca), ma alloc+draw.rect sono CACHATI per
        # (w, h, alpha, radius): a runtime resta solo un blit. Caching
        # visivamente-neutro (stessi pixel) -> sicuro su entrambe le piattaforme.
        if self.has_shadow() and not _ANDROID:
            off = self._effects.get("btn_shadow_offset", [3, 3])
            sc = self._effects.get("btn_shadow_color", [0, 0, 0, 120])
            # L'ombra può intensificarsi con l'hover
            alpha = int(sc[3] * (1.0 + hover_t * 0.3)) if len(sc) > 3 else 120
            sck = (rect.w, rect.h, alpha, radius, tuple(sc[:3]))
            shc = getattr(self, "_shadow_cache", None)
            if shc is None:
                shc = self._shadow_cache = {}
            shadow_surf = shc.get(sck)
            if shadow_surf is None:
                shadow_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                pygame.draw.rect(shadow_surf, (*sc[:3], alpha),
                                 (0, 0, rect.w, rect.h), border_radius=radius)
                if len(shc) > 48:
                    shc.pop(next(iter(shc)))
                shc[sck] = shadow_surf
            screen.blit(shadow_surf, (rect.x + off[0], rect.y + off[1]))

        # Glow (attivo su hover; saltato su Android). Stessa logica: overlay
        # SRCALPHA additivo che resta semitrasparente, ma alloc+draw.rect
        # cachati per (w, h, glow_alpha, radius) -> a runtime solo un blit.
        if not locked and hover_t > 0 and self.has_glow() and not _ANDROID:
            gc = self._effects.get("btn_glow_color", [255, 255, 255, 60])
            gr = int(self._effects.get("btn_glow_radius", 8))
            # Intensità basata su hover_t
            glow_alpha = int(gc[3] * hover_t) if len(gc) > 3 else int(60 * hover_t)
            gw, gh = rect.w + gr * 2, rect.h + gr * 2
            glk = (gw, gh, glow_alpha, radius + gr, tuple(gc[:3]))
            glc = getattr(self, "_glow_cache", None)
            if glc is None:
                glc = self._glow_cache = {}
            glow_surf = glc.get(glk)
            if glow_surf is None:
                glow_surf = pygame.Surface((gw, gh), pygame.SRCALPHA)
                pygame.draw.rect(glow_surf, (*gc[:3], glow_alpha),
                                 (0, 0, gw, gh), border_radius=radius + gr)
                if len(glc) > 48:
                    glc.pop(next(iter(glc)))
                glc[glk] = glow_surf
            screen.blit(glow_surf, (rect.x - gr, rect.y - gr))

        # Background principale (riempimento)
        if glass and _ANDROID:
            # Android: niente glassmorphism SRCALPHA. Il blit per-pixel-alpha della
            # surface vetro PER OGNI bottone OGNI frame era il costo dominante del
            # menu su GPU mobile (~10ms/bottone, come il cabinet dello slot). Fondo
            # OPACO solido a contrasto: leggibile, e un draw.rect diretto e' rapidissimo.
            pygame.draw.rect(screen, self.android_btn_fill(locked, hover_t), rect, border_radius=radius)
        elif glass:
            # Desktop: Effetto Glassmorfismo semi-trasparente con riflesso. La surface
            # SRCALPHA e' CACHATA per (dimensione, hover, locked, radius): a riposo
            # (hover_t=0) e' una sola entry per dimensione -> niente alloc+draw per frame.
            glass_base = self._effects.get("glass_color", [255, 255, 255, 40])
            glass_hover = self._effects.get("glass_hover", [255, 255, 255, 70])
            ht_q = round(hover_t, 2)
            bg = self.lerp_color(tuple(glass_base), tuple(glass_hover), ht_q)
            ck = (rect.w, rect.h, ht_q, bool(locked), radius)
            gc = getattr(self, "_glass_cache", None)
            if gc is None:
                gc = self._glass_cache = {}
            gsurf = gc.get(ck)
            if gsurf is None:
                gsurf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                pygame.draw.rect(gsurf, bg, (0, 0, rect.w, rect.h), border_radius=radius)
                if not locked:
                    refl_col = (255, 255, 255, int(50 * (1.0 + ht_q)))
                    pygame.draw.line(gsurf, refl_col, (5, 5), (rect.w // 2, 5), 1)
                    pygame.draw.line(gsurf, refl_col, (5, 5), (5, rect.h // 2), 1)
                if len(gc) > 48:
                    gc.pop(next(iter(gc)))
                gc[ck] = gsurf
            screen.blit(gsurf, rect)

        else:
            if locked:
                bg = self.color3("btn_locked")
            else:
                c_norm = self.color3("btn_normal")
                c_hov = self.color3("btn_hover")
                bg = self.lerp_color(c_norm, c_hov, hover_t)
            pygame.draw.rect(screen, bg, rect, border_radius=radius)

        # Bordo esterno
        if border_w > 0:
            if locked:
                bc = self.color3("btn_border_locked")
            else:
                bc_norm = self.color3("btn_border_normal")
                bc_hov = self.color3("btn_border_hover")
                bc = self.lerp_color(bc_norm, bc_hov, hover_t)
            
            if no_bg and bc == _FALLBACK_COLOR:
                 bc = self.color3("text_normal")

            pygame.draw.rect(screen, bc, rect, width=border_w, border_radius=radius)

        # Doppio bordo interno (tema mystery)
        if self.has_inner_border() and not locked:
            ib_off = int(self._layout.get("btn_inner_border_offset", 3))
            ib_col = self._layout.get("btn_inner_border_color", [80, 60, 25])
            inner = pygame.Rect(
                rect.x + ib_off, rect.y + ib_off,
                rect.w - ib_off * 2, rect.h - ib_off * 2
            )
            if inner.w > 4 and inner.h > 4:
                pygame.draw.rect(screen, tuple(ib_col), inner,
                                 width=1, border_radius=max(0, radius - ib_off))

    def draw_text(self, screen: pygame.Surface, text: str, font: pygame.font.Font,
                  rect: pygame.Rect, hovered: bool, locked: bool,
                  anchor: str = "center", hover_t: float = 0.0) -> None:
        """
        Renderizza testo con opzionale ombra e flicker.
        anchor: 'center' | 'midbottom' | 'left' | 'right'
        """
        if locked:
            col = self.color3("text_locked")
        else:
            c_norm = self.color3("text_normal")
            c_hov = self.color3("text_hover")
            col = self.lerp_color(c_norm, c_hov, hover_t)

        # Se il tema impone un allineamento (es. horror), sovrascriviamo l'anchor
        # se l'anchor passato è quello standard 'center'
        theme_align = self.layout_val("text_align", None)
        if theme_align and anchor == "center":
            anchor = theme_align

        # Flicker alpha (horror)
        alpha_mod = self.flicker_alpha_mod()

        # Helper per calcolare rect in base all'anchor
        def get_t_rect(surf, base_rect, anch):
            if anch == "center":
                return surf.get_rect(center=base_rect.center)
            elif anch == "midbottom":
                return surf.get_rect(midbottom=(base_rect.centerx, base_rect.bottom - 10))
            elif anch == "left":
                return surf.get_rect(midleft=(base_rect.left + 10, base_rect.centery))
            elif anch == "right":
                return surf.get_rect(midright=(base_rect.right - 10, base_rect.centery))
            return surf.get_rect(center=base_rect.center)

        # Ombra testo
        if self.has_text_shadow():
            off = self._effects.get("text_shadow_offset", [1, 1])
            sc = self._effects.get("text_shadow_color", [0, 0, 0, 120])
            sh_surf = self.render_cached(font, text, (sc[0], sc[1], sc[2]))
            if alpha_mod < 1.0:
                sh_surf.set_alpha(int(255 * alpha_mod * sc[3] / 255) if len(sc) > 3 else 255)

            sh_r = get_t_rect(sh_surf, rect, anchor)
            sh_r.x += off[0]
            sh_r.y += off[1]
            screen.blit(sh_surf, sh_r)

        # Testo principale
        t_surf = self.render_cached(font, text, col)
        if alpha_mod < 1.0:
            t_surf.set_alpha(int(255 * alpha_mod))

        t_r = get_t_rect(t_surf, rect, anchor)
        screen.blit(t_surf, t_r)

    def draw_sepia_overlay(self, screen: pygame.Surface,
                            rect: pygame.Rect) -> None:
        """Overlay seppia per il tema mystery."""
        if not self.has_sepia():
            return
        alpha = int(self._effects.get("sepia_alpha", 30))
        ov = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        ov.fill((120, 80, 20, alpha))
        screen.blit(ov, rect)


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_theme_data(theme_json_path: Path) -> dict:
    """Carica un theme.json (con validazione soft, non bloccante)."""
    try:
        with open(theme_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("MenuTheme: impossibile caricare '%s': %s", theme_json_path, e)
        return {}
    # Validazione non bloccante: logga eventuali incongruenze ma non interrompe.
    try:
        from engine.json_validator import validate
        validate(data, "theme", source_path=str(theme_json_path))
    except Exception:
        pass
    return data


def load_theme_for_game(game_id: str) -> MenuTheme:
    """
    Carica il tema del gioco con ereditarietà dal tema globale dell'engine.
    Questo garantisce che nuove chiavi aggiunte al tema globale siano presenti
    anche se il file del gioco è vecchio (harvested precedentemente).
    """
    # 1. Carica prima il default come base assoluta
    default_path = get_resource_path("engine", "assets", "themes", "default", "theme.json")
    base_data = _load_theme_data(default_path)

    # 2. Determina il tema richiesto dal gioco
    game_theme_path = get_resource_path("games", game_id, "ui_theme", "theme.json")
    game_data = {}
    if game_theme_path.exists():
        game_data = _load_theme_data(game_theme_path)
    
    theme_id = game_data.get("id", "default")
    
    # 3. Carica il tema globale corrispondente (se diverso da default)
    final_data = base_data.copy()
    if theme_id != "default":
        global_path = get_resource_path("engine", "assets", "themes", theme_id, "theme.json")
        if global_path.exists():
            global_data = _load_theme_data(global_path)
            # Merge grossolano (radice)
            final_data.update(global_data)
            # Merge specifico per sezioni critiche
            for section in ["colors", "layout", "effects", "font", "views"]:
                if section in global_data:
                    if section not in final_data: final_data[section] = {}
                    final_data[section].update(global_data[section])

    # 4. Sovrapponi i dati specifici del gioco (Override finale)
    if game_data:
        final_data.update(game_data)
        for section in ["colors", "layout", "effects", "font", "views"]:
            if section in game_data:
                if section not in final_data: final_data[section] = {}
                final_data[section].update(game_data[section])

    logger.info("MenuTheme: caricato tema '%s' per gioco '%s' con ereditarietà.", theme_id, game_id)
    return MenuTheme(final_data, game_id=game_id)
