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
    ACCENT, BORDER, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
    TOP_BAR_H, STATUS_H,
)
from editor.ui.draw import (
    _button_w, _ui_scale,
    _draw_text, _rect, _button, _in_rect, _scrollbar, _text_wh,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("auditor")

# ─── Costanti layout modale ───────────────────────────────────────────────────
# Modal geometry at UI scale 1.0. The row height and the number of rows are
# derived from the fonts in _auditor_layout(): fixed at 52 px and 7 rows, a
# larger UI scale left a wide empty band under a list that had stopped early,
# and the scroll clamp counted rows that were no longer the visible ones.
_MODAL_W: int = 860
_MODAL_H: int = 620
_ITEM_PAD: int = 14        # padding around the two lines of an issue row
_HEADER_H: int = 56
_FOOTER_H: int = 34

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
                self._TR("aud_i_no_game_dir", "Game folder not found"),
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
                issues.append(self._issue(
                    _SEV_ERR,
                    self._TR("aud_i_scan_aborted",
                             "Audit stopped in '{step}'").format(step=label),
                    str(e)))

        if not issues:
            issues.append(self._issue(
                _SEV_OK,
                self._TR("aud_i_all_good", "No problem found"),
                self._TR("aud_i_all_good_d",
                         "The project '{game}' is sound.").format(
                             game=self._auditor_game_id),
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
                self._TR("aud_i_cfg_missing", "game_config.json is missing"),
                str(cfg_p),
            ))
            return

        try:
            with open(cfg_p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            issues.append(self._issue(
                _SEV_ERR,
                self._TR("aud_i_cfg_broken", "game_config.json: JSON parse error"),
                str(e)))
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
                    self._TR("aud_i_menu_bg", "Menu background is missing"),
                    self._TR("aud_i_ref_not_found",
                             "Reference: {ref}  |  file not found").format(ref=bg),
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
                    self._TR("aud_i_menu_music",
                             "Menu music is missing: {name}").format(
                                 name=Path(m).name),
                    self._TR("aud_i_ref_not_found",
                             "Reference: {ref}  |  file not found").format(ref=m),
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
            issues.append(self._issue(
                _SEV_ERR,
                self._TR("aud_i_catalog_broken",
                         "objects_catalog.json: JSON error"),
                str(e)))
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
                    self._TR("aud_i_png_local",
                             "Local PNG missing (found in the engine): {name}").format(
                                 name=Path(img_rel).name),
                    self._TR("aud_i_id_path", "ID: {oid}  |  {path}").format(
                        oid=obj_id, path=img_rel),
                    repair_fn=_fix_copy,
                ))
            else:
                issues.append(self._issue(
                    _SEV_ERR,
                    self._TR("aud_i_png_gone",
                             "PNG missing everywhere: {name}").format(
                                 name=Path(img_rel).name),
                    self._TR("aud_i_id_path", "ID: {oid}  |  {path}").format(
                        oid=obj_id, path=img_rel),
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
                self._TR("aud_i_scene_missing",
                         "scene.json missing in: {folder}").format(
                             folder=scn_dir.name),
                str(scn_dir),
            ))
            return

        try:
            with open(scn_json, "r", encoding="utf-8") as f:
                sd = json.load(f)
        except Exception as e:
            issues.append(self._issue(
                _SEV_ERR,
                self._TR("aud_i_scene_broken",
                         "scene.json is corrupt: {folder}").format(
                             folder=scn_dir.name),
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
                    self._TR("aud_i_scene_bg",
                             "Scene background is missing: {scene}").format(
                                 scene=scene_label),
                    self._TR("aud_i_expected_file",
                             "Expected file: {path}").format(path=bg),
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
                    self._TR("aud_i_scene_png",
                             "Scene PNG asset is missing: {cid}").format(cid=cat_id),
                    self._TR("aud_i_scene_path",
                             "Scene: {scene}  |  {path}").format(
                                 scene=scene_label, path=img_rel),
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
                    self._TR("aud_i_cid_unknown",
                             "catalog_id does not exist: {cid}").format(cid=cid),
                    self._TR("aud_i_cid_unknown_d",
                             "Scene: {scene}  |  objects {idx}  |  not in the "
                             "merged catalog (the engine drops it)").format(
                                 scene=scene_label, idx=idx_txt),
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
                    self._TR("aud_i_cid_dup",
                             "catalog_id repeated in the scene: {cid}").format(cid=cid),
                    self._TR("aud_i_cid_dup_d",
                             "Scene: {scene}  |  {n} occurrences (legitimate "
                             "sometimes, worth a look)").format(
                                 scene=scene_label, n=n),
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
                    self._TR("aud_i_obj_outside",
                             "Object entirely outside the background: {cid}").format(
                                 cid=cid),
                    self._TR("aud_i_obj_outside_d",
                             "Scene: {scene}  |  object #{i}  |  bbox {bbox} "
                             "vs {bg}").format(
                                 scene=scene_label, i=i,
                                 bbox=f"({left:.0f},{top:.0f} {w:.0f}x{h:.0f})",
                                 bg=f"{bg_w}x{bg_h}"),
                ))
            elif (area - inter) / area > _OOB_PARTIAL_FRAC:
                pct = int(round((area - inter) / area * 100))
                issues.append(self._issue(
                    _SEV_WARN,
                    self._TR("aud_i_obj_partial",
                             "Object partly outside the background: {cid}").format(
                                 cid=cid),
                    self._TR("aud_i_obj_partial_d",
                             "Scene: {scene}  |  object #{i}  |  {pct}% of its "
                             "area outside the {bg} bounds").format(
                                 scene=scene_label, i=i, pct=pct,
                                 bg=f"{bg_w}x{bg_h}"),
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
                self._TR("aud_i_no_objects", "No object in the scene")
                if not objects
                else self._TR("aud_i_no_goal_objects",
                              "{n} objects, none with is_goal on").format(
                                  n=len(objects))
            )
            issues.append(self._issue(
                _SEV_ERR,
                self._TR("aud_i_unsolvable",
                         "Scene cannot be solved (no goal): {scene}").format(
                             scene=scene_label),
                self._TR("aud_i_unsolvable_d",
                         "{detail}  |  the scene can never be completed").format(
                             detail=detail),
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
                    self._TR("aud_i_minigame",
                             "Minigame does not exist: {mid}").format(mid=mid),
                    self._TR("aud_i_minigame_d",
                             "Scene: {scene}  |  object #{i}  |  {path} is "
                             "missing").format(scene=scene_label, i=i,
                                               path=manifest),
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
                    self._TR("aud_i_i18n",
                             "Missing translations [{lang}]: {n} keys").format(
                                 lang=lang, n=len(missing)),
                    self._TR("aud_i_scene_keys",
                             "Scene: {scene}  |  {keys}").format(
                                 scene=scene_label, keys=f"{sample}{extra}"),
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
                    self._TR("aud_i_level_nodir",
                             "Level in the config with no folder: {lvl}").format(
                                 lvl=lvl_id),
                    self._TR("aud_i_level_nodir_d",
                             "game_config.json['levels'] refers to '{lvl}' but "
                             "{path} is missing").format(
                                 lvl=lvl_id, path=levels_dir / lvl_id),
                ))

        # Livelli su disco assenti dal config -> WARN (l'engine li accoda comunque)
        for lvl_id in sorted(disk_levels - set(cfg_levels)):
            issues.append(self._issue(
                _SEV_WARN,
                self._TR("aud_i_level_orphan",
                         "Orphan level (not in game_config): {lvl}").format(
                             lvl=lvl_id),
                self._TR("aud_i_level_orphan_d",
                         "The folder is on disk but not in "
                         "game_config.json['levels']: its order is not guaranteed"),
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
                        self._TR("aud_i_levelcfg_missing",
                                 "level_config.json is missing: {lvl}").format(
                                     lvl=lvl_id),
                        self._TR("aud_i_levelcfg_missing_d",
                                 "Without level_config.json the engine cannot "
                                 "start the level"),
                    ))
                continue
            try:
                with open(lc_p, "r", encoding="utf-8") as f:
                    lc = json.load(f)
            except Exception as e:
                issues.append(self._issue(
                    _SEV_ERR,
                    self._TR("aud_i_levelcfg_broken",
                             "level_config.json is corrupt: {lvl}").format(
                                 lvl=lvl_id),
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
                        self._TR("aud_i_scene_nodir",
                                 "Scene in the config with no folder: {path}").format(
                                     path=f"{lvl_id}/{scn_id}"),
                        self._TR("aud_i_scene_nodir_d",
                                 "level_config.json refers to '{scene}' but "
                                 "{path} (or its scene.json) is missing").format(
                                     scene=scn_id, path=lvl_dir / scn_id),
                    ))
            for scn_id in sorted(disk_scenes - set(cfg_scenes)):
                issues.append(self._issue(
                    _SEV_WARN,
                    self._TR("aud_i_scene_orphan",
                             "Orphan scene (not in level_config): {path}").format(
                                 path=f"{lvl_id}/{scn_id}"),
                    self._TR("aud_i_scene_orphan_d",
                             "A folder with a scene.json is on disk but no "
                             "level_config.json refers to it: it will never be "
                             "played"),
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
                max_scroll = self._auditor_layout(*self.screen.get_size())["max_scroll"]
                self._auditor_scroll = min(self._auditor_scroll + 1, max_scroll)
                return True
            if ev.key == pygame.K_UP:
                self._auditor_scroll = max(0, self._auditor_scroll - 1)
                return True

        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            mx, my = ev.pos
            return self._auditor_click(mx, my)

        elif ev.type == pygame.MOUSEWHEEL:
            max_scroll = self._auditor_layout(*self.screen.get_size())["max_scroll"]
            self._auditor_scroll = max(
                0, min(max_scroll, self._auditor_scroll - ev.y)
            )
            return True

        return False

    def _auditor_click(self, mx: int, my: int) -> bool:
        """Gestisce click sul modale auditor. Restituisce True se consumato."""
        w, h = self.screen.get_size()
        box = self._auditor_layout(w, h)["box"]
        dx, dy = box.x, box.y

        modal_rect = pygame.Rect(dx, dy, box.w, box.h)
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

    def _auditor_layout(self, w: int, h: int) -> dict:
        """Rects and row metrics of the auditor modal, derived once.

        Keys: box, header_h, item_h, list, visible_rows, max_scroll,
        footer_y, rescan, close, badge_x.
        """
        title_h = _text_wh("Ag", "sm")[1]
        detail_h = _text_wh("Ag", "xs")[1]
        item_h = title_h + detail_h + _ITEM_PAD
        # The header stacks the modal title and the project name, the footer one
        # line of hint: both follow the font instead of a fixed 56/34 px, where
        # a larger UI scale made the title and the subtitle overlap and pushed
        # the footer under the status bar.
        header_h = max(_HEADER_H, _text_wh("Ag", "lg")[1] + title_h + 18)
        footer_h = max(_FOOTER_H, detail_h + 18)
        # Never taller than the room between the top bar and the status bar.
        avail_h = h - TOP_BAR_H - STATUS_H - 20
        mw = min(int(round(_MODAL_W * _ui_scale())), w - 40)
        mh = min(int(round(_MODAL_H * _ui_scale())), max(200, avail_h))
        dx = (w - mw) // 2
        dy = TOP_BAR_H + 10 + max(0, (avail_h - mh) // 2)
        list_y = dy + header_h + 12
        list_h = max(item_h, mh - header_h - 12 - footer_h - 12)
        visible = max(1, list_h // item_h)
        rescan_label = self._TR("aud_rescan", "RESCAN")
        rescan_w = _button_w(rescan_label, "sm", min_w=100)
        close_r = pygame.Rect(dx + mw - 42, dy + 12, 28, 28)
        rescan_r = pygame.Rect(close_r.left - rescan_w - 12, dy + 12, rescan_w, 32)
        return {
            "box": pygame.Rect(dx, dy, mw, mh),
            "header_h": header_h,
            "item_h": item_h,
            "title_h": title_h,
            "list": pygame.Rect(dx + 14, list_y, mw - 28, visible * item_h),
            "visible_rows": visible,
            "max_scroll": max(0, len(self._auditor_issues) - visible),
            "footer_y": dy + mh - footer_h + 8,
            "rescan": rescan_r,
            "rescan_label": rescan_label,
            "close": close_r,
            "badge_x": dx + 20,
        }

    def _r_auditor_modal(self, w: int, h: int) -> None:
        """Disegna il modale auditor. Da chiamare solo se _auditor_active."""
        mx, my = pygame.mouse.get_pos()
        geo = self._auditor_layout(w, h)
        box = geo["box"]
        dx, dy, mw, mh = box.x, box.y, box.w, box.h
        self._auditor_scroll = max(0, min(self._auditor_scroll, geo["max_scroll"]))

        self._auditor_hitboxes = {}

        # ── Overlay scuro dietro il modale ───────────────────────────────────
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        # ── Corpo modale ─────────────────────────────────────────────────────
        modal_rect = box
        # Ombra
        _rect(self.screen, (10, 10, 15), (dx + 5, dy + 5, mw, mh), radius=12)
        # Background
        _rect(self.screen, (32, 33, 42), modal_rect, radius=12)
        # Bordo accentato
        _rect(self.screen, ACCENT, modal_rect, 2, radius=12)

        # ── Header ───────────────────────────────────────────────────────────
        hdr_h = geo["header_h"]
        hdr_rect = pygame.Rect(dx, dy, mw, hdr_h)
        _rect(self.screen, (38, 40, 55), hdr_rect, radius=12)
        # Linea separatrice header
        pygame.draw.line(
            self.screen, BORDER,
            (dx + 1, dy + hdr_h), (dx + mw - 1, dy + hdr_h)
        )

        # Titolo e sottotitolo
        title_h = _text_wh("Ag", "lg")[1]
        _draw_text(self.screen, self._TR("aud_title", "PROJECT AUDITOR"), "lg",
                   ACCENT, dx + 20, dy + 8)
        game_label = (self._TR("aud_project", "Project: {game}").format(
            game=self._auditor_game_id) if self._auditor_game_id else "")
        _draw_text(self.screen, game_label, "sm", TXT_DIM, dx + 20,
                   dy + 8 + title_h + 2, mw - 40)

        # Contatore issue
        n_err  = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_ERR)
        n_warn = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_WARN)
        n_ok   = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_OK)
        # Bottone Re-Scan
        rescan_r = geo["rescan"]
        rescan_hov = _in_rect((mx, my), rescan_r)
        _button(self.screen, rescan_r, geo["rescan_label"], rescan_hov, font="sm")
        self._auditor_hitboxes["rescan"] = rescan_r

        # Contatori, allineati a destra del bottone Re-Scan: a offset fissi si
        # sovrapponevano al bottone appena una traduzione li allungava.
        badges = []
        if n_err:
            badges.append((self._TR("aud_count_err", "{0} ERR").format(n_err), ERR_C))
        if n_warn:
            badges.append((self._TR("aud_count_warn", "{0} WARN").format(n_warn), WARN_C))
        if n_ok and not (n_err or n_warn):
            badges.append((self._TR("aud_ok", "OK"), OK_C))
        badge_right = rescan_r.left - 16
        for text, colour in reversed(badges):
            bw, bh = _text_wh(text, "sm")
            _draw_text(self.screen, text, "sm", colour,
                       badge_right - bw, dy + 16)
            badge_right -= bw + 14

        # Bottone chiudi
        close_r = geo["close"]
        close_hov = _in_rect((mx, my), close_r)
        _button(self.screen, close_r, "×", close_hov, danger=True, font="sm")
        self._auditor_hitboxes["close"] = close_r

        # ── Area lista issue ─────────────────────────────────────────────────
        list_rect = geo["list"]
        list_x, list_y = list_rect.x, list_rect.y
        list_w, list_h = list_rect.w, list_rect.h
        item_h = geo["item_h"]
        visible_rows = geo["visible_rows"]

        # Clipping area lista
        self.screen.set_clip(list_rect)

        issues = self._auditor_issues
        for rel_i in range(visible_rows):
            abs_i = rel_i + self._auditor_scroll
            if abs_i >= len(issues):
                break

            issue = issues[abs_i]
            iy = list_y + rel_i * item_h
            sev = issue["severity"]
            sev_col = _SEV_COLORS.get(sev, TXT_DIM)
            repaired = issue.get("repaired", False)

            # Sfondo riga (alternato per leggibilità)
            row_bg = (36, 37, 48) if rel_i % 2 == 0 else (32, 33, 42)
            _rect(self.screen, row_bg, (list_x, iy, list_w, item_h - 2), radius=6)

            if repaired:
                _rect(self.screen, (20, 55, 30), (list_x, iy, list_w, item_h - 2), radius=6)

            # Striscia colorata sinistra (indicatore severità)
            stripe_col = (75, 195, 95) if repaired else sev_col
            _rect(self.screen, stripe_col, (list_x, iy + 4, 3, item_h - 10))

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
                _button(self.screen, btn_r, self._TR("aud_fix_btn", "FIX"), btn_hov, font="xs")
                self._auditor_hitboxes[btn_key] = btn_r
            elif repaired:
                _draw_text(self.screen, self._TR("aud_fixed_badge", "Fixed"), "xs", OK_C,
                           list_x + list_w - 100, iy + 18)

        self.screen.set_clip(None)

        # ── Scrollbar ─────────────────────────────────────────────────────────
        if len(issues) > visible_rows:
            _scrollbar(
                self.screen,
                dx + mw - 10,
                list_y,
                6,
                list_h,
                self._auditor_scroll,
                len(issues),
                visible_rows,
            )

        # ── Footer ────────────────────────────────────────────────────────────
        footer_y = geo["footer_y"]
        pygame.draw.line(
            self.screen, BORDER,
            (dx + 1, footer_y - 8),
            (dx + mw - 1, footer_y - 8),
        )
        hint = self._TR("aud_footer_hint",
                 "ESC or a click outside closes  |  arrows or scroll to move")
        _draw_text(self.screen, hint, "xs", TXT_DIM, dx + 20, footer_y)

        # Info totale
        tot_txt = self._TR("aud_total", "{n} issues found").format(n=len(issues))
        tw, _ = _text_wh(tot_txt, "xs")
        _draw_text(self.screen, tot_txt, "xs", TXT_DIM,
                   dx + mw - tw - 20, footer_y)


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
