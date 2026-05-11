"""
editor/core/io.py

Funzioni pure per I/O dati: JSON, catalogo, scene, discovery giochi/livelli.
Nessuna dipendenza da pygame o stato dell'editor.
"""

import json
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] _save_json failed for {path}: {e}")
        return False


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


def _load_scene_data(scene_path: Path) -> dict:
    """Legge scene.json dalla directory della scena. Non modifica stato editor."""
    d = _load_json(scene_path / "scene.json")
    if not d:
        d = {"id": scene_path.name, "background": "background.jpg",
             "background_scale": 1.0, "objects": [], "effects": [],
             "flashlight": False, "flashlight_radius": 150.0}
    d.setdefault("objects", [])
    d.setdefault("effects", [])
    d.setdefault("music", [])
    d.setdefault("flashlight", False)
    d.setdefault("flashlight_radius", 150.0)
    return d


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
