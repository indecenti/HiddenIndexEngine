"""
editor/mixins/auditor.py

AuditorMixin — Project Auditor: scansiona un gioco selezionato alla ricerca
di referenze rotte (PNG mancanti, background assenti, musica orfana) e propone
riparazioni non distruttive con conferma esplicita dell'utente.

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
            self._status("Seleziona prima un gioco", WARN_C, 2)
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

        if not game_path.exists():
            issues.append(self._issue(
                _SEV_ERR,
                f"Cartella gioco non trovata",
                str(game_path),
            ))
            return

        # 1. game_config.json
        self._scan_game_config(game_path, issues)

        # 2. Catalogo oggetti locale
        self._scan_catalog(game_path, issues)

        # 3. Livelli e scene
        self._scan_levels(game_path, issues)

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
        if isinstance(music_list, str):
            music_list = [music_list]
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

        # Background scena
        bg = sd.get("background", "")
        if bg:
            bg_full = scn_dir / bg
            if not bg_full.exists():
                scene_label = f"{scn_dir.parent.name}/{scn_dir.name}"

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

        # Oggetti scena — controlla icon/image vs catalogo locale+engine
        for obj in sd.get("objects", []):
            cat_id = obj.get("catalog_id", "?")
            # Recupera il path immagine dal catalogo in memoria se disponibile
            img_rel = self._auditor_resolve_img(cat_id)
            if img_rel is None:
                continue  # Non sappiamo il path, skip silenzioso

            img_local = scn_dir.parent.parent.parent / img_rel  # games/<g>/
            img_engine = self.base_path / "engine" / "assets" / img_rel

            if not img_local.exists() and not img_engine.exists():
                scene_label = f"{scn_dir.parent.name}/{scn_dir.name}"
                issues.append(self._issue(
                    _SEV_WARN,
                    f"Asset scena PNG mancante: {cat_id}",
                    f"Scena: {scene_label}  |  {img_rel}",
                ))

    def _auditor_resolve_img(self, cat_id: str) -> str | None:
        """
        Cerca il path immagine relativo di cat_id nel catalogo in memoria.
        Restituisce None se non trovato (evita accessi disco ridondanti).
        """
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
            self._status(f"Riparato: {issue['title']}", OK_C, 3)
            logger.info(f"[AUDITOR] Issue riparata: {issue['title']}")
        except Exception as e:
            logger.error(f"[AUDITOR] Errore riparazione: {e}")
            self._status(f"Errore riparazione: {e}", ERR_C, 4)

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
        _draw_text(self.screen, "PROJECT AUDITOR", "lg", ACCENT, dx + 20, dy + 10)
        game_label = f"Progetto: {self._auditor_game_id}" if self._auditor_game_id else ""
        _draw_text(self.screen, game_label, "sm", TXT_DIM, dx + 20, dy + 34)

        # Contatore issue
        n_err  = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_ERR)
        n_warn = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_WARN)
        n_ok   = sum(1 for i in self._auditor_issues if i["severity"] == _SEV_OK)
        badge_x = dx + _MODAL_W - 330
        badge_y = dy + 16
        if n_err:
            _draw_text(self.screen, f"● {n_err} ERR", "sm", ERR_C, badge_x, badge_y)
        if n_warn:
            _draw_text(self.screen, f"  ▲ {n_warn} WARN", "sm", WARN_C, badge_x + 80, badge_y)
        if n_ok and not (n_err or n_warn):
            _draw_text(self.screen, f"✔ OK", "sm", OK_C, badge_x, badge_y)

        # Bottone Re-Scan
        rescan_r = pygame.Rect(dx + _MODAL_W - 210, dy + 12, 100, 32)
        rescan_hov = _in_rect((mx, my), rescan_r)
        _button(self.screen, rescan_r, "↺ RISCAN", rescan_hov, font="sm")
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
                _button(self.screen, btn_r, "✔ RIPARA", btn_hov, font="xs")
                self._auditor_hitboxes[btn_key] = btn_r
            elif repaired:
                _draw_text(self.screen, "Riparato ✔", "xs", OK_C,
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
