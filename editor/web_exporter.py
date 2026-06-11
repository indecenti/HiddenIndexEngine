"""
editor/web_exporter.py

Esporta un gioco HiddenEngine in un sito statico HTML/JS/CSS pronto alla
pubblicazione online.

Principio guida: le coordinate degli oggetti devono rispecchiare PERFETTAMENTE
l'editor/engine Python. Per questo il manifest replica 1:1 la costruzione degli
oggetti di engine/scene_loader.py (stessi default, nessun default di catalogo
applicato a runtime) e il runtime JS replica le trasformazioni di
scaling_manager.py / core.py / click_detector.py.

Uso:
    python -m editor.web_exporter LineVenture
    python -m editor.web_exporter LineVenture --out build_web/LineVenture
"""

from __future__ import annotations

import json
import shutil
import zipfile
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Versione del runtime web (incrementare a modifiche significative di runtime.js).
RUNTIME_VERSION = "1.0.0"

from PIL import Image

from engine.catalog_manager import load_catalog, get_object_by_id
from editor.web_rules import engine_rules

# SFX globali usati dal loop hidden-object (engine/core.py). Mappa chiave logica
# -> path sorgente relativo alla root del progetto.
ENGINE_SFX = {
    "found": "engine/assets/sounds/bling1.mp3",
    "complete": "engine/assets/sounds/victory.mp3",
    "miss": "engine/assets/sounds/error4.mp3",
    "click": "engine/assets/sounds/click_Low.wav",
    "levelup": "engine/assets/sounds/level_up.mp3",
}

_FFMPEG = shutil.which("ffmpeg")

# Dipendenze di asset tra minigiochi (alcuni riusano risorse di altri).
# arcade_eleven carica le carte e i suoni dalla cartella 'tower'.
# spot_differences pesca oggetti random da un pool per-stile (cartoon/real/lineart).
# Il runtime richiede solo >=25 oggetti per stile (vedi runtime/minigames/spot_differences.js)
# e ne disegna una manciata per round con reshuffle: esportare l'INTERO catalogo (~2760
# immagini, centinaia di MB) e' spreco. Limitiamo il pool per stile mantenendo varieta'.
SPOT_MAX_PER_STYLE = 120

MINIGAME_ASSET_DEPS = {
    "arcade_eleven": ["tower"],
    "centipede": ["centipede"],
    "minipong": ["minipong"],
    "slot_classic": ["slot_classic"],
    "spot_differences": ["spot_differences"],
    "sudoku": ["sudoku"],
    "tower": ["tower"],
}

# Replica di engine/scene_loader.py:LAYER_Z
LAYER_Z = {
    "background": 0,
    "objects_low": 10, "objects_back": 10,
    "objects_mid": 20,
    "objects_high": 30, "objects_front": 30,
    "overlay": 40,
    "ui_overlay": 100,
}

# Ottimizzazione immagini web. Gli sfondi sono fotografici/illustrativi: WebP lossy
# li riduce di ~90% rispetto al PNG. La risoluzione viene cappata: e' sicuro perche' le
# coordinate restano in bg-space tramite bg_w/bg_h ORIGINALI nel manifest (lo sfondo viene
# disegnato nel rect di bg-space, vedi runtime ScalingManager). Le icone restano a piena
# risoluzione (nitidezza per l'hidden-object) ma in WebP lossless (piu' piccolo del PNG,
# zero perdita). objCenterAndSize usa width/height/radius dal manifest, mai la dimensione
# naturale dell'icona: anche un eventuale downscale icone sarebbe coordinate-safe.
BG_MAX_DIM = 1920
BG_WEBP_QUALITY = 82

TEMPLATE_DIR = Path(__file__).parent / "web_template"
RUNTIME_DIR = TEMPLATE_DIR / "runtime"
# Ordine deterministico dei moduli base del runtime (i minigiochi vengono
# aggiunti in mezzo, solo quelli effettivamente usati dal gioco).
RUNTIME_CORE_FILES = ["core.js", "game.js"]
# Skin dei menu (overlay DOM/CSS), inclusi dopo il core e prima dei minigiochi.
RUNTIME_SKIN_FILES = ["skins/shaderbg.js", "skins/base.js", "skins/horror.js", "skins/kids.js",
                      "skins/cyber_neon.js", "skins/mystery.js"]
DEFAULT_CORNERS = [[0, 0], [0, 0], [0, 0], [0, 0]]


def _bundle_runtime(output_path: Path, minigame_ids: set[str]) -> None:
    """Concatena i moduli sorgente di web_template/runtime/ in un unico runtime.js.

    Include core + game + SOLO i minigiochi richiesti (minigames/{id}.js) + bootstrap.
    Gli script sono classici (niente ES module): la concatenazione produce lo stesso
    scope globale del vecchio monolite e continua a funzionare da file:// senza server.
    Ogni minigioco si auto-registra in window.MINIGAME_CLASSES.
    """
    parts: list[str] = [
        "// runtime.js — GENERATO da web_exporter._bundle_runtime (NON modificare a mano).\n"
        "// Sorgenti: editor/web_template/runtime/{core,game,minigames/*,bootstrap}.js\n",
    ]
    for fname in RUNTIME_CORE_FILES:
        parts.append((RUNTIME_DIR / fname).read_text(encoding="utf-8"))
    for fname in RUNTIME_SKIN_FILES:
        sp = RUNTIME_DIR / fname
        if sp.exists():
            parts.append(sp.read_text(encoding="utf-8"))
    for mid in sorted(minigame_ids):
        mg_path = RUNTIME_DIR / "minigames" / f"{mid}.js"
        if mg_path.exists():
            parts.append(mg_path.read_text(encoding="utf-8"))
        else:
            print(f"  [WARN] runtime minigioco mancante (non in bundle): {mid}.js")
    parts.append((RUNTIME_DIR / "bootstrap.js").read_text(encoding="utf-8"))
    output_path.write_text("\n".join(parts), encoding="utf-8", newline="")


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _resolve_icon_src(base: Path, game_id: str, icon_rel: str) -> Path | None:
    """Replica la risoluzione di scene_loader: prima il gioco, poi engine/assets."""
    if not icon_rel:
        return None
    local = base / "games" / game_id / icon_rel
    if local.exists():
        return local
    engine = base / "engine" / "assets" / icon_rel
    if engine.exists():
        return engine
    return None


def _build_object(raw: dict, instance_id: str, catalog) -> dict:
    """Costruisce un oggetto manifest mirroring scene_loader._select_objects."""
    cid = raw["catalog_id"]
    cat = get_object_by_id(catalog, cid) or {}

    layer = raw.get("layer", "objects_mid")
    raw_lz = raw.get("layer_z")
    layer_z = int(raw_lz) if raw_lz is not None else LAYER_Z.get(layer, 20)

    return {
        "instance_id": instance_id,
        "catalog_id": cid,
        "label_key": cat.get("label_key", cid),
        "icon": cat.get("icon", ""),  # path web riscritto piu' avanti
        "_icon_rel": cat.get("icon", ""),  # path catalogo originale (interno)
        "x": float(raw["x"]),
        "y": float(raw["y"]),
        "detection_type": raw.get("detection_type", "circle"),
        "radius": float(raw.get("radius", 30)),
        "hint_delay": float(raw.get("hint_delay", 30)),
        "width": float(raw.get("width", 0)),
        "height": float(raw.get("height", 0)),
        "layer": layer,
        "layer_z": layer_z,
        "is_goal": _to_bool(raw.get("is_goal", True)),
        "always_show": _to_bool(raw.get("always_show", False)),
        "rotation": float(raw.get("rotation", 0.0)),
        "flip_x": _to_bool(raw.get("flip_x", False)),
        "flip_y": _to_bool(raw.get("flip_y", False)),
        "alpha": int(raw.get("alpha", 255)),
        "grayscale": _to_bool(raw.get("grayscale", False)),
        "grayscale_factor": float(raw.get("grayscale_factor", 1.0)),
        "color_filter": list(raw.get("color_filter", [255, 255, 255])),
        "corners": raw.get("corners", DEFAULT_CORNERS),
        "scale": float(raw.get("scale", 1.0)),
        "minigame_trigger": raw.get("minigame_trigger"),
    }


_VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm")


def _is_video(name: str) -> bool:
    return str(name).lower().endswith(_VIDEO_EXT)


def _ffprobe_size(src: Path) -> tuple[int, int]:
    """Dimensioni (w, h) di un video via ffprobe. Fallback 1280x720."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 1280, 720
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(src)],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        w, h = out.split("x")[:2]
        return int(w), int(h)
    except Exception as e:
        print(f"  [WARN] ffprobe fallito per {src.name}: {e}")
        return 1280, 720


def _video_thumb(src: Path, dst: Path) -> bool:
    """Estrae un fotogramma del video come anteprima JPEG (480px)."""
    if not _FFMPEG:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [_FFMPEG, "-y", "-loglevel", "error", "-ss", "0.5", "-i", str(src),
             "-vframes", "1", "-vf", "scale=480:-1", str(dst)],
            check=True, capture_output=True,
        )
        return dst.exists()
    except Exception as e:
        print(f"  [WARN] thumbnail video fallita per {src.name}: {e}")
        return False


def _transcode_audio(src: Path, dst: Path, *, music: bool) -> bool:
    """Transcodifica un file audio in MP3 compresso per il web tramite ffmpeg.

    music=True  -> 112 kbps stereo (loop musica di scena/menu)
    music=False -> 96 kbps mono   (SFX brevi a bassa latenza)

    Se ffmpeg non e' disponibile copia il file originale (nessuna compressione).
    Ritorna True in caso di successo.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not _FFMPEG:
        # Fallback: copia raw mantenendo l'estensione originale
        raw = dst.with_suffix(src.suffix)
        shutil.copy2(src, raw)
        return True
    args = [_FFMPEG, "-y", "-loglevel", "error", "-i", str(src)]
    if music:
        args += ["-c:a", "libmp3lame", "-b:a", "112k", "-ac", "2"]
    else:
        args += ["-c:a", "libmp3lame", "-b:a", "96k", "-ac", "1"]
    args += [str(dst)]
    try:
        subprocess.run(args, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [WARN] transcodifica fallita per {src.name}: {e.stderr.decode(errors='ignore')[:120]}")
        return False


def _export_audio(base: Path, game_id: str, output_dir: Path,
                  scene_music_refs: dict[str, str],
                  menu_music_ref: str | None) -> dict:
    """Esporta SFX globali + musica (scene e menu) come MP3 compressi.

    scene_music_refs: dict[track_name -> resolved_src_path_str]
    Ritorna: {"sfx": {chiave: webpath}, "music": {track_name: webpath}, "menu_music": webpath|None}
    """
    sfx_dir = output_dir / "assets" / "audio" / "sfx"
    music_dir = output_dir / "assets" / "audio" / "music"

    sfx_web: dict[str, str] = {}
    for key, rel in ENGINE_SFX.items():
        src = base / rel
        if not src.exists():
            print(f"  [WARN] SFX mancante: {rel}")
            continue
        dst = sfx_dir / f"{key}.mp3"
        if _transcode_audio(src, dst, music=False):
            actual = dst if dst.exists() else dst.with_suffix(src.suffix)
            sfx_web[key] = f"assets/audio/sfx/{actual.name}"

    music_web: dict[str, str] = {}
    for track_name, src_str in scene_music_refs.items():
        src = Path(src_str)
        if not src.exists():
            print(f"  [WARN] musica mancante: {src}")
            continue
        safe = track_name.replace("/", "__").replace("\\", "__")
        dst = music_dir / (Path(safe).stem + ".mp3")
        if _transcode_audio(src, dst, music=True):
            actual = dst if dst.exists() else dst.with_suffix(src.suffix)
            music_web[track_name] = f"assets/audio/music/{actual.name}"

    menu_music_web = None
    if menu_music_ref:
        src = base / "games" / game_id / menu_music_ref
        if src.exists():
            dst = music_dir / ("menu_" + Path(menu_music_ref).stem + ".mp3")
            if _transcode_audio(src, dst, music=True):
                actual = dst if dst.exists() else dst.with_suffix(src.suffix)
                menu_music_web = f"assets/audio/music/{actual.name}"
        else:
            print(f"  [WARN] musica menu mancante: {src}")

    return {"sfx": sfx_web, "music": music_web, "menu_music": menu_music_web}


def _export_minigames(base: Path, output_dir: Path, used: set[str], languages: list[str]) -> tuple[list[str], dict]:
    """Copia gli asset dei minigiochi usati in assets/minigames/{id}/ e ne raccoglie
    le stringhe namespaced per-minigioco (per evitare collisioni di chiavi tra minigiochi).

    Ritorna: (lista id esportati, {mg_id: {lang: {chiave: testo}}}).
    """
    exported: list[str] = []
    mg_strings: dict[str, dict] = {}
    if not used:
        return exported, mg_strings

    for mg_id in sorted(used):
        src_dir = base / "engine" / "minigames" / mg_id
        if not src_dir.exists():
            print(f"  [WARN] minigioco non trovato: {mg_id}")
            continue
        dst_dir = output_dir / "assets" / "minigames" / mg_id
        # Copia l'INTERO albero del minigioco (immagini in assets/ o nella radice,
        # icon, ecc.) escludendo solo il codice Python. Cosi' funziona sia per i
        # minigiochi con sottocartella assets/ (tetran) sia con immagini in radice
        # (arcade_eleven). Le stringhe restano comunque incorporate nel manifest.
        ignore = shutil.ignore_patterns("*.py", "__pycache__", "*.pyc", "*.pyo")
        shutil.copytree(src_dir, dst_dir, ignore=ignore, dirs_exist_ok=True)

        if mg_id == "slot_classic":
            # Copia i simboli grafici dal catalogo dell'engine
            assets_map = {
                "shiny_star": "obj_slot_shiny_star.png",
                "golden_bell": "obj_slot_golden_bell.png",
                "red_cherries": "obj_slot_red_cherries.png",
                "lucky_seven": "obj_slot_lucky_7.png",
                "blue_diamond": "obj_slot_big_diamond.png",
                "green_clover": "obj_slot_four_leaf_clover.png",
                "grape_bunch": "obj_slot_purple_grapes.png"
            }
            # Crea la cartella assets/ nel minigioco se non esiste
            dst_assets = dst_dir / "assets"
            dst_assets.mkdir(parents=True, exist_ok=True)
            for filename in assets_map.values():
                src_pic = base / "engine" / "assets" / "objects_cartoon" / filename
                if not src_pic.exists():
                    src_pic = base / "engine" / "assets" / "objects" / filename
                if src_pic.exists():
                    shutil.copy2(src_pic, dst_assets / filename)
                    print(f"  [Minigame] simbolo slot copiato: {filename}")

        if mg_id == "spot_differences":
            # Copia le immagini degli oggetti da tutti e tre i cataloghi dell'engine
            # e inserisce un archivio compatto objects.json all'interno della cartella del minigioco.
            dst_objects = dst_dir / "objects"
            dst_objects.mkdir(parents=True, exist_ok=True)
            
            catalog_files = [
                "global_cartoon_catalog.json", 
                "global_real_catalog.json", 
                "global_lineart_catalog.json"
            ]
            
            copied_list = []
            per_style: dict[str, int] = {}  # cap per stile (vedi SPOT_MAX_PER_STYLE)
            for cat_name in catalog_files:
                cat_path = base / "engine" / "data" / cat_name
                if cat_path.exists():
                    try:
                        cat_data = _load_json(cat_path)
                        for obj in cat_data.get("objects", []):
                            icon_rel = obj.get("icon")
                            if not icon_rel:
                                continue
                            style = obj.get("style", "cartoon").lower()
                            if per_style.get(style, 0) >= SPOT_MAX_PER_STYLE:
                                continue
                            src_pic = base / "engine" / "assets" / icon_rel
                            if src_pic.exists():
                                shutil.copy2(src_pic, dst_objects / src_pic.name)
                                per_style[style] = per_style.get(style, 0) + 1
                                copied_list.append({
                                    "id": src_pic.stem,
                                    "icon": f"assets/minigames/spot_differences/objects/{src_pic.name}",
                                    "style": style,
                                    "tags": [t.lower() for t in obj.get("tags", [])]
                                })
                    except Exception as e:
                        print(f"  [WARN] Fallito parsing catalogo {cat_name} in exporter: {e}")

            # Scrive l'elenco degli oggetti in un file locale del minigioco, in modo che runtime.js possa caricarlo
            with open(dst_dir / "objects.json", "w", encoding="utf-8") as f:
                json.dump({"objects": copied_list}, f, ensure_ascii=False, indent=2)
            print(f"  [Minigame] esportati {len(copied_list)} oggetti del catalogo per spot_differences "
                  f"(cap {SPOT_MAX_PER_STYLE}/stile: {per_style})")

        # Copia anche gli asset dei minigiochi-dipendenza (es. arcade_eleven -> tower)
        for dep in MINIGAME_ASSET_DEPS.get(mg_id, []):
            dep_src = base / "engine" / "minigames" / dep
            if dep_src.exists():
                shutil.copytree(dep_src, output_dir / "assets" / "minigames" / dep,
                                ignore=ignore, dirs_exist_ok=True)
                print(f"  [Minigame] dipendenza copiata: {dep} (per {mg_id})")
        # Stringhe del minigioco, namespaced per id
        per_lang: dict[str, dict] = {}
        str_src = src_dir / "strings"
        if str_src.exists():
            for lang in languages:
                p = str_src / f"{lang}.json"
                if p.exists():
                    try:
                        per_lang[lang] = _load_json(p)
                    except Exception as e:
                        print(f"  [WARN] stringhe {mg_id}/{lang}: {e}")
        mg_strings[mg_id] = per_lang
        exported.append(mg_id)
        print(f"  [Minigame] esportato: {mg_id}")
    return exported, mg_strings


def _load_theme(base: Path, game_id: str, theme_id: str) -> dict:
    """Carica il tema UI: prima games/{id}/ui_theme/theme.json, poi engine/assets/themes/{id}."""
    candidates = [
        base / "games" / game_id / "ui_theme" / "theme.json",
        base / "engine" / "assets" / "themes" / theme_id / "theme.json",
        base / "engine" / "assets" / "themes" / "default" / "theme.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                data = _load_json(path)
                return {
                    "id": data.get("id", theme_id),
                    "colors": data.get("colors", {}),
                    "layout": data.get("layout", {}),
                    "effects": data.get("effects", {}),
                    "font": data.get("font", {}),
                    # Estensione skin (per gli skin web DOM/CSS).
                    "layout_profile": data.get("layout_profile", {}),
                    "motion": data.get("motion", {}),
                    "background": data.get("background", {}),
                    "particles": data.get("particles", {}),
                    "typography": data.get("typography", {}),
                    "decor": data.get("decor", {}),
                    "audio_feel": data.get("audio_feel", {}),
                    "scene3d": data.get("scene3d", {}),
                }
            except Exception as e:
                print(f"  [WARN] tema non leggibile {path}: {e}")
    return {"id": theme_id, "colors": {}, "layout": {}, "effects": {}, "font": {},
            "layout_profile": {}, "motion": {}, "background": {}, "particles": {},
            "typography": {}, "decor": {}, "audio_feel": {}, "scene3d": {}}


def _export_fonts(base: Path, game_id: str, theme: dict, assets_dir: Path) -> list[dict]:
    """Copia i font bundlati del tema (typography[*].file) nel build web e
    ritorna [{family, url}] per le @font-face del runtime. Dedup per file."""
    typ = (theme or {}).get("typography", {})
    if not isinstance(typ, dict):
        return []
    theme_id = theme.get("id", "default")
    out: list[dict] = []
    seen: set[str] = set()
    for cfg in typ.values():
        if not isinstance(cfg, dict):
            continue
        file_rel, fam = cfg.get("file"), cfg.get("family")
        if not file_rel or not fam:
            continue
        family = fam[0] if isinstance(fam, list) and fam else fam
        src = next((c for c in (
            base / "games" / game_id / "ui_theme" / file_rel,
            base / "engine" / "assets" / "themes" / theme_id / file_rel,
        ) if c.exists()), None)
        if not src or src.name in seen:
            continue
        seen.add(src.name)
        (assets_dir / "fonts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, assets_dir / "fonts" / src.name)
        out.append({"family": family, "url": f"assets/fonts/{src.name}"})
    return out


def _theme_hex(theme: dict) -> str:
    """Colore principale del tema in #rrggbb (per theme-color / PWA)."""
    c = (theme or {}).get("colors", {})
    rgb = c.get("btn_glow_color") or c.get("slider_fill") or c.get("scene_border_hover") or [120, 160, 240]
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)


def _bg_hex(theme: dict) -> str:
    c = (theme or {}).get("colors", {})
    rgb = c.get("background_overlay") or [10, 12, 20]
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _render_index_html(lang: str, title: str, desc: str, theme_color: str,
                       favicon: str, og_image: str) -> str:
    """index.html completo: meta SEO/Open Graph/Twitter/PWA + canvas + loading screen."""
    og = f'<meta property="og:image" content="{_esc(og_image)}"><meta name="twitter:image" content="{_esc(og_image)}">' if og_image else ""
    fav = f'<link rel="icon" href="{_esc(favicon)}"><link rel="apple-touch-icon" href="{_esc(favicon)}">' if favicon else ""
    t, d = _esc(title), _esc(desc)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>{t}</title>
<meta name="description" content="{d}">
<meta name="theme-color" content="{theme_color}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
{og}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
{fav}
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="manifest.webmanifest">
<link rel="stylesheet" href="style.css">
</head>
<body>
<canvas id="game"></canvas>
<div id="loader" class="loader">
  <div class="loader-box">
    {f'<img class="loader-icon" src="{_esc(favicon)}" alt="">' if favicon else ''}
    <div class="loader-title">{t}</div>
    <div class="loader-bar"><div id="loader-fill"></div></div>
  </div>
</div>
<script src="manifest.js"></script>
<script src="runtime.js"></script>
<script>
// Service worker: offline + installabilita' PWA. Non funziona da file:// (richiede
// http/https): in quel caso si salta in silenzio (il gioco gira comunque via manifest.js).
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {{
  window.addEventListener("load", function () {{
    navigator.serviceWorker.register("sw.js").catch(function () {{}});
  }});
}}
</script>
</body>
</html>
"""


def _write_webmanifest(out: Path, title: str, theme_color: str, bg_color: str, icon: str | None) -> None:
    icons = [{"src": icon, "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}] if icon else []
    data = {
        "name": title,
        "short_name": title[:18],
        "start_url": "./index.html",
        "display": "standalone",
        "orientation": "landscape",
        "background_color": bg_color,
        "theme_color": theme_color,
        "icons": icons,
    }
    (out / "manifest.webmanifest").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_service_worker(out: Path, game_id: str, version: str) -> None:
    """Service worker: precache della app-shell + caching cache-first progressivo degli
    asset al primo fetch (offline-ready). Il nome cache include game+versione, cosi' un
    nuovo build invalida la cache vecchia. Le richieste Range (video/audio seeking) passano
    dirette per non rompere lo streaming. Funziona solo da http(s) (vedi index.html)."""
    cache_name = f"{game_id}-v{version}"
    shell = '["./","./index.html","./style.css","./runtime.js","./manifest.js",' \
            '"./manifest.json","./manifest.webmanifest"]'
    sw = f"""// sw.js — GENERATO da web_exporter. Cache: {cache_name}
const CACHE = "{cache_name}";
const SHELL = {shell};
self.addEventListener("install", (e) => {{
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
}});
self.addEventListener("activate", (e) => {{
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
}});
self.addEventListener("fetch", (e) => {{
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.headers.has("range")) return; // video/audio seeking: passa diretto
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {{
      if (res && res.status === 200 && res.type === "basic") {{
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }}
      return res;
    }}).catch(() => caches.match("./index.html")))
  );
}});
"""
    (out / "sw.js").write_text(sw, encoding="utf-8")


def _collect_strings(base: Path, game_id: str) -> tuple[dict, list[str]]:
    """Unisce stringhe engine + gioco (il gioco vince). Lingue = quelle del gioco."""
    strings: dict[str, dict] = {}
    game_strings_dir = base / "games" / game_id / "strings"
    engine_strings_dir = base / "engine" / "assets" / "strings"

    languages = []
    if game_strings_dir.exists():
        languages = sorted(p.stem for p in game_strings_dir.glob("*.json"))
    if not languages and engine_strings_dir.exists():
        languages = sorted(p.stem for p in engine_strings_dir.glob("*.json"))

    for lang in languages:
        merged = {}
        ep = engine_strings_dir / f"{lang}.json"
        gp = game_strings_dir / f"{lang}.json"
        if ep.exists():
            merged.update(_load_json(ep))
        if gp.exists():
            merged.update(_load_json(gp))
        strings[lang] = merged

    return strings, languages


def export_web_game(game_id: str, output_dir: Path, base: Path | None = None,
                    version: str | None = None) -> dict:
    base = base or Path(__file__).resolve().parents[1]
    game_path = base / "games" / game_id
    if not game_path.exists():
        raise FileNotFoundError(f"Gioco non trovato: {game_path}")

    game_config = _load_json(game_path / "game_config.json")
    version = version or game_config.get("version", "1.0")
    catalog = load_catalog(game_id)

    output_dir = Path(output_dir)
    # Pulisce i contenuti senza rimuovere la cartella radice (potrebbe essere
    # bloccata da un server in esecuzione su Windows).
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
    output_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = output_dir / "assets"
    scenes_assets = assets_dir / "scenes"
    icons_assets = assets_dir / "icons"
    thumbs_assets = assets_dir / "thumbs"
    scenes_assets.mkdir(parents=True, exist_ok=True)
    icons_assets.mkdir(parents=True, exist_ok=True)
    thumbs_assets.mkdir(parents=True, exist_ok=True)

    copied_icons: dict[str, str] = {}  # icon_rel -> web path

    def _copy_icon(icon_rel: str) -> str:
        if not icon_rel:
            return ""
        if icon_rel in copied_icons:
            return copied_icons[icon_rel]
        src = _resolve_icon_src(base, game_id, icon_rel)
        if not src:
            print(f"  [WARN] icona mancante: {icon_rel}")
            copied_icons[icon_rel] = ""
            return ""
        # Nome file univoco (basename -> .webp). Stessa icon_rel ritorna gia' dalla cache
        # sopra, quindi una collisione qui = due icon_rel diverse con lo stesso basename.
        web_name = Path(icon_rel).with_suffix(".webp").name
        dst = icons_assets / web_name
        if dst.exists():
            safe = icon_rel.replace("/", "__").replace("\\", "__")
            web_name = Path(safe).with_suffix(".webp").name
            dst = icons_assets / web_name
        try:
            with Image.open(src) as im:
                im.convert("RGBA").save(dst, "WEBP", lossless=True, quality=100, method=6)
        except Exception as e:
            print(f"  [WARN] conversione WebP icona fallita {icon_rel}: {e} (copia raw)")
            web_name = Path(icon_rel).name
            dst = icons_assets / web_name
            shutil.copy2(src, dst)
        web_path = f"assets/icons/{web_name}"
        copied_icons[icon_rel] = web_path
        return web_path

    # track_name -> path sorgente risolto (per la transcodifica audio)
    scene_music_refs: dict[str, str] = {}
    # Minigiochi effettivamente referenziati da un trigger nelle scene: SOLO questi
    # finiscono nel bundle runtime.js (vedi _bundle_runtime) e ne vengono esportati
    # gli asset (le dipendenze di MINIGAME_ASSET_DEPS sono risolte in _export_minigames).
    triggered_minigames: set[str] = set()

    levels_out = []
    levels_dir = game_path / "levels"
    level_dirs = sorted(p for p in levels_dir.iterdir() if p.is_dir()) if levels_dir.exists() else []

    for level_dir in level_dirs:
        lvl_cfg_path = level_dir / "level_config.json"
        lvl_cfg = _load_json(lvl_cfg_path) if lvl_cfg_path.exists() else {"id": level_dir.name}
        scene_entries = lvl_cfg.get("scenes", [])
        # ordina per 'order' se presente
        scene_entries = sorted(scene_entries, key=lambda s: s.get("order", 0))

        # fallback: se level_config non elenca scene, scopri le cartelle
        if not scene_entries:
            scene_entries = [{"id": p.name} for p in sorted(level_dir.iterdir())
                             if p.is_dir() and (p / "scene.json").exists()]

        scenes_out = []
        for sc_entry in scene_entries:
            sid = sc_entry["id"]
            scene_dir = level_dir / sid
            scene_json = scene_dir / "scene.json"
            if not scene_json.exists():
                print(f"  [WARN] scene.json mancante: {scene_dir}")
                continue
            sdata = _load_json(scene_json)

            # Validazione schema PRIMA di costruire il manifest: una scena che
            # l'engine Python rifiuterebbe non deve finire silenziosamente nel
            # build web (dove diventerebbe un errore JS oscuro nel browser del
            # giocatore). Stesso contratto validate-on-load dell'engine.
            from engine.json_validator import validate as _validate_scene
            _scene_errors = _validate_scene(sdata, "scene", source_path=str(scene_json))
            if _scene_errors:
                raise ValueError(
                    f"Export interrotto: scene.json non valido ({scene_json}):\n"
                    + "\n".join(_scene_errors)
                )

            # Background: copia + dimensioni reali (bg-space). Supporta immagini e video.
            bg_name = sdata["background"]
            bg_src = scene_dir / bg_name
            is_video = _is_video(bg_name)
            bg_w, bg_h = 1280, 720
            bg_web = ""
            thumb_web = ""
            bg_is_video = False
            if bg_src.exists():
                dst_dir = scenes_assets / f"{level_dir.name}__{sid}"
                dst_dir.mkdir(parents=True, exist_ok=True)
                thumb_name = f"{level_dir.name}__{sid}.jpg"
                if is_video:
                    # Video: dimensioni via ffprobe (per le coordinate), anteprima dal frame.
                    bg_w, bg_h = _ffprobe_size(bg_src)
                    shutil.copy2(bg_src, dst_dir / bg_name)
                    bg_web = f"assets/scenes/{level_dir.name}__{sid}/{bg_name}"
                    bg_is_video = True
                    if _video_thumb(bg_src, thumbs_assets / thumb_name):
                        thumb_web = f"assets/thumbs/{thumb_name}"
                else:
                    with Image.open(bg_src) as im:
                        # bg-space = dimensioni ORIGINALI: le coordinate non cambiano anche
                        # se il file esportato viene ridotto di risoluzione.
                        bg_w, bg_h = im.size
                        rgb = im.convert("RGB")
                        # thumbnail menu (480px)
                        tw = 480
                        th = max(1, round(bg_h * tw / bg_w))
                        rgb.resize((tw, th), Image.LANCZOS).save(
                            thumbs_assets / thumb_name, "JPEG", quality=80)
                        thumb_web = f"assets/thumbs/{thumb_name}"
                        # sfondo: WebP, risoluzione cappata a BG_MAX_DIM
                        scale = min(1.0, BG_MAX_DIM / max(bg_w, bg_h))
                        bg_img = rgb
                        if scale < 1.0:
                            bg_img = rgb.resize(
                                (max(1, round(bg_w * scale)), max(1, round(bg_h * scale))),
                                Image.LANCZOS)
                        bg_out_name = Path(bg_name).with_suffix(".webp").name
                        bg_img.save(dst_dir / bg_out_name, "WEBP",
                                    quality=BG_WEBP_QUALITY, method=6)
                    bg_web = f"assets/scenes/{level_dir.name}__{sid}/{bg_out_name}"
            else:
                print(f"  [WARN] background mancante: {bg_src}")

            # Oggetti — mirroring scene_loader
            objs = []
            counts: dict[str, int] = {}
            for raw in sdata.get("objects", []):
                cid = raw["catalog_id"]
                counts[cid] = counts.get(cid, 0) + 1
                iid = cid if counts[cid] == 1 else f"{cid}_{counts[cid]}"
                obj = _build_object(raw, iid, catalog)
                obj["icon"] = _copy_icon(obj.pop("_icon_rel"))
                if obj.get("minigame_trigger") and obj["minigame_trigger"].get("minigame_id"):
                    triggered_minigames.add(obj["minigame_trigger"]["minigame_id"])
                objs.append(obj)

            # Effetti ambientali (glint/smoke/flies) + fumetti (bubble_tip),
            # mirroring scene_loader defaults.
            fx_out = []
            bubbles_out = []
            for raw_fx in sdata.get("effects", []):
                ftype = raw_fx.get("type", "glint")
                if ftype == "bubble_tip":
                    bubbles_out.append({
                        "x": float(raw_fx.get("x", 0)),
                        "y": float(raw_fx.get("y", 0)),
                        "text_key": raw_fx.get("text_key", "NEW_TIP"),
                        "trigger": raw_fx.get("trigger", "start_scene"),
                        "width": float(raw_fx.get("width", 300)),
                        "height": float(raw_fx.get("height", 180)),
                        "color": list(raw_fx.get("color", [255, 255, 255])),
                        "alpha": int(raw_fx.get("alpha", 255)),
                        "font_size": int(raw_fx.get("font_size", 22)),
                        "font_color": list(raw_fx.get("font_color", [40, 40, 40])),
                        "layer_z": int(raw_fx.get("layer_z", 40)),
                    })
                    continue
                fx_out.append({
                    "type": ftype,
                    "x": float(raw_fx.get("x", 0)),
                    "y": float(raw_fx.get("y", 0)),
                    "radius": float(raw_fx.get("radius", 50)),
                    "color": list(raw_fx.get("color", [255, 255, 255])),
                    "intensity": float(raw_fx.get("intensity", 1.0)),
                    "layer_z": int(raw_fx.get("layer_z", 40)),
                    "phase": float(raw_fx.get("phase", 0.0)),
                    "pulse_min": float(raw_fx.get("pulse_min", 0.1)),
                    "pulse_period": float(raw_fx.get("pulse_period", 2.0)),
                })

            # Musica di scena: l'engine risolve games/{id}/audio/music/{nome}
            raw_music = sdata.get("music", [])
            if isinstance(raw_music, str):
                raw_music = [raw_music]
            scene_track = raw_music[0] if raw_music else None
            if scene_track:
                src = game_path / "audio" / "music" / scene_track
                scene_music_refs.setdefault(scene_track, str(src))

            scenes_out.append({
                "id": sid,
                "order": sc_entry.get("order", 0),
                "time_limit": sc_entry.get("time_limit", 120),
                "background": bg_web,
                "bg_is_video": bg_is_video,
                "thumb": thumb_web,
                "background_scale": float(sdata.get("background_scale", 1.0)),
                "bg_w": bg_w,
                "bg_h": bg_h,
                "music_track": scene_track,  # risolto in web path dopo l'export audio
                "effects": fx_out,
                "bubble_tips": bubbles_out,
                "flashlight": _to_bool(sdata.get("flashlight", False)),
                "flashlight_radius": float(sdata.get("flashlight_radius", 150.0)),
                # Selezione casuale (replicata a runtime, ad ogni avvio scena)
                "random_layer_selection": _to_bool(sdata.get("random_layer_selection", False)),
                "auto_random_finds": _to_bool(sdata.get("auto_random_finds", False)),
                "num_random_finds": (int(sdata["num_random_finds"]) if sdata.get("num_random_finds") is not None else None),
                "objects": objs,
            })

        levels_out.append({
            "id": lvl_cfg.get("id", level_dir.name),
            "name_key": lvl_cfg.get("name_key", level_dir.name),
            "timer_behavior": lvl_cfg.get("timer_behavior", "complete"),
            "scenes": scenes_out,
        })

    # ── Audio: SFX globali + musica scene/menu (MP3 compresso) ──────────────
    menu_cfg = game_config.get("menu", {})
    menu_music_list = menu_cfg.get("music", []) if isinstance(menu_cfg, dict) else []
    menu_music_ref = menu_music_list[0] if menu_music_list else None
    audio = _export_audio(base, game_id, output_dir, scene_music_refs, menu_music_ref)

    # Video di sfondo del menu (game_config menu.background, se .mp4/.webm/...)
    menu_video = None
    menu_bg = menu_cfg.get("background", "") if isinstance(menu_cfg, dict) else ""
    if menu_bg and _is_video(menu_bg):
        mv_src = game_path / menu_bg
        if mv_src.exists():
            mv_dir = assets_dir / "video"
            mv_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mv_src, mv_dir / Path(menu_bg).name)
            menu_video = f"assets/video/{Path(menu_bg).name}"
        else:
            print(f"  [WARN] video menu mancante: {mv_src}")

    # Poster statico del menu (mostrato come fallback del video e poster del <video>)
    menu_poster = None
    poster_ref = menu_cfg.get("background_static", "") if isinstance(menu_cfg, dict) else ""
    if not poster_ref and menu_bg and not _is_video(menu_bg):
        poster_ref = menu_bg  # se il menu ha gia' un'immagine statica
    if poster_ref:
        pp = game_path / poster_ref
        if pp.exists():
            shutil.copy2(pp, assets_dir / ("menu_poster" + pp.suffix))
            menu_poster = f"assets/menu_poster{pp.suffix}"

    # Collega ogni scena al suo web path musica
    for lvl in levels_out:
        for sc in lvl["scenes"]:
            track = sc.pop("music_track", None)
            sc["music"] = audio["music"].get(track) if track else None

    strings, languages = _collect_strings(base, game_id)

    # Minigiochi: copia asset + stringhe namespaced per-minigioco
    minigames, mg_strings = _export_minigames(base, output_dir, triggered_minigames, languages)

    manifest = {
        "game_id": game_id,
        "title_key": game_config.get("title_key", game_id),
        "default_language": game_config.get("default_language", "it"),
        "ui_theme": game_config.get("ui_theme", "default"),
        "version": version,
        "runtime_version": RUNTIME_VERSION,
        "ref": {"w": 1280, "h": 720},
        "rules": engine_rules(),  # fonte unica: costanti lette dall'engine (vedi WEB_EXPORT_SYNC.md)
        "theme": _load_theme(base, game_id, game_config.get("ui_theme", "default")),
        "languages": languages,
        "strings": strings,
        "sfx": audio["sfx"],
        "menu_music": audio["menu_music"],
        "menu_video": menu_video,
        "menu_poster": menu_poster,
        "minigames": minigames,
        "minigame_strings": mg_strings,
        "levels": levels_out,
    }
    manifest["fonts"] = _export_fonts(base, game_id, manifest["theme"], assets_dir)

    manifest_str = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest_str)
    # manifest.js: stesso contenuto come variabile globale, cosi' il gioco si apre
    # anche con doppio-clic su index.html (file://) senza bisogno di un server.
    with open(output_dir / "manifest.js", "w", encoding="utf-8") as f:
        f.write("window.__MANIFEST__ = " + manifest_str + ";\n")

    # ── Meta del sito (SEO/social/PWA) ───────────────────────────────────────
    default_lang = manifest["default_language"]
    title = (strings.get(default_lang, {}) or {}).get(manifest["title_key"], game_id)
    n_scenes_meta = sum(len(l["scenes"]) for l in levels_out)
    desc = (f"{title} — gioco hidden object. "
            f"{len(levels_out)} livelli, {n_scenes_meta} scene, {len(languages)} lingue. Gioca online.")
    theme_color = _theme_hex(manifest["theme"])
    bg_color = _bg_hex(manifest["theme"])

    # favicon: icona gioco -> poster -> prima thumbnail.  og-image: poster -> thumb -> icona.
    icon_ref = game_config.get("icon", "")
    favicon_web = ""
    if icon_ref and (game_path / icon_ref).exists() and not _is_video(icon_ref):
        shutil.copy2(game_path / icon_ref, assets_dir / ("icon" + Path(icon_ref).suffix))
        favicon_web = f"assets/icon{Path(icon_ref).suffix}"
    first_thumb = next((s["thumb"] for l in levels_out for s in l["scenes"] if s.get("thumb")), "")
    if not favicon_web:
        favicon_web = (menu_poster or first_thumb or "")
    og_web = (menu_poster or first_thumb or favicon_web or "")

    # index.html generato (meta completi) + style.css/runtime.js statici
    (output_dir / "index.html").write_text(
        _render_index_html(default_lang, title, desc, theme_color, favicon_web, og_web),
        encoding="utf-8")
    shutil.copy2(TEMPLATE_DIR / "style.css", output_dir / "style.css")
    # runtime.js: bundle dei soli minigiochi triggerati nelle scene.
    _bundle_runtime(output_dir / "runtime.js", triggered_minigames)
    _write_webmanifest(output_dir, title, theme_color, bg_color, favicon_web or None)
    _write_service_worker(output_dir, game_id, version)

    # File .bat per avviare un server locale e aprire il browser (Windows).
    # Utile per testare velocemente; per la pubblicazione basta caricare la cartella.
    bat = (
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        "set PORT=8000\r\n"
        "echo ====================================================\r\n"
        "echo  Server locale: http://localhost:%PORT%\r\n"
        "echo  Premi CTRL+C in questa finestra per fermarlo.\r\n"
        "echo ====================================================\r\n"
        "start \"\" \"http://localhost:%PORT%/\"\r\n"
        "python -m http.server %PORT% || py -m http.server %PORT%\r\n"
        "pause\r\n"
    )
    (output_dir / "avvia_server.bat").write_text(bat, encoding="utf-8")

    # Metadati di build (versionamento)
    n_scenes_v = sum(len(l["scenes"]) for l in levels_out)
    version_info = {
        "game_id": game_id,
        "version": version,
        "runtime_version": RUNTIME_VERSION,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "languages": languages,
        "levels": len(levels_out),
        "scenes": n_scenes_v,
        "minigames": minigames,
    }
    with open(output_dir / "version.json", "w", encoding="utf-8") as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)

    # Stats
    n_scenes = sum(len(l["scenes"]) for l in levels_out)
    n_objs = sum(len(s["objects"]) for l in levels_out for s in l["scenes"])
    total_bytes = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    print(f"[OK] Esportato '{game_id}' -> {output_dir}")
    print(f"     {len(levels_out)} livelli, {n_scenes} scene, {n_objs} oggetti, "
          f"{len(copied_icons)} icone, {len(languages)} lingue")
    print(f"     Dimensione totale: {total_bytes/1024/1024:.1f} MB")

    return {
        "success": True,
        "output_dir": str(output_dir),
        "levels": len(levels_out),
        "scenes": n_scenes,
        "objects": n_objs,
        "meta": {
            "title": title, "description": desc, "lang": default_lang,
            "theme_color": theme_color, "bg_color": bg_color,
            "favicon": favicon_web, "og_image": og_web,
            "languages": languages, "minigames": minigames,
        },
    }


def _next_web_version(game_id: str, root: Path, base: Path) -> str:
    """Versione del prossimo build web (mirror di build_system.next_build_version):
    parte dalla versione di game_config; se v<version> esiste gia', incrementa il minor."""
    current = _load_json(base / "games" / game_id / "game_config.json").get("version", "1.0")
    if not (root / f"v{current}").exists():
        return current
    try:
        major, minor = current.split(".", 1)
        minor_int = int(minor)
    except ValueError:
        major, minor_int = current, 0
    while True:
        minor_int += 1
        cand = f"{major}.{minor_int}"
        if not (root / f"v{cand}").exists():
            return cand


def export_web_versioned(game_id: str, base: Path | None = None, version: str | None = None) -> dict:
    """Build versionato: build_web/<game>/v<X.Y>/ + index.html redirect a 'latest' + builds.json."""
    base = base or Path(__file__).resolve().parents[1]
    root = base / "build_web" / game_id
    root.mkdir(parents=True, exist_ok=True)

    # Migrazione: rimuove eventuali artefatti di un vecchio build "flat" nella root.
    for stale in ("runtime.js", "manifest.js", "manifest.json", "style.css", "avvia_server.bat", "version.json"):
        p = root / stale
        if p.exists():
            try: p.unlink()
            except OSError: pass
    if (root / "assets").is_dir():
        shutil.rmtree(root / "assets", ignore_errors=True)

    version = version or _next_web_version(game_id, root, base)
    out = root / f"v{version}"
    result = export_web_game(game_id, out, base, version=version)
    meta = result.get("meta", {})
    vdir = f"v{version}/"
    fav_root = (vdir + meta["favicon"]) if meta.get("favicon") else ""
    og_root = (vdir + meta["og_image"]) if meta.get("og_image") else ""

    # index.html nella root: landing curata con meta + redirect alla versione latest.
    (root / "index.html").write_text(
        _render_landing_html(meta.get("lang", "it"), meta.get("title", game_id),
                             meta.get("description", ""), meta.get("theme_color", "#0b1220"),
                             fav_root, og_root, vdir),
        encoding="utf-8")
    shutil.copy2(out / "avvia_server.bat", root / "avvia_server.bat")

    # builds.json: storico versioni
    builds_path = root / "builds.json"
    builds = []
    if builds_path.exists():
        try: builds = _load_json(builds_path).get("builds", [])
        except Exception: builds = []
    vinfo = _load_json(out / "version.json")
    builds = [b for b in builds if b.get("version") != version]
    builds.append({"version": version, "built_at": vinfo["built_at"], "path": vdir})
    builds.sort(key=lambda b: b["built_at"])
    builds_path.write_text(json.dumps(
        {"game_id": game_id, "latest": version, "builds": builds}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # game.json: metadati per la piattaforma/portale (un record per gioco)
    game_meta = {
        "id": game_id,
        "title": meta.get("title", game_id),
        "description": meta.get("description", ""),
        "version": version,
        "languages": meta.get("languages", []),
        "minigames": meta.get("minigames", []),
        "theme_color": meta.get("theme_color", ""),
        "icon": fav_root,
        "og_image": og_root,
        "url": vdir,            # entry point del gioco (relativo alla cartella del gioco)
        "built_at": vinfo["built_at"],
    }
    (root / "game.json").write_text(json.dumps(game_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # build_web/index.json: catalogo aggregato di tutti i giochi (per il portale)
    _update_catalog_index(root.parent, game_id, game_meta)

    print(f"     Versione: v{version}  (latest -> build_web/{game_id}/index.html)")
    result["version"] = version
    result["root"] = str(root)
    return result


def _render_landing_html(lang, title, desc, theme_color, favicon, og_image, vdir) -> str:
    """Landing della root: meta social/SEO + redirect automatico alla versione latest."""
    og = f'<meta property="og:image" content="{_esc(og_image)}"><meta name="twitter:image" content="{_esc(og_image)}">' if og_image else ""
    fav = f'<link rel="icon" href="{_esc(favicon)}">' if favicon else ""
    t, d = _esc(title), _esc(desc)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{t}</title>
<meta name="description" content="{d}">
<meta name="theme-color" content="{theme_color}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
{og}
<meta name="twitter:card" content="summary_large_image">
{fav}
<meta http-equiv="refresh" content="0; url=./{vdir}">
<style>html,body{{margin:0;height:100%;background:{theme_color}1a;background-color:#0b1220;color:#cdd;
font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;text-align:center}}
a{{color:{theme_color}}}</style>
</head>
<body><div><h1 style="margin:0 0 8px">{t}</h1>
<p>Caricamento… <a href="./{vdir}">apri il gioco</a></p></div></body>
</html>
"""


def _update_catalog_index(build_root: Path, game_id: str, game_meta: dict) -> None:
    """Aggiorna build_web/index.json con il record del gioco (catalogo per il portale)."""
    idx_path = build_root / "index.json"
    games = {}
    if idx_path.exists():
        try:
            for g in _load_json(idx_path).get("games", []):
                games[g["id"]] = g
        except Exception:
            games = {}
    # nel catalogo, i path sono relativi alla root di build_web: <game>/<...>
    rec = dict(game_meta)
    rec["icon"] = f"{game_id}/{game_meta['icon']}" if game_meta.get("icon") else ""
    rec["og_image"] = f"{game_id}/{game_meta['og_image']}" if game_meta.get("og_image") else ""
    rec["url"] = f"{game_id}/{game_meta['url']}"
    games[game_id] = rec
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "games": sorted(games.values(), key=lambda g: g["id"]),
    }
    idx_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def zip_game(root: Path) -> Path:
    """Crea uno .zip distribuibile della cartella del gioco (game.json alla radice
    dello zip). Include SOLO la versione 'latest' + i file di root (non lo storico
    delle vecchie versioni), per tenere lo zip leggero. Adatto all'upload drag&drop
    nel portale (web_platform)."""
    root = Path(root)
    dst = root.parent / f"{root.name}.zip"
    if dst.exists():
        dst.unlink()
    # versione latest dal game.json (es. "v1.2/")
    latest_dir = ""
    gj = root / "game.json"
    if gj.exists():
        latest_dir = _load_json(gj).get("url", "").strip("/")  # "v1.2"
    root_files = {"game.json", "index.html", "builds.json", "avvia_server.bat"}
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            top = rel.parts[0]
            keep = (top in root_files) or (latest_dir and top == latest_dir)
            if keep:
                zf.write(f, arcname=str(rel))
    print(f"     ZIP distribuibile: {dst} ({dst.stat().st_size/1024/1024:.1f} MB)")
    return dst


def main():
    ap = argparse.ArgumentParser(description="Esporta un gioco HiddenEngine in sito web statico.")
    ap.add_argument("game_id", help="ID del gioco (es. LineVenture)")
    ap.add_argument("--out", default=None,
                    help="Cartella di output esplicita (build 'flat', niente versionamento)")
    ap.add_argument("--version", default=None,
                    help="Forza la versione (default: da game_config, con auto-incremento)")
    ap.add_argument("--zip", action="store_true",
                    help="Crea anche uno .zip distribuibile (per upload nel portale)")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    if args.out:
        res = export_web_game(args.game_id, Path(args.out), base, version=args.version)
        if args.zip:
            zip_game(Path(args.out))
    else:
        res = export_web_versioned(args.game_id, base, version=args.version)
        if args.zip:
            zip_game(Path(res["root"]))


if __name__ == "__main__":
    main()
