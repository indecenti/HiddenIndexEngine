"""
editor/mixins/batch_import.py

BatchImportMixin — import in blocco di PNG come oggetti del catalogo locale.

Flusso: _batch_import_open() -> dialog file multiplo (tkinter) -> modale sullo
stack unificato (editor.modal_stack) con opzioni (rimozione sfondo AI,
auto-ritaglio, stile catalogo, tag comuni) -> worker thread che processa un
file alla volta (rembg + evolved_trim), salva il PNG in
games/<id>/objects/<slug>_icon.png e registra l'entry in objects_catalog.json
con seed i18n. Annulla interrompe dopo il file corrente.

Le funzioni di pipeline (process_image, batch_import_one) sono pure e senza UI:
riusate dal modale "+ Nuovo Oggetto" e testabili headless.
"""

import logging
import re
import threading
import unicodedata
from pathlib import Path
from typing import Optional

import pygame

from editor.constants import (
    LANGS, PANEL, BORDER, BTN, BTN_HO, ACCENT,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.core.io import _load_json, _save_json, _load_catalog
from editor.mixins.img_editor_logic import evolved_trim
from editor.ui.draw import _rect, _draw_text, _in_rect, _text_wh
from editor.ui.widgets import Button, InputBox, ScrollList, WidgetGroup

logger = logging.getLogger(__name__)

# Default catalogo (coerenti con il modale "+ Nuovo Oggetto")
DEFAULT_DETECTION = "circle"
DEFAULT_RADIUS = 30
DEFAULT_HINT_DELAY = 30

# Valori del campo "style" (enum di engine/schemas/catalog_schema.json)
STYLE_CARTOON = "cartoon"
STYLE_LINEART = "line art"

# Stati per riga del batch
ST_WAIT = "In attesa"
ST_RUN = "Elaborazione"
ST_OK = "OK"
ST_ERR = "Errore"
_ST_COLORS = {ST_WAIT: TXT_DIM, ST_RUN: ACCENT, ST_OK: OK_C, ST_ERR: ERR_C}

# Slug: solo ascii minuscolo + underscore
_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_FALLBACK_SLUG = "oggetto"

# Geometria modale
_MODAL_W, _MODAL_H = 660, 560
_PAD = 16
_TITLE_H = 30
_ROW_H = 26
_ROW_GAP = 8
_LIST_ITEM_H = 26
_BTN_W, _BTN_H = 150, 32
_PROGRESS_H = 14
_LOG_LINES = 3
_LOG_LINE_H = 18
_OVERLAY_ALPHA = 150
_STATUS_COL_W = 150
_TOGGLE_W = 210
_STYLE_BTN_W = 110
_STYLE_LABEL_W = 100
_ERR_MSG_MAX = 80
_ROW_BG = (44, 46, 58)
_ROW_BG_HOVER = (55, 60, 80)

# Checkbox condivisa (usata anche dal modale nuovo oggetto)
_CHECKBOX_BOX = 18
_CHECKBOX_GAP = 8


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET DI DISEGNO CONDIVISI
# ─────────────────────────────────────────────────────────────────────────────

def draw_checkbox(surf: pygame.Surface, rect, label: str,
                  checked: bool, enabled: bool = True) -> None:
    """Disegna una checkbox con etichetta; l'hitbox e' l'intero rect."""
    rect = pygame.Rect(rect)
    hovered = enabled and _in_rect(pygame.mouse.get_pos(), rect)
    box = pygame.Rect(rect.x, rect.y + (rect.h - _CHECKBOX_BOX) // 2,
                      _CHECKBOX_BOX, _CHECKBOX_BOX)
    _rect(surf, BTN_HO if hovered else BTN, box, radius=3)
    _rect(surf, ACCENT if checked else BORDER, box, 1, radius=3)
    if checked:
        _rect(surf, ACCENT, box.inflate(-8, -8), radius=2)
    color = (TXT_HI if checked else TXT) if enabled else TXT_DIM
    _, th = _text_wh(label, "sm")
    _draw_text(surf, label, "sm", color, box.right + _CHECKBOX_GAP,
               rect.y + (rect.h - th) // 2, rect.w - _CHECKBOX_BOX - _CHECKBOX_GAP * 2)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PURA (senza UI: riusata da newobj_modal e dai test headless)
# ─────────────────────────────────────────────────────────────────────────────

def rembg_available() -> bool:
    """True se rembg e' importabile (dipendenza opzionale, non nei requirements)."""
    try:
        import rembg        # noqa: F401 — lazy, opzionale
        from PIL import Image  # noqa: F401 — arriva con rembg
        return True
    except ImportError:
        return False


_REMBG_SESSION = None
_REMBG_LOCK = threading.Lock()


def _rembg_session():
    """Sessione rembg riusata tra le chiamate (evita di ricaricare il modello)."""
    global _REMBG_SESSION
    import rembg  # Lazy: dipendenza opzionale, non nei requirements
    with _REMBG_LOCK:
        if _REMBG_SESSION is None and hasattr(rembg, "new_session"):
            _REMBG_SESSION = rembg.new_session()
    return _REMBG_SESSION


def load_rgba(path: Path) -> pygame.Surface:
    """Carica un'immagine come superficie 32 bit SRCALPHA (senza display)."""
    img = pygame.image.load(str(path))
    if img.get_bitsize() == 32 and (img.get_flags() & pygame.SRCALPHA):
        return img
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    return out


def remove_bg_ai(surf: pygame.Surface) -> pygame.Surface:
    """
    Rimozione sfondo AI (rembg, policy di progetto: vedi
    docs/assets/IMAGE_PROCESSING_GUIDELINES.md). Il primo uso puo' scaricare
    i pesi U2-Net. Solleva ImportError se rembg non e' installato.
    """
    import rembg           # Lazy: dipendenza opzionale, non nei requirements
    from PIL import Image  # Lazy: arriva con rembg ma verifichiamo
    raw = pygame.image.tobytes(surf, "RGBA")
    pil_img = Image.frombytes("RGBA", surf.get_size(), raw)
    out = rembg.remove(pil_img, session=_rembg_session()).convert("RGBA")
    # frombytes copia i dati: la superficie resta scrivibile (evolved_trim
    # modifica l'alpha in-place)
    return pygame.image.frombytes(out.tobytes(), out.size, "RGBA")


def process_image(src: Path, remove_bg: bool, autotrim: bool) -> pygame.Surface:
    """Pipeline pura: carica src e applica rimozione sfondo AI e/o auto-ritaglio."""
    surf = load_rgba(src)
    if remove_bg:
        surf = remove_bg_ai(surf)
    if autotrim:
        surf = evolved_trim(surf)
    return surf


def slugify(name: str) -> str:
    """Normalizza un nome file in id catalogo: ascii minuscolo, underscore."""
    ascii_name = (unicodedata.normalize("NFKD", name)
                  .encode("ascii", "ignore").decode("ascii"))
    slug = _SLUG_INVALID_RE.sub("_", ascii_name.lower()).strip("_")
    return slug or _FALLBACK_SLUG


def unique_slug(base: str, taken: set, objects_dir: Path) -> str:
    """Risolve le collisioni (id catalogo o file icona) con suffisso numerico."""
    slug, n = base, 2
    while slug in taken or (objects_dir / f"{slug}_icon.png").exists():
        slug = f"{base}_{n}"
        n += 1
    return slug


def _humanize(slug: str) -> str:
    """Etichetta di default leggibile (es. 'wooden_spoon' -> 'Wooden spoon')."""
    return slug.replace("_", " ").strip().capitalize()


def seed_i18n(game_path: Path, slug: str) -> None:
    """
    Seed della label oggetto (obj_<id>, stessa chiave del flusso newobj) nei
    file lingua del gioco, cosi' il gioco resta distribuibile standalone.
    Non sovrascrive traduzioni esistenti.
    """
    strings_dir = game_path / "strings"
    strings_dir.mkdir(exist_ok=True)
    key = f"obj_{slug}"
    label = _humanize(slug)
    for lang in LANGS:
        p = strings_dir / f"{lang}.json"
        data = _load_json(p)
        if key not in data:
            data[key] = label
            _save_json(p, data)


def batch_import_one(src: Path, game_path: Path, taken_ids: set, *,
                     remove_bg: bool, autotrim: bool,
                     style: str, tags: list) -> dict:
    """
    Importa un singolo file: processa l'immagine, salva il PNG in
    games/<id>/objects/<slug>_icon.png e registra l'entry nel catalogo locale
    (objects_catalog.json) con seed i18n. Funzione pura rispetto alla UI:
    usata dal worker del modale e dai test headless.
    Aggiorna taken_ids con lo slug scelto e ritorna l'entry registrata.
    """
    surf = process_image(src, remove_bg, autotrim)
    objects_dir = game_path / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    slug = unique_slug(slugify(src.stem), taken_ids, objects_dir)
    icon_name = f"{slug}_icon.png"
    pygame.image.save(surf, str(objects_dir / icon_name))

    entry = {
        "id": slug,
        "label_key": f"obj_{slug}",
        "icon": f"objects/{icon_name}",
        "style": style,
        "default_detection": DEFAULT_DETECTION,
        "default_radius": DEFAULT_RADIUS,
        "default_hint_delay": DEFAULT_HINT_DELAY,
        "tags": list(tags),
    }
    cat_path = game_path / "objects_catalog.json"
    cat_data = _load_json(cat_path)
    cat_data.setdefault("objects", []).append(entry)
    if not _save_json(cat_path, cat_data):
        raise RuntimeError(f"Scrittura catalogo fallita: {cat_path}")
    seed_i18n(game_path, slug)
    taken_ids.add(slug)
    return entry


def parse_tags(text: str) -> list:
    """Parsa il campo 'tag comuni': separati da virgola, minuscoli, no duplicati."""
    seen, out = set(), []
    for raw_tag in text.split(","):
        tag = raw_tag.strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _files_dialog(title: str, filetypes: Optional[list] = None,
                  initialdir: Optional[Path] = None) -> list:
    """
    Dialog di selezione file MULTIPLO via tkinter stdlib (stesso pattern di
    editor.core.io._file_dialog, che pero' supporta solo il file singolo).
    """
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
        paths = filedialog.askopenfilenames(**kw)
        root.destroy()
        return [Path(p) for p in paths]
    except Exception:
        logger.exception("Dialog file multiplo non disponibile")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MIXIN
# ─────────────────────────────────────────────────────────────────────────────

class BatchImportMixin:
    """Import in blocco di immagini nel catalogo locale del gioco aperto."""

    def _batch_import_open(self) -> None:
        """Apre il dialog multi-file e il modale di import batch."""
        if not getattr(self, "game_path", None):
            self._status("Apri prima un progetto per l'import batch", WARN_C, 3)
            return
        files = _files_dialog("Scegli le immagini da importare",
                              filetypes=[("Immagini PNG", "*.png")],
                              initialdir=self.game_path)
        if not files:
            return
        self._modal_push(_BatchImportModal(self, files))


# ─────────────────────────────────────────────────────────────────────────────
# MODALE (protocollo stack unificato: handle_event(editor, ev), render(editor))
# ─────────────────────────────────────────────────────────────────────────────

class _BatchImportModal:
    """Lista file con stato per riga, opzioni, progress bar e log."""

    def __init__(self, editor, files: list) -> None:
        self.rows: list = [{"path": Path(p), "status": ST_WAIT, "msg": ""}
                           for p in files]
        self.opt_remove_bg = True
        self.opt_autotrim = True
        self.style = STYLE_CARTOON
        self.running = False
        self.cancel = False
        self.done = 0
        self.imported = 0
        self.imported_ids: list = []
        self.log: list = []

        self.tags_input = InputBox((0, 0, 10, _ROW_H), "",
                                   hint="tag1, tag2, ...", font="sm")
        self.list = ScrollList((0, 0, 10, 10), lambda: self.rows,
                               self._draw_row, item_h=_LIST_ITEM_H)
        self.btn_style_cartoon = Button(
            (0, 0, _STYLE_BTN_W, _ROW_H), "Cartoon",
            lambda: self._set_style(STYLE_CARTOON),
            active_fn=lambda: self.style == STYLE_CARTOON)
        self.btn_style_lineart = Button(
            (0, 0, _STYLE_BTN_W, _ROW_H), "Line art",
            lambda: self._set_style(STYLE_LINEART),
            active_fn=lambda: self.style == STYLE_LINEART)
        self.btn_start = Button((0, 0, _BTN_W, _BTN_H), "AVVIA",
                                lambda: self._start(editor))
        self.btn_close = Button((0, 0, _BTN_W, _BTN_H), "Chiudi",
                                lambda: self._close(editor))
        self.group = WidgetGroup([self.tags_input, self.list,
                                  self.btn_style_cartoon, self.btn_style_lineart,
                                  self.btn_start, self.btn_close])
        # Hitbox checkbox e aree di stato, ricalcolate dal layout
        self._cb_remove_rect = pygame.Rect(0, 0, _TOGGLE_W, _ROW_H)
        self._cb_trim_rect = pygame.Rect(0, 0, _TOGGLE_W, _ROW_H)
        self._progress_rect = pygame.Rect(0, 0, 10, _PROGRESS_H)
        self._log_y = 0

    # ── Stato / worker ───────────────────────────────────────────────────────

    def _log_msg(self, msg: str) -> None:
        logger.info("[BATCH_IMPORT] %s", msg)
        self.log.append(msg)

    def _set_style(self, style: str) -> None:
        if not self.running:
            self.style = style

    def _start(self, editor) -> None:
        """Avvia il worker: un file alla volta, la UI resta reattiva."""
        if self.running:
            return
        if all(r["status"] == ST_OK for r in self.rows):
            self._log_msg("Niente da importare: tutti i file sono gia' OK")
            return
        remove_bg = self.opt_remove_bg
        if remove_bg and not rembg_available():
            remove_bg = False
            self.opt_remove_bg = False
            self._log_msg("rembg non disponibile: rimozione sfondo disattivata")
        elif remove_bg:
            self._log_msg("AI attiva: il primo uso puo' scaricare il modello U2-Net")
        tags = parse_tags(self.tags_input.text)
        self.tags_input.focused = False
        game_path = editor.game_path
        # Id gia' occupati: catalogo unito in memoria + catalogo locale su disco
        taken = {c.get("id") for c in getattr(editor, "catalog", []) if c.get("id")}
        local = _load_json(game_path / "objects_catalog.json")
        taken.update(o.get("id") for o in local.get("objects", []) if o.get("id"))

        self.running = True
        self.cancel = False
        self.done = sum(1 for r in self.rows if r["status"] == ST_OK)
        autotrim = self.opt_autotrim
        style = self.style

        def worker() -> None:
            # Nel worker solo file e superfici locali: nessun accesso alla UI
            for row in self.rows:
                if self.cancel:
                    break
                if row["status"] == ST_OK:
                    continue
                row["status"] = ST_RUN
                row["msg"] = ""
                try:
                    entry = batch_import_one(
                        row["path"], game_path, taken,
                        remove_bg=remove_bg, autotrim=autotrim,
                        style=style, tags=tags)
                    row["status"] = ST_OK
                    row["msg"] = entry["id"]
                    self.imported += 1
                    self.imported_ids.append(entry["id"])
                    self._log_msg(f"OK: {row['path'].name} -> {entry['id']}")
                except Exception as exc:
                    logger.exception("Import fallito: %s", row["path"])
                    row["status"] = ST_ERR
                    row["msg"] = str(exc)[:_ERR_MSG_MAX]
                    self._log_msg(f"Errore: {row['path'].name}")
                self.done += 1
            self._log_msg("Import annullato" if self.cancel else "Import completato")
            self.running = False

        threading.Thread(target=worker, daemon=True, name="batch_import").start()

    def _close(self, editor) -> None:
        """Chiudi (o, durante l'esecuzione, annulla dopo il file corrente)."""
        if self.running:
            self.cancel = True
            self._log_msg("Annullamento: interrompo dopo il file corrente")
            return
        editor._modal_pop(self)
        if self.imported <= 0:
            return
        # Stesso refresh del modale nuovo oggetto: ricarica il catalogo unito
        game_id = getattr(editor, "game_name", None) or editor.game_path.name
        editor.catalog = _load_catalog(game_id)
        # Seed in memoria per l'editor traduzioni gia' caricato (come newobj)
        if getattr(editor, "_lang_data", None):
            for slug in self.imported_ids:
                for lang in editor.LANGS:
                    editor._lang_data.setdefault(lang, {}).setdefault(
                        f"obj_{slug}", "")
        editor._status(
            f"Import batch: {self.imported} oggetti aggiunti al catalogo", OK_C, 4)

    # ── Layout / input / render ──────────────────────────────────────────────

    def _layout(self, w_win: int, h_win: int) -> pygame.Rect:
        panel = pygame.Rect((w_win - _MODAL_W) // 2, (h_win - _MODAL_H) // 2,
                            _MODAL_W, _MODAL_H)
        x = panel.x + _PAD
        inner_w = _MODAL_W - _PAD * 2
        y = panel.y + _PAD + _TITLE_H
        self._cb_remove_rect.update(x, y, _TOGGLE_W, _ROW_H)
        self._cb_trim_rect.update(x + _TOGGLE_W + _PAD, y, _TOGGLE_W, _ROW_H)
        y += _ROW_H + _ROW_GAP
        self.btn_style_cartoon.rect.update(x + _STYLE_LABEL_W, y,
                                           _STYLE_BTN_W, _ROW_H)
        self.btn_style_lineart.rect.update(
            x + _STYLE_LABEL_W + _STYLE_BTN_W + _ROW_GAP, y, _STYLE_BTN_W, _ROW_H)
        y += _ROW_H + _ROW_GAP
        self.tags_input.rect.update(x + _STYLE_LABEL_W, y,
                                    inner_w - _STYLE_LABEL_W, _ROW_H)
        y += _ROW_H + _ROW_GAP
        list_bottom = (panel.bottom - _PAD - _BTN_H - _ROW_GAP
                       - _LOG_LINES * _LOG_LINE_H - _PROGRESS_H - _ROW_GAP * 2)
        self.list.rect.update(x, y, inner_w, max(_LIST_ITEM_H, list_bottom - y))
        self._progress_rect.update(x, list_bottom + _ROW_GAP, inner_w, _PROGRESS_H)
        self._log_y = self._progress_rect.bottom + _ROW_GAP
        self.btn_start.rect.update(x, panel.bottom - _PAD - _BTN_H, _BTN_W, _BTN_H)
        self.btn_close.rect.update(panel.right - _PAD - _BTN_W,
                                   panel.bottom - _PAD - _BTN_H, _BTN_W, _BTN_H)
        return panel

    def handle_event(self, editor, ev) -> bool:
        self._layout(*editor.screen.get_size())
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.tags_input.focused:
                self.tags_input.focused = False
            else:
                self._close(editor)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and not self.running:
            if _in_rect(ev.pos, self._cb_remove_rect):
                self.opt_remove_bg = not self.opt_remove_bg
                return True
            if _in_rect(ev.pos, self._cb_trim_rect):
                self.opt_autotrim = not self.opt_autotrim
                return True
        self.group.handle_event(ev)
        return True

    def _draw_row(self, surf, rect, row, index, hovered) -> None:
        _rect(surf, _ROW_BG_HOVER if hovered else _ROW_BG, rect, radius=4)
        _draw_text(surf, row["path"].name, "sm", TXT, rect.x + 8, rect.y + 5,
                   rect.w - _STATUS_COL_W - _PAD)
        label = row["status"]
        if row["msg"]:
            label = f"{label}: {row['msg']}"
        _draw_text(surf, label, "xs", _ST_COLORS.get(row["status"], TXT_DIM),
                   rect.right - _STATUS_COL_W, rect.y + 7, _STATUS_COL_W - _ROW_GAP)

    def render(self, editor) -> None:
        screen = editor.screen
        w_win, h_win = screen.get_size()
        panel = self._layout(w_win, h_win)
        self.tags_input.enabled = not self.running
        self.btn_start.enabled = not self.running
        self.btn_style_cartoon.enabled = not self.running
        self.btn_style_lineart.enabled = not self.running
        self.btn_close.label = "Annulla" if self.running else "Chiudi"
        self.btn_close.danger = self.running

        overlay = pygame.Surface((w_win, h_win), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, _OVERLAY_ALPHA))
        screen.blit(overlay, (0, 0))
        _rect(screen, PANEL, panel, radius=8)
        _rect(screen, ACCENT, panel, 2, radius=8)
        _draw_text(screen, f"Import Batch Oggetti ({len(self.rows)} file)",
                   "md", TXT_HI, panel.x + _PAD, panel.y + _PAD - 4)

        draw_checkbox(screen, self._cb_remove_rect, "Rimuovi sfondo (AI)",
                      self.opt_remove_bg, enabled=not self.running)
        draw_checkbox(screen, self._cb_trim_rect, "Auto-ritaglio",
                      self.opt_autotrim, enabled=not self.running)
        _draw_text(screen, "Stile:", "sm", TXT_DIM, panel.x + _PAD,
                   self.btn_style_cartoon.rect.y + 6)
        _draw_text(screen, "Tag comuni:", "sm", TXT_DIM, panel.x + _PAD,
                   self.tags_input.rect.y + 6)
        self.group.draw(screen)

        # Progress bar + contatore
        total = len(self.rows)
        _rect(screen, BTN, self._progress_rect, radius=4)
        if total > 0 and self.done > 0:
            fill = self._progress_rect.copy()
            fill.w = max(1, int(round(self._progress_rect.w * self.done / total)))
            _rect(screen, ACCENT, fill, radius=4)
        _rect(screen, BORDER, self._progress_rect, 1, radius=4)
        counter = f"{self.done}/{total}"
        cw, ch = _text_wh(counter, "xs")
        _draw_text(screen, counter, "xs", TXT_HI,
                   self._progress_rect.centerx - cw // 2,
                   self._progress_rect.y + (self._progress_rect.h - ch) // 2)

        # Log: ultimi messaggi (lista, slice atomica sotto GIL)
        ly = self._log_y
        for msg in self.log[-_LOG_LINES:]:
            _draw_text(screen, msg, "xs", TXT_DIM, panel.x + _PAD, ly,
                       _MODAL_W - _PAD * 2)
            ly += _LOG_LINE_H
