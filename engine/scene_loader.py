"""
engine/scene_loader.py
Caricamento e parsing delle scene (file scene.json).
"""

import os
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from pathlib import Path

import pygame
import numpy as np

from engine.utils import get_resource_path, get_logger
from engine.json_validator import load_and_validate

log = get_logger(__name__)

@dataclass
class SceneObject:
    """Rappresentazione di un oggetto interattivo nella scena."""
    instance_id: str
    catalog_id: str
    label_key: str
    icon_path: str
    x: float
    y: float
    detection_type: str
    radius: float = 0.0
    width: float = 0.0
    height: float = 0.0
    mask_path: str = ""
    mask_scale: float = 1.0
    mask_scale_x: float = 1.0
    mask_scale_y: float = 1.0
    layer: str = "objects_mid"
    layer_z: int = 20
    always_show: bool = False
    is_goal: bool = True
    rotation: float = 0.0
    flip_x: bool = False
    flip_y: bool = False
    alpha: int = 255
    grayscale: bool = False
    grayscale_factor: float = 1.0
    color_filter: tuple = (255, 255, 255)
    corners: list[list[int]] = field(default_factory=lambda: [[0,0], [0,0], [0,0], [0,0]])
    scale: float = 1.0
    minigame_trigger: Optional[dict] = None

    icon_surface: Optional[pygame.Surface] = field(default=None, repr=False)
    mask_surface: Optional[pygame.Surface] = field(default=None, repr=False)
    found: bool = False
    _cached_surface: Optional[pygame.Surface] = field(default=None, repr=False)
    _cached_params: Optional[tuple] = field(default=None, repr=False)

LAYER_Z = {
    "background": 0, 
    "objects_low": 10, "objects_back": 10, 
    "objects_mid": 20, 
    "objects_high": 30, "objects_front": 30, 
    "overlay": 40,
    "ui_overlay": 100
}

class SceneLoader:
    def __init__(self, game_id: str, catalog: dict) -> None:
        self._game_id = game_id
        self._catalog = {obj["id"]: obj for obj in catalog.get("objects", [])}
        self._custom_layer_z = {}
        self._preloaded_scene = None
        self._preload_lock = threading.Lock()

    def _get_layer_z(self, layer_name: str) -> int:
        return LAYER_Z.get(layer_name, self._custom_layer_z.get(layer_name, 20))

    def load_scene(self, level_id: str, scene_id: str) -> 'SceneData':
        """Carica una scena, usando quella precaricata se disponibile."""
        with self._preload_lock:
            if self._preloaded_scene and self._preloaded_scene.id == scene_id:
                log.info(f"[LOADER] Uso scena precaricata: {scene_id}")
                data = self._preloaded_scene
                self._preloaded_scene = None
                return data

        return self._load_scene_internal(level_id, scene_id)

    def is_preload_ready(self, scene_id: str) -> bool:
        """Controlla se la scena specificata è già stata caricata in background."""
        with self._preload_lock:
            return self._preloaded_scene is not None and self._preloaded_scene.id == scene_id

    def start_preload(self, level_id: str, scene_id: str) -> None:
        """Avvia il caricamento asincrono di una scena."""
        def _thread_load():
            try:
                data = self._load_scene_internal(level_id, scene_id)
                with self._preload_lock:
                    self._preloaded_scene = data
                log.info(f"[LOADER] Preload completato per: {scene_id}")
            except Exception as e:
                log.error(f"[LOADER] Errore durante il preload di {scene_id}: {e}")

        thread = threading.Thread(target=_thread_load, daemon=True)
        thread.start()

    def _load_scene_internal(self, level_id: str, scene_id: str) -> 'SceneData':
        scene_dir = get_resource_path("games", self._game_id, "levels", level_id, scene_id)
        json_path = os.path.join(scene_dir, "scene.json")
        data = load_and_validate(json_path, "scene")
        def _to_bool(v):
            if isinstance(v, bool): return v
            if isinstance(v, str): return v.lower() in ["true", "1", "yes"]
            return bool(v)

        # Logica Random Layer Mode (NEW)
        # Se attiva, carichiamo solo uno dei tre layer principali, scelto a random.
        rand_layer_active = _to_bool(data.get("random_layer_selection", False))
        raw_objs = data["objects"]
        if rand_layer_active:
            import random
            chosen_layer = random.choice(["objects_low", "objects_mid", "objects_high"])
            log.info(f"[LOADER] Random Layer Mode ATTIVA. Scelto layer: {chosen_layer}")
            # Filtra solo gli oggetti appartenenti ai layer 'intercambiabili', mantiene sempre l'overlay o altri layer fissi
            raw_objs = [o for o in raw_objs if o.get("layer", "objects_mid") == chosen_layer or not o.get("layer", "").startswith("objects_")]

        objs = self._select_objects(raw_objs, len(raw_objs), scene_dir)
        
        # Caricamento Effetti (Bubble tips, ambiental, ecc)
        raw_effects = data.get("effects", [])
        effects = []
        for fx_raw in raw_effects:
            class Effect: pass
            fx = Effect()
            # Valori di default robusti per prevenire AttributeError nel renderer
            fx.type = fx_raw.get("type", "glint")
            fx.x = float(fx_raw.get("x", 0))
            fx.y = float(fx_raw.get("y", 0))
            fx.radius = float(fx_raw.get("radius", 50))
            fx.color = tuple(fx_raw.get("color", (255, 255, 255)))
            fx.intensity = float(fx_raw.get("intensity", 1.0))
            fx.layer_z = int(fx_raw.get("layer_z", 40))
            fx.phase = float(fx_raw.get("phase", 0.0))
            fx.pulse_min = float(fx_raw.get("pulse_min", 0.1))
            
            for k, v in fx_raw.items():
                setattr(fx, k, v)
            
            # Inizializza stati runtime garantendo coerenza
            setattr(fx, "_visible", False)
            setattr(fx, "_chars_visible", 0.0)
            setattr(fx, "_t_accum", 0.0)
            if not hasattr(fx, "trigger"): setattr(fx, "trigger", "manual")
            effects.append(fx)

        # Logica di Rotazione Automatica (Shuffle Obiettivi)
        auto_random = _to_bool(data.get("auto_random_finds", False))
        # Se auto_random è attivo, il numero di goals viene definito da num_random_finds.
        # Se non presente, di default usiamo tutti gli oggetti disponibili nel pool.
        num_goals = int(data.get("num_random_finds", len(objs)))

        if auto_random:
            import random
            log.info(f"[LOADER] Rotazione automatica: seleziono {num_goals} obiettivi.")
            
            # Step 1: Resettiamo tutti gli oggetti (nessuno è goal inizialmente)
            for o in objs: o.is_goal = False
            
            # Step 2: Identifichiamo i fissi e i variabili
            fixed = [o for o in objs if o.always_show]
            pool  = [o for o in objs if not o.always_show]
            
            # Step 3: I fissi sono sempre goal (entro il limite num_goals)
            final_goals = fixed[:num_goals]
            for o in final_goals: o.is_goal = True
            
            # Step 4: Peschiamo il rimanente dal pool casualmente
            remaining_slots = num_goals - len(final_goals)
            if remaining_slots > 0 and pool:
                random.shuffle(pool)
                extra = pool[:remaining_slots]
                for o in extra: o.is_goal = True
            
            log.info(f"[LOADER] Shuffle completato: {len(final_goals)} fissi, {max(0, remaining_slots)} casuali.")

        bg_path = os.path.join(scene_dir, data["background"])
        
        # Saltiamo il caricamento come Surface se è un video (verrà gestito dal core)
        is_vid = bg_path.lower().endswith((".mp4", ".mov", ".mkv"))
        bg_surf = None
        if os.path.exists(bg_path) and not is_vid:
            bg_surf = pygame.image.load(bg_path).convert()

        from engine.scene_loader import SceneData
        return SceneData(
            id=scene_id, name_key=data.get("name_key", scene_id),
            background_path=bg_path, background_scale=float(data.get("background_scale", 1.0)),
            objects=objs, pool_size=len(objs),
            background_surface=bg_surf, preload_ready=True,
            music=data.get("music", []),
            effects=effects,
            flashlight=_to_bool(data.get("flashlight", False)),
            flashlight_radius=float(data.get("flashlight_radius", 150.0))
        )

    def _select_objects(self, raw_list: list, count: int, scene_dir: str) -> List[SceneObject]:
        def _to_bool(v):
            if isinstance(v, bool): return v
            if isinstance(v, str): return v.lower() in ["true", "1", "yes"]
            return bool(v)

        result = []
        counts = {}
        gs_count = 0
        
        for raw in raw_list:
            cid = raw["catalog_id"]
            cat = self._catalog.get(cid, {})
            counts[cid] = counts.get(cid, 0) + 1
            iid = cid if counts[cid] == 1 else f"{cid}_{counts[cid]}"
            
            gs = _to_bool(raw.get("grayscale", False))
            if gs: gs_count += 1
            
            # Caricamento superficie icona con fallback su assets engine
            icon_path = cat.get("icon", "")
            icon_surf = None
            if icon_path:
                # 1. Prova in locale al gioco
                local_path = get_resource_path("games", self._game_id, icon_path)
                # 2. Prova in engine/assets (globali)
                engine_path = get_resource_path("engine", "assets", icon_path)
                
                final_path = local_path if local_path.exists() else engine_path
                
                if final_path.exists():
                    try:
                        icon_surf = pygame.image.load(str(final_path)).convert_alpha()
                    except Exception as e:
                        log.error(f"Errore caricamento icona {final_path}: {e}")
                else:
                    log.warning(f"Asset icona mancante: {icon_path} (cercato in local e engine)")
            
            obj = SceneObject(
                instance_id=iid, catalog_id=cid, label_key=cat.get("label_key", cid),
                icon_path=str(icon_path),
                x=float(raw["x"]), y=float(raw["y"]),
                detection_type=raw.get("detection_type", "circle"),
                radius=float(raw.get("radius", 30)),
                width=float(raw.get("width", 0)), height=float(raw.get("height", 0)),
                layer=raw.get("layer", "objects_mid"),
                layer_z=self._get_layer_z(raw.get("layer", "objects_mid")),
                is_goal=_to_bool(raw.get("is_goal", True)),
                always_show=_to_bool(raw.get("always_show", False)),
                rotation=float(raw.get("rotation", 0.0)),
                flip_x=_to_bool(raw.get("flip_x", False)), 
                flip_y=_to_bool(raw.get("flip_y", False)),
                alpha=int(raw.get("alpha", 255)),
                grayscale=gs,
                grayscale_factor=float(raw.get("grayscale_factor", 1.0)),
                color_filter=tuple(raw.get("color_filter", (255, 255, 255))),
                corners=raw.get("corners", [[0,0], [0,0], [0,0], [0,0]]),
                scale=float(raw.get("scale", 1.0)),
                minigame_trigger=raw.get("minigame_trigger"),
                icon_surface=icon_surf
            )
            result.append(obj)
            
        if gs_count > 0:
            log.info(f"[LOADER] Caricati {gs_count} oggetti con filtro Bianco e Nero attivo.")
        
        # Ordinamento critico per Z-index affinché il rendering in-game sia corretto
        result.sort(key=lambda o: o.layer_z)
        return result

@dataclass
class SceneData:
    id: str
    name_key: str
    background_path: str
    background_scale: float
    objects: list[SceneObject]
    pool_size: int
    background_surface: Optional[pygame.Surface] = None
    preload_ready: bool = False
    music: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    flashlight: bool = False
    flashlight_radius: float = 150.0
