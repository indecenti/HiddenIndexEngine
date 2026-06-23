#!/usr/bin/env python3
"""
tools/hie_mcp_server.py — MCP server del progetto HiddenIndexEngine.

Espone a un client MCP (es. Claude Code) strumenti specifici per lavorare sul
motore HOG:

  - render_scene        : renderizza una scena in PNG (headless, via engine)
  - render_asset        : renderizza un singolo asset del catalogo in PNG
  - validate_scene      : valida una scene.json (schema + integrita' referenziale)
  - search_catalog      : cerca oggetti nel catalogo per id o tag
  - check_missing_assets: trova entry di catalogo con PNG mancante
  - list_games          : elenca giochi, livelli e scene
  - build_status        : artefatti di build presenti (apk/aab/exe) — sola lettura

Fedelta': il rendering e la risoluzione del catalogo riusano i moduli reali
dell'engine (`engine.catalog_manager`, `engine.scene_loader`, `engine.utils`),
quindi il risultato coincide con quanto mostra il gioco.

Avvio come MCP server (stdio):   python tools/hie_mcp_server.py
Self-test della logica core:     python tools/hie_mcp_server.py --selftest

Richiede il pacchetto `mcp` SOLO per girare come server (vedi requirements-dev.txt).
Il self-test e l'import dei core helper funzionano anche senza `mcp`.
"""

from __future__ import annotations

import io
import os
import sys
import json
import logging
import contextlib
import tempfile
from pathlib import Path
from typing import Optional

# Repo root sul path, indipendentemente dal cwd con cui il client lancia il server.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Pygame headless: niente finestra, niente audio. Va impostato PRIMA di importare
# qualsiasi modulo engine (che a sua volta importa pygame).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Su stdio MCP il canale stdout e' RISERVATO al protocollo JSON-RPC: qualsiasi
# scrittura spuria lo corrompe. Mandiamo il logging dell'engine su stderr e
# silenziamo lo spam noto di validazione catalogo (il catalogo globale ha entry
# legacy che non passano lo schema stretto; e' una condizione dati preesistente,
# non un errore del server). Le violazioni di scena le ritorna comunque
# validate_scene leggendo il valore di ritorno, non il log.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logging.getLogger("engine.json_validator").setLevel(logging.CRITICAL)


@contextlib.contextmanager
def _quiet_stdout():
    """Reindirizza temporaneamente sys.stdout su stderr (protezione canale MCP)."""
    old = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old


# ---------------------------------------------------------------------------
# Inizializzazione pygame lazy (serve un display dummy per convert_alpha)
# ---------------------------------------------------------------------------

_pygame_ready = False


def _ensure_pygame() -> None:
    global _pygame_ready
    if _pygame_ready:
        return
    import pygame
    with _quiet_stdout():
        pygame.init()
        pygame.display.set_mode((64, 64))
    _pygame_ready = True


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

def _games_dir() -> Path:
    return _ROOT / "games"


def _scene_dir(game_id: str, level_id: str, scene_id: str) -> Path:
    return _games_dir() / game_id / "levels" / level_id / scene_id


def _resolve_icon(icon: str, game_id: Optional[str]) -> Optional[Path]:
    """Risolve un path icona come fa l'engine: prima locale al gioco, poi engine/assets."""
    if not icon:
        return None
    candidates = []
    if game_id:
        candidates.append(_games_dir() / game_id / icon)
    candidates.append(_ROOT / "engine" / "assets" / icon)
    for c in candidates:
        if c.exists():
            return c
    return None


def _is_video(path: str) -> bool:
    return path.lower().endswith((".mp4", ".mov", ".mkv"))


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

def _merged_catalog(game_id: str):
    from engine.catalog_manager import load_catalog
    return load_catalog(game_id)


def _global_objects() -> list[dict]:
    from engine.catalog_manager import _load_global_catalog
    try:
        return _load_global_catalog().get("objects", [])
    except Exception:
        return []


def _catalog_entry(catalog_id: str, game_id: Optional[str]) -> Optional[dict]:
    if game_id:
        try:
            return _merged_catalog(game_id).get_by_id(catalog_id)
        except Exception:
            pass
    for o in _global_objects():
        if o.get("id") == catalog_id:
            return o
    return None


# ---------------------------------------------------------------------------
# Core ops (riusabili senza il pacchetto mcp)
# ---------------------------------------------------------------------------

def list_games() -> list[dict]:
    """Elenca i giochi (cartelle con game_config.json) con livelli e scene."""
    out: list[dict] = []
    gd = _games_dir()
    if not gd.exists():
        return out
    for d in sorted(gd.iterdir()):
        if not d.is_dir() or not (d / "game_config.json").exists():
            continue
        levels = []
        ld = d / "levels"
        if ld.exists():
            for lvl in sorted(p for p in ld.iterdir() if p.is_dir()):
                scenes = [
                    s.name for s in sorted(p for p in lvl.iterdir() if p.is_dir())
                    if (s / "scene.json").exists()
                ]
                if scenes:
                    levels.append({"level": lvl.name, "scenes": scenes})
        out.append({"game": d.name, "levels": levels})
    return out


def search_catalog(query: str = "", tag: str = "", game_id: str = "",
                   limit: int = 50) -> list[dict]:
    """Cerca nel catalogo (unito se game_id, altrimenti solo globale).

    Match: (query substring nell'id) AND (tag presente nei tag). Campi vuoti = no filtro.
    """
    if game_id:
        objs = _merged_catalog(game_id).get("objects")
    else:
        objs = _global_objects()
    q = query.lower().strip()
    t = tag.lower().strip()
    res = []
    for o in objs:
        oid = str(o.get("id", ""))
        tags = [str(x).lower() for x in o.get("tags", [])]
        if q and q not in oid.lower():
            continue
        if t and t not in tags:
            continue
        res.append({
            "id": oid,
            "icon": o.get("icon") or o.get("image", ""),
            "detection": o.get("default_detection", ""),
            "style": o.get("style", ""),
            "tags": o.get("tags", []),
        })
        if len(res) >= max(1, limit):
            break
    return res


def check_missing_assets(game_id: str = "") -> dict:
    """Trova entry di catalogo il cui PNG non esiste su filesystem."""
    missing = []
    if game_id:
        objs = _merged_catalog(game_id).get("objects")
    else:
        objs = _global_objects()
    for o in objs:
        icon = o.get("icon") or o.get("image", "")
        if not icon:
            missing.append({"id": o.get("id"), "icon": "", "reason": "campo icon assente"})
            continue
        if _resolve_icon(icon, game_id or None) is None:
            missing.append({"id": o.get("id"), "icon": icon, "reason": "file non trovato"})
    return {
        "scope": game_id or "globale",
        "checked": len(objs),
        "missing_count": len(missing),
        "missing": missing[:300],
    }


def validate_scene(game_id: str, level_id: str, scene_id: str) -> dict:
    """Valida una scena: schema JSON + integrita' referenziale + coordinate."""
    issues: list[dict] = []

    def add(sev: str, msg: str, obj: Optional[int] = None) -> None:
        item = {"severity": sev, "msg": msg}
        if obj is not None:
            item["object_index"] = obj
        issues.append(item)

    sdir = _scene_dir(game_id, level_id, scene_id)
    path = sdir / "scene.json"
    if not path.exists():
        return {"ok": False, "issues": [{"severity": "error", "msg": f"scene.json non trovato: {path}"}]}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "issues": [{"severity": "error", "msg": f"JSON non valido: {e}"}]}

    # 1. Validazione schema (jsonschema opzionale)
    try:
        from engine.json_validator import validate as vjson
        for e in vjson(raw, "scene", source_path=str(path)) or []:
            add("error", f"schema: {e}")
    except Exception as e:
        add("warning", f"validazione schema saltata: {e}")

    # 2. Background
    bg_name = raw.get("background", "")
    bg_path = sdir / bg_name
    bg_w = bg_h = None
    if not bg_name:
        add("error", "campo 'background' mancante")
    elif _is_video(bg_name):
        if not bg_path.exists():
            add("warning", f"background video assente: {bg_name}")
    elif not bg_path.exists():
        add("error", f"background non trovato: {bg_name}")
    else:
        try:
            import pygame
            _ensure_pygame()
            bg_w, bg_h = pygame.image.load(str(bg_path)).get_size()
        except Exception as e:
            add("warning", f"impossibile leggere dimensioni background: {e}")

    # 3. Oggetti: catalog_id esistente, icona presente, detection coerente, bounds
    try:
        cat = _merged_catalog(game_id)
    except Exception as e:
        cat = None
        add("warning", f"catalogo non caricato: {e}")

    objects = raw.get("objects", [])
    goals = 0
    for i, o in enumerate(objects):
        cid = o.get("catalog_id", "")
        if o.get("is_goal", True):
            goals += 1
        entry = cat.get_by_id(cid) if cat is not None else None
        if cid and entry is None:
            add("error", f"catalog_id '{cid}' assente dal catalogo (goal invisibile, oggetto scartato dall'engine)", i)
        elif entry is not None:
            icon = entry.get("icon") or entry.get("image", "")
            if _resolve_icon(icon, game_id) is None:
                add("error", f"icona mancante per '{cid}': {icon}", i)

        dt = o.get("detection_type", "")
        if dt == "circle" and "radius" not in o:
            add("warning", f"detection circle senza 'radius' (uso default)", i)
        if dt == "rect" and ("width" not in o or "height" not in o):
            add("warning", f"detection rect senza width/height", i)

        if bg_w and bg_h:
            x, y = o.get("x", 0), o.get("y", 0)
            if not (0 <= x <= bg_w and 0 <= y <= bg_h):
                add("warning", f"oggetto fuori dai bounds del background ({x},{y}) vs {bg_w}x{bg_h}", i)

    errors = [i for i in issues if i["severity"] == "error"]
    return {
        "ok": len(errors) == 0,
        "scene": f"{game_id}/{level_id}/{scene_id}",
        "background_size": [bg_w, bg_h] if bg_w else None,
        "object_count": len(objects),
        "goal_count": goals,
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "issues": issues,
    }


def render_scene_png(game_id: str, level_id: str, scene_id: str,
                     max_width: int = 1280) -> bytes:
    """Renderizza una scena in PNG (spazio nativo del background, poi ridimensionato)."""
    _ensure_pygame()
    import pygame
    from engine.scene_loader import SceneLoader
    from engine.utils import apply_grayscale

    sdir = _scene_dir(game_id, level_id, scene_id)
    raw = json.loads((sdir / "scene.json").read_text(encoding="utf-8"))

    cat = _merged_catalog(game_id)
    loader = SceneLoader(game_id, cat)
    raw_objs = raw.get("objects", [])
    # _select_objects carica le icon_surface e NON applica il random layer/goal:
    # vogliamo la scena completa per la preview.
    objs = loader._select_objects(raw_objs, len(raw_objs), str(sdir))

    bg_name = raw.get("background", "")
    bg_path = sdir / bg_name
    if bg_path.exists() and not _is_video(bg_name):
        canvas = pygame.image.load(str(bg_path)).convert_alpha()
    else:
        canvas = pygame.Surface((1280, 720))
        canvas.fill((28, 28, 38))

    for o in objs:  # gia' ordinati per layer_z
        if o.icon_surface is None:
            continue
        if o.detection_type == "rect":
            cx, cy = o.x + o.width / 2, o.y + o.height / 2
            w, h = o.width, o.height
        else:
            cx, cy = o.x, o.y
            w = o.width if o.width > 0 else o.radius * 2
            h = o.height if o.height > 0 else o.radius * 2
        scale = getattr(o, "scale", 1.0)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))

        surf = pygame.transform.smoothscale(o.icon_surface, (dw, dh))
        if o.flip_x or o.flip_y:
            surf = pygame.transform.flip(surf, o.flip_x, o.flip_y)
        if o.rotation:
            surf = pygame.transform.rotozoom(surf, o.rotation, 1.0)
        if getattr(o, "grayscale", False):
            surf = apply_grayscale(surf, getattr(o, "grayscale_factor", 1.0))
        if tuple(o.color_filter) != (255, 255, 255):
            tint = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            tint.fill((*o.color_filter, 255))
            surf.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        if o.alpha < 255:
            surf.set_alpha(o.alpha)

        iw, ih = surf.get_size()
        canvas.blit(surf, (int(round(cx - iw / 2)), int(round(cy - ih / 2))))

    cw, ch = canvas.get_size()
    if max_width and cw > max_width:
        ratio = max_width / cw
        canvas = pygame.transform.smoothscale(canvas, (int(max_width), max(1, int(ch * ratio))))

    buf = io.BytesIO()
    pygame.image.save(canvas, buf, "scene.png")
    return buf.getvalue()


def render_asset_png(catalog_id: str, game_id: str = "", max_dim: int = 512) -> bytes:
    """Renderizza un singolo asset di catalogo in PNG."""
    _ensure_pygame()
    import pygame

    entry = _catalog_entry(catalog_id, game_id or None)
    if entry is None:
        raise ValueError(f"catalog_id '{catalog_id}' non trovato nel catalogo")
    icon = entry.get("icon") or entry.get("image", "")
    path = _resolve_icon(icon, game_id or None)
    if path is None:
        raise FileNotFoundError(f"PNG non trovato per '{catalog_id}': {icon}")

    surf = pygame.image.load(str(path)).convert_alpha()
    w, h = surf.get_size()
    if max_dim and max(w, h) > max_dim:
        r = max_dim / max(w, h)
        surf = pygame.transform.smoothscale(surf, (max(1, int(w * r)), max(1, int(h * r))))
    buf = io.BytesIO()
    pygame.image.save(surf, buf, "asset.png")
    return buf.getvalue()


def build_status() -> dict:
    """Artefatti di build presenti (sola lettura)."""
    out: dict = {"apk": [], "aab": [], "exe": [], "build_dirs": []}
    for sub, exts in (("dist", (".exe", ".apk", ".aab")),
                      ("bin", (".apk", ".aab")),
                      ("build", (".apk", ".aab"))):
        base = _ROOT / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            ext = p.suffix.lower()
            if ext in exts and p.is_file():
                key = ext.lstrip(".")
                rec = {"path": str(p.relative_to(_ROOT)), "mb": round(p.stat().st_size / 1e6, 1)}
                out.setdefault(key, []).append(rec)
    bd = _ROOT / "build"
    if bd.exists():
        for game in sorted(p for p in bd.iterdir() if p.is_dir()):
            vers = sorted(v.name for v in game.iterdir() if v.is_dir())
            if vers:
                out["build_dirs"].append({"game": game.name, "versions": vers})
    for k in ("apk", "aab", "exe"):
        out[k] = out.get(k, [])[:50]
    return out


# ---------------------------------------------------------------------------
# Registrazione MCP (FastMCP). Importazione guardata: la logica core resta
# usabile (e testabile) anche senza il pacchetto `mcp` installato.
# ---------------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP, Image
    _HAS_MCP = True
except Exception:  # pragma: no cover - dipende dall'ambiente
    FastMCP = None  # type: ignore
    Image = None  # type: ignore
    _HAS_MCP = False


def _build_server():
    mcp = FastMCP("hie")

    @mcp.tool(name="list_games")
    def _list_games() -> str:
        """Elenca i giochi del progetto con i relativi livelli e scene."""
        return json.dumps(list_games(), ensure_ascii=False, indent=2)

    @mcp.tool(name="search_catalog")
    def _search_catalog(query: str = "", tag: str = "", game: str = "",
                        limit: int = 50) -> str:
        """Cerca oggetti nel catalogo per substring dell'id e/o per tag.

        game vuoto = solo catalogo globale; altrimenti catalogo unito del gioco.
        """
        return json.dumps(search_catalog(query, tag, game, limit), ensure_ascii=False, indent=2)

    @mcp.tool(name="check_missing_assets")
    def _check_missing_assets(game: str = "") -> str:
        """Elenca le entry di catalogo il cui PNG non esiste su filesystem."""
        return json.dumps(check_missing_assets(game), ensure_ascii=False, indent=2)

    @mcp.tool(name="validate_scene")
    def _validate_scene(game: str, level: str, scene: str) -> str:
        """Valida una scene.json: schema, catalog_id esistenti, icone, bounds, goal."""
        return json.dumps(validate_scene(game, level, scene), ensure_ascii=False, indent=2)

    @mcp.tool(name="render_scene")
    def _render_scene(game: str, level: str, scene: str, max_width: int = 1280):
        """Renderizza una scena completa in PNG (headless, fedele all'engine)."""
        png = render_scene_png(game, level, scene, max_width)
        if Image is not None:
            return Image(data=png, format="png")
        return _save_png_fallback(png, f"{game}_{level}_{scene}")

    @mcp.tool(name="render_asset")
    def _render_asset(catalog_id: str, game: str = "", max_dim: int = 512):
        """Renderizza un singolo asset di catalogo in PNG."""
        png = render_asset_png(catalog_id, game, max_dim)
        if Image is not None:
            return Image(data=png, format="png")
        return _save_png_fallback(png, f"asset_{catalog_id}")

    @mcp.tool(name="build_status")
    def _build_status() -> str:
        """Elenca gli artefatti di build (apk/aab/exe) presenti nel repo."""
        return json.dumps(build_status(), ensure_ascii=False, indent=2)

    return mcp


def _save_png_fallback(png: bytes, name: str) -> str:
    out = Path(tempfile.gettempdir()) / f"hie_{name}.png"
    out.write_bytes(png)
    return f"PNG salvato in: {out}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _selftest() -> int:
    print("[selftest] list_games ...")
    games = list_games()
    print(f"  giochi: {[g['game'] for g in games]}")

    print("[selftest] search_catalog(query='key', limit=3) ...")
    print(f"  {json.dumps(search_catalog(query='key', limit=3), ensure_ascii=False)}")

    target = None
    for g in games:
        for lvl in g["levels"]:
            if lvl["scenes"]:
                target = (g["game"], lvl["level"], lvl["scenes"][0])
                break
        if target:
            break
    if not target:
        print("[selftest] nessuna scena trovata, stop.")
        return 0

    game, level, scene = target
    print(f"[selftest] validate_scene {game}/{level}/{scene} ...")
    v = validate_scene(game, level, scene)
    print(f"  ok={v['ok']} errori={v['error_count']} warning={v['warning_count']} "
          f"oggetti={v['object_count']} bg={v['background_size']}")

    print(f"[selftest] render_scene {game}/{level}/{scene} ...")
    png = render_scene_png(game, level, scene, max_width=900)
    out = Path(tempfile.gettempdir()) / "hie_selftest_scene.png"
    out.write_bytes(png)
    print(f"  PNG {len(png)} byte -> {out}")
    print("[selftest] OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if not _HAS_MCP:
        print("Pacchetto 'mcp' non installato. Esegui: pip install -r requirements-dev.txt",
              file=sys.stderr)
        sys.exit(1)
    _build_server().run()
