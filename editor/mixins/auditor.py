"""
editor/mixins/auditor.py

AuditorMixin — Project Auditor: scansiona un gioco selezionato alla ricerca
di referenze rotte (PNG mancanti, background assenti, musica orfana) e propone
riparazioni non distruttive con conferma esplicita dell'utente.

Check di scena aggiuntivi (non distruttivi, nessun repair automatico):
- catalog_id inesistenti nel catalogo unito (ERR) e duplicati in scena (WARN);
- bounding box oggetti fuori dai bounds del background (ERR/WARN);
- scena senza oggetti goal, quindi non risolvibile (ERR);
- minigame_trigger verso minigiochi senza manifest (ERR);
- completezza traduzioni per le lingue del gioco (WARN);
- coerenza game_config['levels'] / level_config vs cartelle su disco (ERR/WARN).

NON modifica dati senza click esplicito sui pulsanti di riparazione.
NON disegna mai fuori dai bounds del suo modale.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI,
    OK_C, ERR_C, WARN_C,
    PANEL, BG,
)
from editor.ui.draw import (
    _draw_text, _rect, _button, _in_rect, _scrollbar, _text_wh,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("auditor")

# ─── Costanti layout modale ───────────────────────────────────────────────────
_MODAL_W: int = 860
_MODAL_H: int = 620
_ITEM_H: int = 52          # altezza riga issue
_VISIBLE_ROWS: int = 7     # quante righe stanno nella list area

# Tipi di severità
_SEV_ERR  = "error"
_SEV_WARN = "warn"
_SEV_OK   = "ok"

_SEV_COLORS = {
    _SEV_ERR:  ERR_C,
    _SEV_WARN: WARN_C,
    _SEV_OK:   OK_C,
}

# ─── Costanti check di scena (allineate a engine/scene_loader) ────────────────
_OOB_PARTIAL_FRAC: float = 0.30          # frazione area fuori background per WARN
_DEFAULT_RADIUS: float = 30.0            # default engine per detection circle
_I18N_SAMPLE_MAX: int = 5                # max chiavi mancanti mostrate nel dettaglio
_VIDEO_EXTS: tuple[str, ...] = (".mp4", ".mov", ".mkv")


def _as_bool(v: object) -> bool:
    """Replica _to_bool di engine/scene_loader (bool, stringhe 'true'/'1'/'yes')."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


class AuditorMixin:
    """
    Mixin che aggiunge il Project Auditor all'editor.

    Stato gestito:
        _auditor_active     : bool  — modale aperto/chiuso
        _auditor_game_id    : str   — gioco sotto analisi
        _auditor_issues     : list  — lista dict issue trovate
        _auditor_scroll     : int   — scroll lista issue (in righe)
        _auditor_running    : bool  — scansione in corso
        _auditor_hitboxes   : dict  — hitbox pulsanti repair (per click)
    """

    # ─────────────────────────────────────────────────────────────────────────
    # INIT
    # ─────────────────────────────────────────────────────────────────────────

    def _auditor_init(self) -> None:
        """Inizializza lo stato del modale auditor (chiamato da __init__)."""
        self._auditor_active: bool = False
        self._auditor_game_id: str = ""
        self._auditor_issues: list = []
        self._auditor_scroll: int = 0
        self._auditor_running: bool = False
        self._auditor_hitboxes: dict = {}
        # Cache di scansione (ripopolate a ogni audit da _auditor_scan)
        self._auditor_cat_index: dict[str, dict] = {}
        self._auditor_cat_ids: set[str] = set()
        self._auditor_bg_cache: dict[str, tuple[int, int] | None] = {}
        self._auditor_strings_cache: dict[str, dict] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # APERTURA
    # ─────────────────────────────────────────────────────────────────────────

    def _auditor_open(self, game_id: str = "") -> None:
        """Apre il modale e lancia la scansione sul gioco indicato."""
        if not game_id:
            # Prova a usare il gioco corrente o quello selezionato in dashboard
            if self.gs_sel_game is not None and self.gs_sel_game < len(self.gs_games):
                game_id = self.gs_games[self.gs_sel_game]
            elif getattr(self, "game_path", None):
                game_id = self.game_path.name
        if not game_id:
            self._status(self._TR("aud_select_game_first", "Select a game first"), WARN_C, 2)
            return
        self._auditor_game_id = game_id
        self._auditor_issues = []
        self._auditor_scroll = 0
        self._auditor_hitboxes = {}
        self._auditor_active = True
        self._auditor_running = True
        self._auditor_scan()
        self._auditor_running = False
        logger.info(f"[AUDITOR] Scansione completata: {len(self._auditor_issues)} issue trovate")

    # ─────────────────────────────────────────────────────────────────────────
    # SCANSIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _auditor_scan(self) -> None:
        """
        Scansiona il gioco e popola self._auditor_issues.
        Ogni issue è un dict con:
            severity  : str  (_SEV_ERR | _SEV_WARN | _SEV_OK)
            title     : str  — breve descrizione
            detail    : str  — path / contesto aggiuntivo
            repair_fn : callable | None — funzione riparazione (None = manuale)
            repaired  : bool — già riparata in questa sessione
        """
        issues = self._auditor_issues
        game_path = self.base_path / "games" / self._auditor_game_id

        # Catalogo del gioco IN AUDIT (non quello eventualmente aperto nell'editor):
        # senza questo, _auditor_resolve_img userebbe self.catalog (gioco diverso o
        # vuoto) e il controllo dei PNG mancanti verrebbe saltato silenziosamente.
        try:
            from editor.core.io import _load_catalog
            self._auditor_catalog = _load_catalog(self._auditor_game_id)
        except Exception as e:
            logger.error(f"[AUDITOR] Catalogo di {self._auditor_game_id} non caricato: {e}")
            self._auditor_catalog = getattr(self, "catalog", [])

        # Indice id -> entry del catalogo unito + cache per i check di scena.
        self._auditor_cat_index = {
            str(o.get("id")): o
            for o in self._auditor_catalog
            if isinstance(o, dict) and o.get("id")
        }
        self._auditor_cat_ids = set(self._auditor_cat_index)
        self._auditor_bg_cache = {}
        self._auditor_strings_cache = {}

        if not game_path.exists():
            issues.append(self._issue(
                _SEV_ERR,
                f"Cartella gioco non trovata",
                str(game_path),
            ))
            return

        # Ogni scansione e' isolata: un JSON malformato in una non deve far abortire
        # l'intero audit (e crashare l'app), ma diventare un issue segnalato.
        for label, scan_fn in (
            ("game_config", lambda: self._scan_game_config(game_path, issues)),
            ("catalogo", lambda: self._scan_catalog(game_path, issues)),
            ("livelli/scene", lambda: self._scan_levels(game_path, issues)),
        ):
            try:
                scan_fn()
            except Exception as e:
                logger.error(f"[AUDITOR] Errore scansione {label}: {e}")
                issues.append(self._issue(_SEV_ERR, f"Audit interrotto in '{label}'", str(e)))

        if not issues:
            issues.append(self._issue(
                _SEV_OK,
                "Nessun problema trovato",
                f"Il progetto '{self._auditor_game_id}' è integro.",
            ))

    # ── Helpers scansione ─────────────────────────────────────────────────────

    @staticmethod
    def _issue(
        severity: str,
        title: str,
        detail: str = "",
        repair_fn=None,
    ) -> dict:
        return {
            "severity": severity,
            "title": title,
            "detail": detail,
            "repair_fn": repair_fn,
            "repaired": False,
        }

    def _scan_game_config(self, game_path: Path, issues: list) -> None:
        cfg_p = game_path / "game_config.json"
        if not cfg_p.exists():
            issues.append(self._issue(
                _SEV_ERR,
                "game_config.json mancante",
                str(cfg_p),
            ))
            return

        try:
            with open(cfg_p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            issues.append(self._issue(_SEV_ERR, "game_config.json: errore parsing JSON", str(e)))
            return

        # Background menu
        bg = cfg.get("menu", {}).get("background", "")
        if bg:
            bg_full = game_path / bg
            if not bg_full.exists():
                def _fix_bg(gp=game_path, c=cfg, cp=cfg_p, b=bg) -> None:
                    c["menu"]["background"] = ""
                    _safe_save_json(cp, c)
                    logger.info(f"[AUDITOR] Rimossa referenza background mancante: {b}")

                issues.append(self._issue(
                    _SEV_ERR,
                    "Background menu mancante",
                    f"Referenza: {bg}  →  File non trovato",
                    repair_fn=_fix_bg,
                ))

        # Musica menu
        music_list = cfg.get("menu", {}).get("music", [])
        # Coercizione difensiva: la chiave puo' essere presente ma null o di tipo errato.
        if not isinstance(music_list, list):
            music_list = [music_list] if isinstance(music_list, str) else []
        for m in music_list:
            m_full = game_path / m
            if not m_full.exists():
                def _fix_music(gp=game_path, c=cfg, cp=cfg_p, missing=m) -> None:
                    ml = c["menu"].get("music", [])
                    if isinstance(ml, str):
                        ml = [ml]
                    ml = [x for x in ml if x != missing]
                    c["menu"]["music"] = ml
                    _safe_save_json(cp, c)
                    logger.info(f"[AUDITOR] Rimossa voce musica mancante: {missing}")

                issues.append(self._issue(
                    _SEV_WARN,
                    f"Musica menu mancante: {Path(m).name}",
                    f"Referenza: {m}  →  File non trovato",
                    repair_fn=_fix_music,
                ))

    def _scan_catalog(self, game_path: Path, issues: list) -> None:
        cat_p = game_path / "objects_catalog.json"
        if not cat_p.exists():
            return  # Catalogo locale opzionale, non è un errore

        try:
            with open(cat_p, "r", encoding="utf-8") as f:
                cat = json.load(f)
        except Exception as e:
            issues.append(self._issue(_SEV_ERR, "objects_catalog.json: errore JSON", str(e)))
            return

        for obj in cat.get("objects", []):
            obj_id = obj.get("id", "?")
            img_rel = obj.get("image") or obj.get("icon", "")
            if not img_rel:
                continue

            img_local = game_path / img_rel
            if img_local.exists():
                continue

            # Cerca nel pool globale engine
            engine_p = self.base_path / "engine" / "assets" / img_rel
            if engine_p.exists():
                def _fix_copy(src=engine_p, dst=img_local) -> None:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    logger.info(f"[AUDITOR] PNG copiato da engine: {dst.name}")

                issues.append(self._issue(
                    _SEV_WARN,
                    f"PNG locale mancante (trovato in engine): {Path(img_rel).name}",
                    f"ID: {obj_id}  |  {img_rel}",
                    repair_fn=_fix_copy,
                ))
            else:
                issues.append(self._issue(
                    _SEV_ERR,
                    f"PNG completamente mancante: {Path(img_rel).name}",
                    f"ID: {obj_id}  |  {img_rel}",
                ))

    def _scan_levels(self, game_path: Path, issues: list) -> None:
        self._scan_levels_config(game_path, issues)

        levels_dir = game_path / "levels"
        if not levels_dir.exists():
            return

        for lvl_dir in sorted(levels_dir.iterdir()):
            if not lvl_dir.is_dir():
                continue
            for scn_dir in sorted(lvl_dir.iterdir()):
                if not scn_dir.is_dir():
                    continue
                self._scan_scene(scn_dir, issues)

    def _scan_scene(self, scn_dir: Path, issues: list) -> None:
        scn_json = scn_dir / "scene.json"
        if not scn_json.exists():
            issues.append(self._issue(
                _SEV_WARN,
                f"scene.json mancante in: {scn_dir.name}",
                str(scn_dir),
            ))
            return

        try:
            with open(scn_json, "r", encoding="utf-8") as f:
                sd = json.load(f)
        except Exception as e:
            issues.append(self._issue(
                _SEV_ERR,
                f"scene.json corrotto: {scn_dir.name}",
                str(e),
            ))
            return

        scene_label = f"{scn_dir.parent.name}/{scn_dir.name}"
        game_path = scn_dir.parent.parent.parent  # games/<g>/

        # Background scena
        bg = sd.get("background", "")
        if bg:
            bg_full = scn_dir / bg
            if not bg_full.exists():
                def _fix_bg_scene(sj=scn_json, s=sd, b=bg) -> None:
                    s["background"] = ""
                    _safe_save_json(sj, s)
                    logger.info(f"[AUDITOR] Rimosso background scena mancante: {b}")

                issues.append(self._issue(
                    _SEV_ERR,
                    f"Background scena mancante: {scene_label}",
                    f"File atteso: {bg}",
                    repair_fn=_fix_bg_scene,
                ))

        objects = sd.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        objects = [o for o in objects if isinstance(o, dict)]

        # Oggetti scena — controlla icon/image vs catalogo locale+engine
        for obj in objects:
            cat_id = obj.get("catalog_id", "?")
            # Recupera il path immagine dal catalogo in memoria se disponibile
            img_rel = self._auditor_resolve_img(cat_id)
            if img_rel is None:
                continue  # Non sappiamo il path, skip silenzioso

            img_local = game_path / img_rel
            img_engine = self.base_path / "engine" / "assets" / img_rel

            if not img_local.exists() and not img_engine.exists():
                issues.append(self._issue(
                    _SEV_WARN,
                    f"Asset scena PNG mancante: {cat_id}",
                    f"Scena: {scene_label}  |  {img_rel}",
                ))

        # Check aggiuntivi (tutti non distruttivi, nessun repair automatico)
        self._scan_scene_catalog_ids(scene_label, objects, issues)
        self._scan_scene_bounds(scn_dir, scene_label, sd, objects, issues)
        self._scan_scene_goals(scene_label, sd, objects, issues)
        self._scan_scene_minigames(scene_label, objects, issues)
        self._scan_scene_i18n(game_path, scene_label, objects, issues)

    # ── Check aggiuntivi di scena ─────────────────────────────────────────────

    def _scan_scene_catalog_ids(
        self, scene_label: str, objects: list, issues: list
    ) -> None:
        """catalog_id inesistenti nel catalogo unito (ERR) e duplicati (WARN)."""
        cat_ids = self._auditor_cat_ids
        if cat_ids:
            # Con catalogo vuoto (caricamento fallito) il check salterebbe tutto:
            # meglio nessun rilievo che un falso ERR per ogni oggetto.
            missing: dict[str, list[int]] = {}
            for i, obj in enumerate(objects):
                cid = str(obj.get("catalog_id", ""))
                if cid and cid not in cat_ids:
                    missing.setdefault(cid, []).append(i)
            for cid, idxs in missing.items():
                idx_txt = ", ".join(f"#{n}" for n in idxs)
                issues.append(self._issue(
                    _SEV_ERR,
                    f"catalog_id inesistente: {cid}",
                    f"Scena: {scene_label}  |  oggetti {idx_txt}  |  "
                    "assente dal catalogo unito (l'engine lo scarta)",
                ))

        counts: dict[str, int] = {}
        for obj in objects:
            cid = str(obj.get("catalog_id", ""))
            if cid:
                counts[cid] = counts.get(cid, 0) + 1
        for cid, n in counts.items():
            if n > 1:
                issues.append(self._issue(
                    _SEV_WARN,
                    f"catalog_id duplicato nella scena: {cid}",
                    f"Scena: {scene_label}  |  {n} occorrenze "
                    "(legittimo in alcuni casi, ma da verificare)",
                ))

    def _scan_scene_bounds(
        self, scn_dir: Path, scene_label: str, sd: dict, objects: list, issues: list
    ) -> None:
        """
        Bounding box oggetti vs dimensioni background.
        ERR se completamente fuori, WARN se fuori oltre _OOB_PARTIAL_FRAC dell'area.
        """
        size = self._scene_bg_size(scn_dir, sd.get("background", ""))
        if size is None:
            return
        bg_w, bg_h = size
        for i, obj in enumerate(objects):
            box = self._object_bbox(obj)
            if box is None:
                continue
            left, top, w, h = box
            area = w * h
            if area <= 0:
                continue
            ix = min(left + w, float(bg_w)) - max(left, 0.0)
            iy = min(top + h, float(bg_h)) - max(top, 0.0)
            inter = max(0.0, ix) * max(0.0, iy)
            cid = obj.get("catalog_id", "?")
            if inter <= 0:
                issues.append(self._issue(
                    _SEV_ERR,
                    f"Oggetto completamente fuori dal background: {cid}",
                    f"Scena: {scene_label}  |  oggetto #{i}  |  bbox "
                    f"({left:.0f},{top:.0f} {w:.0f}x{h:.0f}) vs {bg_w}x{bg_h}",
                ))
            elif (area - inter) / area > _OOB_PARTIAL_FRAC:
                pct = int(round((area - inter) / area * 100))
                issues.append(self._issue(
                    _SEV_WARN,
                    f"Oggetto parzialmente fuori dal background: {cid}",
                    f"Scena: {scene_label}  |  oggetto #{i}  |  {pct}% dell'area "
                    f"fuori dai bounds {bg_w}x{bg_h}",
                ))

    @staticmethod
    def _object_bbox(obj: dict) -> tuple[float, float, float, float] | None:
        """
        Bounding box (left, top, w, h) in spazio pixel nativo del background.
        Convenzione ancore: rect (x,y)=top-left; circle/mask (x,y)=centro con
        dimensione width|radius*2 (come engine/scene_loader).
        """
        try:
            x = float(obj.get("x", 0))
            y = float(obj.get("y", 0))
            width = float(obj.get("width", 0) or 0)
            height = float(obj.get("height", 0) or 0)
            radius = float(obj.get("radius", _DEFAULT_RADIUS) or _DEFAULT_RADIUS)
        except (TypeError, ValueError):
            return None
        dt = str(obj.get("detection_type", ""))
        if dt == "rect":
            if width <= 0 or height <= 0:
                return None  # dimensioni assenti: bbox non calcolabile
            return (x, y, width, height)
        w = width if width > 0 else radius * 2.0
        h = height if height > 0 else radius * 2.0
        return (x - w / 2.0, y - h / 2.0, w, h)

    def _scene_bg_size(self, scn_dir: Path, bg_name: str) -> tuple[int, int] | None:
        """Dimensioni del background con cache per path. None se non determinabili."""
        if not bg_name or bg_name.lower().endswith(_VIDEO_EXTS):
            return None
        bg_path = scn_dir / bg_name
        key = str(bg_path)
        cache = self._auditor_bg_cache
        if key in cache:
            return cache[key]
        size: tuple[int, int] | None = None
        if bg_path.exists():
            try:
                size = pygame.image.load(str(bg_path)).get_size()
            except Exception as e:
                logger.warning(
                    f"[AUDITOR] Dimensioni background non lette ({bg_path.name}): {e}"
                )
        cache[key] = size
        return size

    def _scan_scene_goals(
        self, scene_label: str, sd: dict, objects: list, issues: list
    ) -> None:
        """Scena senza oggetti goal: il giocatore non puo' completarla (ERR)."""
        if _as_bool(sd.get("auto_random_finds", False)) and objects:
            return  # i goal vengono assegnati a runtime dallo shuffle dell'engine
        goals = sum(1 for o in objects if _as_bool(o.get("is_goal", True)))
        if goals == 0:
            detail = (
                "Nessun oggetto nella scena" if not objects
                else f"{len(objects)} oggetti, nessuno con is_goal attivo"
            )
            issues.append(self._issue(
                _SEV_ERR,
                f"Scena non risolvibile (nessun goal): {scene_label}",
                f"{detail}  |  la scena non puo' essere completata",
            ))

    def _scan_scene_minigames(
        self, scene_label: str, objects: list, issues: list
    ) -> None:
        """minigame_trigger verso minigiochi senza manifest.json in engine (ERR)."""
        seen: set[str] = set()
        for i, obj in enumerate(objects):
            trig = obj.get("minigame_trigger")
            if not isinstance(trig, dict):
                continue
            mid = str(trig.get("minigame_id", "")).strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            manifest = self.base_path / "engine" / "minigames" / mid / "manifest.json"
            if not manifest.exists():
                issues.append(self._issue(
                    _SEV_ERR,
                    f"Minigioco inesistente: {mid}",
                    f"Scena: {scene_label}  |  oggetto #{i}  |  manca {manifest}",
                ))

    def _scan_scene_i18n(
        self, game_path: Path, scene_label: str, objects: list, issues: list
    ) -> None:
        """
        Completezza traduzioni: per ogni lingua in games/<id>/strings/ verifica
        che la chiave label di ogni oggetto (label_key da catalogo, fallback
        'obj_<catalog_id>') esista non vuota nelle stringhe del gioco o, in
        fallback come da LanguageManager, in engine/assets/strings/ (WARN).
        """
        strings_dir = game_path / "strings"
        if not strings_dir.exists():
            return
        langs = sorted(p.stem for p in strings_dir.glob("*.json"))
        if not langs:
            return

        # Chiavi label richieste dagli oggetti della scena. I catalog_id
        # inesistenti sono esclusi: gia' segnalati come ERR dal check dedicato.
        keys: set[str] = set()
        for obj in objects:
            cid = str(obj.get("catalog_id", ""))
            if not cid or (self._auditor_cat_ids and cid not in self._auditor_cat_ids):
                continue
            entry = self._auditor_cat_index.get(cid, {})
            keys.add(entry.get("label_key") or f"obj_{cid}")
        if not keys:
            return

        engine_strings_dir = self.base_path / "engine" / "assets" / "strings"
        for lang in langs:
            game_str = self._auditor_strings(strings_dir / f"{lang}.json")
            engine_str = self._auditor_strings(engine_strings_dir / f"{lang}.json")
            missing = sorted(
                k for k in keys
                if not str(game_str.get(k, "") or "").strip()
                and not str(engine_str.get(k, "") or "").strip()
            )
            if missing:
                sample = ", ".join(missing[:_I18N_SAMPLE_MAX])
                extra = "" if len(missing) <= _I18N_SAMPLE_MAX else ", ..."
                issues.append(self._issue(
                    _SEV_WARN,
                    f"Traduzioni mancanti [{lang}]: {len(missing)} chiavi",
                    f"Scena: {scene_label}  |  {sample}{extra}",
                ))

    def _auditor_strings(self, path: Path) -> dict:
        """Carica un file stringhe JSON con cache per audit ({} se assente/corrotto)."""
        key = str(path)
        cache = self._auditor_strings_cache
        if key in cache:
            return cache[key]
        data: dict = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception as e:
                logger.warning(f"[AUDITOR] Stringhe non lette ({path.name}): {e}")
        cache[key] = data
        return data

    # ── Coerenza levels config ────────────────────────────────────────────────

    def _scan_levels_config(self, game_path: Path, issues: list) -> None:
        """
        Coerenza tra game_config.json['levels'], i level_config.json e le
        cartelle su disco: voci config senza cartella (ERR), livelli/scene
        presenti su disco ma non registrati (WARN, orfani).
        """
        levels_dir = game_path / "levels"
        disk_levels: set[str] = set()
        if levels_dir.exists():
            disk_levels = {d.name for d in levels_dir.iterdir() if d.is_dir()}

        cfg_levels: list[str] = []
        cfg_p = game_path / "game_config.json"
        if cfg_p.exists():
            try:
                with open(cfg_p, "r", encoding="utf-8") as f:
                    raw = json.load(f).get("levels", [])
                if isinstance(raw, list):
                    cfg_levels = [str(x) for x in raw]
            except Exception:
                return  # parsing gia' segnalato da _scan_game_config

        # Voci di game_config['levels'] senza cartella su disco -> ERR
        for lvl_id in cfg_levels:
            if lvl_id not in disk_levels:
                issues.append(self._issue(
                    _SEV_ERR,
                    f"Livello in config senza cartella: {lvl_id}",
                    f"game_config.json['levels'] referenzia '{lvl_id}' "
                    f"ma manca {levels_dir / lvl_id}",
                ))

        # Livelli su disco assenti dal config -> WARN (l'engine li accoda comunque)
        for lvl_id in sorted(disk_levels - set(cfg_levels)):
            issues.append(self._issue(
                _SEV_WARN,
                f"Livello orfano (non in game_config): {lvl_id}",
                "Cartella presente su disco ma assente da "
                "game_config.json['levels']: ordine non garantito",
            ))

        # Coerenza scene per livello: level_config.json vs cartelle scena
        for lvl_id in sorted(disk_levels):
            lvl_dir = levels_dir / lvl_id
            lc_p = lvl_dir / "level_config.json"
            disk_scenes = {
                d.name for d in lvl_dir.iterdir()
                if d.is_dir() and (d / "scene.json").exists()
            }
            if not lc_p.exists():
                if lvl_id in cfg_levels:
                    issues.append(self._issue(
                        _SEV_ERR,
                        f"level_config.json mancante: {lvl_id}",
                        "Senza level_config.json il livello non e' "
                        "avviabile dall'engine",
                    ))
                continue
            try:
                with open(lc_p, "r", encoding="utf-8") as f:
                    lc = json.load(f)
            except Exception as e:
                issues.append(self._issue(
                    _SEV_ERR,
                    f"level_config.json corrotto: {lvl_id}",
                    str(e),
                ))
                continue
            cfg_scenes = [
                str(s.get("id", "")) for s in lc.get("scenes", [])
                if isinstance(s, dict) and s.get("id")
            ]
            for scn_id in cfg_scenes:
                if scn_id not in disk_scenes:
                    issues.append(self._issue(
                        _SEV_ERR,
                        f"Scena in config senza cartella: {lvl_id}/{scn_id}",
                        f"level_config.json referenzia '{scn_id}' ma manca "
                        f"{lvl_dir / scn_id} (o il suo scene.json)",
                    ))
            for scn_id in sorted(disk_scenes - set(cfg_scenes)):
                issues.append(self._issue(
                    _SEV_WARN,
                    f"Scena orfana (non in level_config): {lvl_id}/{scn_id}",
                    "Cartella con scene.json presente su disco ma non "
                    "referenziata da level_config.json: non verra' mai giocata",
                ))

    def _auditor_resolve_img(self, cat_id: str) -> str | None:
        """
        Cerca il path immagine relativo di cat_id nel catalogo in memoria.
        Restituisce None se non trovato (evita accessi disco ridondanti).
        """
        cat = getattr(self, "_auditor_catalog", None)
        if cat is None:
            cat = getattr(self, "catalog", [])
        for item in cat:
            if item.get("id") == cat_id:
                return item.get("image") or item.get("icon") or None
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # RIPARAZIONE
    # ─────────────────────────────────────────────────────────────────────────

    def _auditor_repair(self, issue_idx: int) -> None:
        """Esegue la funzione di riparazione per l'issue indicata."""
        issues = self._auditor_issues
        if not (0 <= issue_idx < len(issues)):
            return
        issue = issues[issue_idx]
        if issue.get("repaired") or issue.get("repair_fn") is None:
            return
        try:
            issue["repair_fn"]()
            issue["repaired"] = True
            self._status(self._TR("aud_fixed", "Fixed: {0}").format(issue['title']), OK_C, 3)
            logger.info(f"[AUDITOR] Issue riparata: {issue['title']}")
            # Se il gioco riparato e' quello aperto nell'editor, lo stato in memoria
            # e' ora disallineato dal disco: invalidiamo la cache scene e avvisiamo,
            # cosi' l'utente ricarica prima che un salvataggio reintroduca la referenza.
            if self._auditor_game_id == getattr(self, "game_name", None):
                try:
                    from editor.core.io import _SCENE_DATA_CACHE
                    _SCENE_DATA_CACHE.clear()
                except Exception:
                    pass
                self._status(self._TR("aud_fixed_reload", "Fixed: reload the scene/game to apply it in the editor"), WARN_C, 5)
        except Exception as e:
            logger.error(f"[AUDITOR] Errore riparazione: {e}")
            self._status(self._TR("aud_fix_error", "Repair error: {0}").format(e), ERR_C, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # EVENTI
    # ─────────────────────────────────────────────────────────────────────────

    def _auditor_handle_event(self, ev: pygame.event.Event) -> bool:
        """
        Gestisce eventi per il modale auditor.
        Restituisce True se l'evento è stato consumato.
        """
        if not self._auditor_active:
            return False

        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self._auditor_active = False
                return True
            if ev.key == pygame.K_DOWN:
                max_scroll = max(0, len(self._auditor_issues) - _VISIBLE_ROWS)
                self._auditor_scroll = min(self._auditor_scroll + 1, max_scroll)
                return True
            if ev.key == pygame.K_UP:
                self._auditor_scroll = max(0, self._auditor_scroll - 1)
                return True

        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            mx, my = ev.pos
            return self._auditor_click(mx, my)

        elif ev.type == pygame.MOUSEWHEEL:
            max_scroll = max(0, len(self._auditor_issues) - _VISIBLE_ROWS)
            self._auditor_scroll = max(
                0, min(max_scroll, self._auditor_scroll - ev.y)
            )
            return True

        return False

    def _auditor_click(self, mx: int, my: int) -> bool:
        """Gestisce click sul modale auditor. Restituisce True se consumato."""
        w, h = self.screen.get_size()
        dx = (w - _MODAL_W) // 2
        dy = (h - _MODAL_H) // 2

        modal_rect = pygame.Rect(dx, dy, _MODAL_W, _MODAL_H)
        if not _in_rect((mx, my), modal_rect):
            # Click fuori modale: chiudi
            self._auditor_active = False
            return True

        # Bottone chiusura
        close_r = self._auditor_hitboxes.get("close")
        if close_r and _in_rect((mx, my), close_r):
            self._auditor_active = False
            return True

        # Bottone re-scan
        rescan_r = self._auditor_hitboxes.get("rescan")
        if rescan_r and _in_rect((mx, my), rescan_r):
            self._auditor_open(self._auditor_game_id)
            return True

        # Bottoni repair individuali
        for key, rect in self._auditor_hitboxes.items():
            if key.startswith("repair_"):
                idx_str = key[len("repair_"):]
                if idx_str.isdigit() and _in_rect((mx, my), rect):
                    self._auditor_repair(int(idx_str))
                    return True

        return True  # Click dentro il modale: sempre consumato

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_auditor_modal(self, w: int, h: int) -> None:
        """Disegna il modale auditor. Da chiamare solo se _auditor_active."""
        mx, my = pygame.mouse.get_pos()
        dx = (w - _MODAL_W) // 2
        dy = (h - _MODAL_H) // 2

        self._auditor_hitboxes = {}

        # ── Overlay scuro dietro il modale ───────────────────────────────────
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        # ── Corpo modale ─────────────────────────────────────────────────────
        modal_rect = pygame.Rect(dx, dy, _MODAL_W, _MODAL_H)
        # Ombra
        _rect(self.screen, (10, 10, 15), (dx + 5, dy + 5, _MODAL_W, _MODAL_H), radius=12)
        # Background
        _rect(self.screen, (32, 33, 42), modal_rect, radius=12)
        # Bordo accentato
        _rect(self.screen, ACCENT, modal_rect, 2, radius=12)

        # ── Header ───────────────────────────────────────────────────────────
        hdr_h = 56
        hdr_rect = pygame.Rect(dx, dy, _MODAL_W, hdr_h)
        _rect(self.screen, (38, 40, 55), hdr_rect, radius=12)
        # Linea separatrice header
        pygame.draw.line(
            self.screen, BORDER,
            (dx + 1, dy + hdr_h), (dx + _MODAL_W - 1, dy + hdr_h)
        )

        # Titolo e sottotitolo
        _draw_text(self.screen, self._TR("aud_title", "PROJECT AUDITOR"), "lg", ACCENT, dx + 20, dy + 10)
        game_label = f"Progetto: {self._auditor_game_id}" if self._auditor_game_id else ""
        _draw_text(self.screen, game_label, "sm", TXT_DIM, dx + 20, dy + 34)

        # Contatore issue
        n_err  = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_ERR)
        n_warn = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_WARN)
        n_ok   = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_OK)
        badge_x = dx + _MODAL_W - 330
        badge_y = dy + 16
        if n_err:
            _draw_text(self.screen, self._TR("aud_count_err", "● {0} ERR").format(n_err), "sm", ERR_C, badge_x, badge_y)
        if n_warn:
            _draw_text(self.screen, self._TR("aud_count_warn", "  ▲ {0} WARN").format(n_warn), "sm", WARN_C, badge_x + 80, badge_y)
        if n_ok and not (n_err or n_warn):
            _draw_text(self.screen, self._TR("aud_ok", "✔ OK"), "sm", OK_C, badge_x, badge_y)

        # Bottone Re-Scan
        rescan_r = pygame.Rect(dx + _MODAL_W - 210, dy + 12, 100, 32)
        rescan_hov = _in_rect((mx, my), rescan_r)
        _button(self.screen, rescan_r, self._TR("aud_rescan", "↺ RESCAN"), rescan_hov, font="sm")
        self._auditor_hitboxes["rescan"] = rescan_r

        # Bottone chiudi
        close_r = pygame.Rect(dx + _MODAL_W - 42, dy + 12, 28, 28)
        close_hov = _in_rect((mx, my), close_r)
        _button(self.screen, close_r, "×", close_hov, danger=True, font="sm")
        self._auditor_hitboxes["close"] = close_r

        # ── Area lista issue ─────────────────────────────────────────────────
        list_y = dy + hdr_h + 12
        list_h = _VISIBLE_ROWS * _ITEM_H
        list_x = dx + 14
        list_w = _MODAL_W - 28

        # Clipping area lista
        self.screen.set_clip(pygame.Rect(list_x, list_y, list_w, list_h))

        issues = self._auditor_issues
        for rel_i in range(_VISIBLE_ROWS):
            abs_i = rel_i + self._auditor_scroll
            if abs_i >= len(issues):
                break

            issue = issues[abs_i]
            iy = list_y + rel_i * _ITEM_H
            sev = issue["severity"]
            sev_col = _SEV_COLORS.get(sev, TXT_DIM)
            repaired = issue.get("repaired", False)

            # Sfondo riga (alternato per leggibilità)
            row_bg = (36, 37, 48) if rel_i % 2 == 0 else (32, 33, 42)
            _rect(self.screen, row_bg, (list_x, iy, list_w, _ITEM_H - 2), radius=6)

            if repaired:
                _rect(self.screen, (20, 55, 30), (list_x, iy, list_w, _ITEM_H - 2), radius=6)

            # Striscia colorata sinistra (indicatore severità)
            stripe_col = (75, 195, 95) if repaired else sev_col
            _rect(self.screen, stripe_col, (list_x, iy + 4, 3, _ITEM_H - 10))

            # Testo issue
            title_col = (160, 220, 160) if repaired else TXT_HI
            _draw_text(self.screen, issue["title"], "sm", title_col,
                       list_x + 14, iy + 7, list_w - 140)
            _draw_text(self.screen, issue["detail"], "xs", TXT_DIM,
                       list_x + 14, iy + 27, list_w - 140)

            # Bottone riparazione (solo se c'è una repair_fn e non ancora riparata)
            if issue.get("repair_fn") and not repaired:
                btn_r = pygame.Rect(list_x + list_w - 120, iy + 10, 112, 30)
                # Store key using absolute index
                btn_key = f"repair_{abs_i}"
                btn_hov = _in_rect((mx, my), btn_r)
                _button(self.screen, btn_r, self._TR("aud_fix_btn", "✔ FIX"), btn_hov, font="xs")
                self._auditor_hitboxes[btn_key] = btn_r
            elif repaired:
                _draw_text(self.screen, self._TR("aud_fixed_badge", "Fixed ✔"), "xs", OK_C,
                           list_x + list_w - 100, iy + 18)

        self.screen.set_clip(None)

        # ── Scrollbar ─────────────────────────────────────────────────────────
        if len(issues) > _VISIBLE_ROWS:
            _scrollbar(
                self.screen,
                dx + _MODAL_W - 10,
                list_y,
                6,
                list_h,
                self._auditor_scroll,
                len(issues),
                _VISIBLE_ROWS,
            )

        # ── Footer ────────────────────────────────────────────────────────────
        footer_y = dy + hdr_h + list_h + 24
        pygame.draw.line(
            self.screen, BORDER,
            (dx + 1, footer_y - 8),
            (dx + _MODAL_W - 1, footer_y - 8),
        )
        hint = "ESC / click fuori per chiudere  •  ↑↓ o scroll per navigare"
        _draw_text(self.screen, hint, "xs", TXT_DIM, dx + 20, footer_y)

        # Info totale
        tot_txt = f"{len(issues)} issue trovate"
        tw, _ = _text_wh(tot_txt, "xs")
        _draw_text(self.screen, tot_txt, "xs", TXT_DIM,
                   dx + _MODAL_W - tw - 20, footer_y)


# ─── Utility ──────────────────────────────────────────────────────────────────

def _safe_save_json(path: Path, data: dict) -> None:
    """Scrittura atomica JSON con backup .bak preventivo."""
    import os
    tmp = path.with_suffix(".tmp")
    try:
        bak = path.with_suffix(".bak")
        if path.exists():
            shutil.copy2(str(path), str(bak))
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp), str(path))
    except Exception as e:
        logger.error(f"[AUDITOR] Errore scrittura atomica {path}: {e}")
        raise
