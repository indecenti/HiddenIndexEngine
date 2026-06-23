"""
editor/core/io.py

Funzioni pure per I/O dati: JSON, catalogo, scene, discovery giochi/livelli.
Nessuna dipendenza da pygame o stato dell'editor.
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        # File presente ma illeggibile/corrotto: lo segnaliamo (a differenza del
        # file mancante, che e' un caso normale). I chiamanti che gestiscono dati
        # critici (scene) devono distinguere i due casi per non perderli.
        logging.warning("_load_json: file presente ma non parsabile %s: %s", path, e)
        return {}


def _save_json(path: Path, data: dict) -> bool:
    """
    Scrittura JSON crash-safe: delega a engine.utils.safe_write_json che
    scrive su tmp + os.replace atomico + fsync. In caso di crash a metà
    write, il file originale resta intatto (non più corruzione silenziosa).
    """
    from engine.utils import safe_write_json
    ok = safe_write_json(path, data, indent=2, ensure_ascii=False)
    if not ok:
        return False

    # Invalida cache se salviamo una scena
    if path.name == "scene.json":
        p_res = path.parent.resolve()
        p_str = str(p_res)

        # Invalida RAM
        if str(path.parent) in _SCENE_DATA_CACHE:
            _SCENE_DATA_CACHE.pop(str(path.parent))

        # Invalida RAM e DISCO delle miniature
        thumb_dir = _CACHE_DIR / "thumbs"
        for size in [(86, 48), (64, 36)]:
            t_hash = hashlib.md5(f"{p_str}_{size[0]}x{size[1]}".encode()).hexdigest()
            _THUMB_CACHE.pop(t_hash, None)
            c_p = thumb_dir / f"{t_hash}.png"
            if c_p.exists():
                try:
                    c_p.unlink()
                except OSError as e:
                    logging.debug(f"_save_json: thumbnail cache invalidate failed for {c_p}: {e}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# CATALOGO E SCENE
# ─────────────────────────────────────────────────────────────────────────────

def _load_catalog(game_id: str) -> list:
    """Load merged catalog: global + game-specific objects."""
    try:
        from engine.catalog_manager import load_catalog as engine_load_catalog
        catalog_dict = engine_load_catalog(game_id)
        return catalog_dict.get("objects", [])
    except Exception:
        # Fallback if catalog_manager fails
        return []


def _load_effects_catalog() -> list:
    """Carica il catalogo effetti da engine/data/effects_catalog.json."""
    try:
        import json
        from pathlib import Path as _Path
        p = _Path("engine") / "data" / "effects_catalog.json"
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f).get("effects", [])
    except Exception:
        pass
    return []


_SCENE_DATA_CACHE: dict[str, dict] = {}

def _load_scene_data(scene_path: Path) -> dict:
    """Legge scene.json dalla directory della scena con caching interno."""
    # Usiamo str(path) come chiave per evitare il costo di resolve() ad ogni chiamata
    path_key = str(scene_path)
    if path_key in _SCENE_DATA_CACHE:
        return _SCENE_DATA_CACHE[path_key]
        
    scene_file = scene_path / "scene.json"
    d = _load_json(scene_file)
    if not d:
        # Distinzione mancante vs corrotto: se il file esiste ed e' non vuoto ma
        # non e' stato parsato, NON e' una scena nuova bensi' corrotta. Ne salviamo
        # una copia (.corrupt) prima che un eventuale salvataggio la sovrascriva,
        # evitando perdita di dati irreversibile.
        try:
            if scene_file.exists() and scene_file.stat().st_size > 2:
                backup = scene_path / "scene.json.corrupt"
                if not backup.exists():
                    import shutil
                    shutil.copy2(scene_file, backup)
                logging.error(
                    "scene.json corrotto: %s — backup preservato in %s", scene_file, backup
                )
        except Exception as e:
            logging.error("Gestione scene.json corrotto fallita per %s: %s", scene_file, e)
        d = {"id": scene_path.name, "background": "background.jpg",
             "background_scale": 1.0, "objects": [], "effects": [],
             "flashlight": False, "flashlight_radius": 150.0}
    d.setdefault("objects", [])
    d.setdefault("effects", [])
    d.setdefault("music", [])
    d.setdefault("flashlight", False)
    d.setdefault("flashlight_radius", 150.0)
    
    _SCENE_DATA_CACHE[path_key] = d
    return d


_THUMB_CACHE: dict[str, any] = {}
_CACHE_DIR = Path(".editor_cache")

def _get_scene_thumbnail(scene_path: Path, size: tuple[int, int]) -> Optional[any]:
    """
    Recupera una Surface di anteprima per la scena con persistenza su disco.
    """
    import pygame
    path_str = str(scene_path.resolve())
    t_hash = hashlib.md5(f"{path_str}_{size[0]}x{size[1]}".encode()).hexdigest()
    
    # 1. Cache in RAM (Velocissima)
    if t_hash in _THUMB_CACHE:
        return _THUMB_CACHE[t_hash]
        
    # 2. Cache su DISCO (Persistente)
    thumb_dir = _CACHE_DIR / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    cache_path = thumb_dir / f"{t_hash}.png"
    
    if cache_path.exists():
        try:
            surf = pygame.image.load(str(cache_path)).convert_alpha()
            _THUMB_CACHE[t_hash] = surf
            return surf
        except Exception: pass

    # 3. Generazione (Lenta, solo la prima volta)
    try:
        sd = _load_scene_data(scene_path)
        bg_file = sd.get("background", "")
        if not bg_file: return None
        
        full_path = scene_path / bg_file
        if not full_path.exists(): return None
        
        raw = pygame.image.load(str(full_path)).convert()
        tw, th = size
        iw, ih = raw.get_size()
        scale = max(tw/iw, th/ih)
        nw, nh = int(iw * scale), int(ih * scale)
        
        if iw > 2000 or ih > 2000:
            scaled = pygame.transform.scale(raw, (nw, nh))
        else:
            scaled = pygame.transform.smoothscale(raw, (nw, nh))
            
        final = pygame.Surface(size, pygame.SRCALPHA)
        final.blit(scaled, ((tw-nw)//2, (th-nh)//2))
        
        # Salva su disco per la prossima sessione
        pygame.image.save(final, str(cache_path))
        
        _THUMB_CACHE[t_hash] = final
        return final
    except Exception as e:
        logging.debug(f"[IO] Thumbnail generation failed for {scene_path}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

def _discover_games(base: Path) -> list:
    gdir = base / "games"
    if not gdir.exists():
        return []
    return sorted(d.name for d in gdir.iterdir()
                  if d.is_dir() and not d.name.startswith("."))


def _discover_levels(game_path: Path) -> list:
    ldir = game_path / "levels"
    if not ldir.exists():
        return []
        
    game_cfg = _load_json(game_path / "game_config.json")
    levels_cfg = game_cfg.get("levels", [])
    order_map_lvl = {lvl_id: i for i, lvl_id in enumerate(levels_cfg)}
    
    registered_levels = []
    orphan_levels = []
    
    for ld in ldir.iterdir():
        if not ld.is_dir():
            continue
        cfg_p = ld / "level_config.json"
        cfg = _load_json(cfg_p)
        
        # Troviamo tutte le sottocartelle (scene)
        found_dirs = [s for s in ld.iterdir() if s.is_dir()]
        
        # Ordiniamo le scene in base alla lista in level_config.json se presente
        scenes_cfg = cfg.get("scenes", [])
        order_map = {s.get("id"): i for i, s in enumerate(scenes_cfg)}
        
        # Separiamo scene registrate da scene "orfane" (nuove o non in config)
        registered = []
        orphans = []
        for sdir in found_dirs:
            if sdir.name in order_map:
                registered.append(sdir)
            else:
                orphans.append(sdir)
        
        # Ordiniamo le registrate in base alla posizione in config
        registered.sort(key=lambda x: order_map[x.name])
        # Le orfane le mettiamo in fondo (alfabeticamente)
        orphans.sort(key=lambda x: x.name)
        
        final_scenes = registered + orphans
        
        level_data = {"id": ld.name, "path": ld, "cfg": cfg, "scenes": final_scenes}
        if ld.name in order_map_lvl:
            registered_levels.append(level_data)
        else:
            orphan_levels.append(level_data)

    # Ordiniamo i registrati in base all'ordine nel file config
    registered_levels.sort(key=lambda x: order_map_lvl[x["id"]])
    # Le orfane in fondo alfabeticamente
    orphan_levels.sort(key=lambda x: x["id"])
    
    return registered_levels + orphan_levels


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY OGGETTI
# ─────────────────────────────────────────────────────────────────────────────

def _default_effect(effect_id: str, effect_type: str, x: float, y: float,
                    radius: float = 55, color=None, intensity: float = 0.85,
                    pulse_period: float = 2.0, pulse_min: float = 0.1,
                    phase: float = 0.0, text_key: str = "", trigger: str = "start_scene",
                    width: int = 300, height: int = 180, layer: str = "overlay",
                    layer_z: int = 40) -> dict:
    """Factory per un nuovo effetto visivo nella scena."""
    d = {
        "effect_id": effect_id,
        "type": effect_type,
        "x": round(x),
        "y": round(y),
        "radius": radius,
        "color": color if color is not None else [255, 215, 60],
        "intensity": round(intensity, 2),
        "pulse_period": round(pulse_period, 2),
        "pulse_min": round(pulse_min, 2),
        "phase": round(phase, 2),
        "layer": layer,
        "layer_z": layer_z,
    }
    if effect_type == "bubble_tip":
        d.update({
            "text_key":   text_key or "NEW_TIP",
            "trigger":    trigger,
            "width":      width,
            "height":     height,
            "alpha":      255,
            "font_size":  22,
            "font_color": [40, 40, 40]
        })
    return d


def _default_obj(catalog_id, x, y, detection, radius=30, width=60, height=60,
                 layer="objects_mid", hint_delay=30, is_goal=True) -> dict:
    obj = {
        "catalog_id": catalog_id, "x": round(x), "y": round(y),
        "detection_type": detection, "layer": layer,
        "always_show": False, "is_goal": is_goal,
        "hint_delay": hint_delay
    }
    if detection == "circle":
        obj["radius"] = radius
        obj["width"]  = radius * 2
        obj["height"] = radius * 2
    elif detection == "rect":
        obj["width"]  = width
        obj["height"] = height
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# FILE DIALOG
# ─────────────────────────────────────────────────────────────────────────────

def _file_dialog(title="Seleziona file", filetypes=None, initialdir=None):
    """Minimal file dialog via tkinter stdlib (no extra dependencies)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.focus_force()
        root.wm_attributes("-topmost", True)

        kw = {"title": title, "parent": root}
        if filetypes:
            kw["filetypes"] = filetypes
        if initialdir:
            kw["initialdir"] = str(initialdir)

        path = filedialog.askopenfilename(**kw)
        root.destroy()
        return Path(path) if path else None
    except Exception:
        return None
