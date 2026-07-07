"""
editor/core/asset_catalog.py

AssetCatalog — strato dati condiviso dei modali asset dell'editor
(background, musica, video). Unifica la logica prima triplicata con
divergenze (rilievo B-H17): scansione directory, catalogo tag persistente,
ricerca per nome/tag, rename con validazione, soft-delete via cestino,
import file e cache miniature su disco caricata in thread.

Formato catalogo su disco (unificato, scritto con safe_write_json):
    { "<nome_file>": { "tags": ["tag1", ...], ...metadati extra } }

In lettura sono accettati anche formati legacy:
    { "<nome_file>": ["tag1", ...] }              (lista diretta di tag)
    { "<nome_file>": "tag1, tag2" }               (stringa CSV di tag)
    { "<nome_file>": {"tags": "tag1, tag2"} }     (campo tags come CSV)
Alla prima riscrittura il file viene normalizzato nel formato unificato;
i metadati extra (es. "duration" per la musica) vengono preservati.

Qui vive SOLO lo strato dati: nessuna dipendenza dallo stato dell'editor.
La UI (layout, input, rendering) resta nei mixin dei modali.
"""

import json
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import pygame

from engine.utils import get_logger, safe_delete, safe_write_json

logger = get_logger(__name__)

# Caratteri vietati nei nomi file (Windows + separatori di path).
INVALID_NAME_CHARS: frozenset[str] = frozenset('/\\:*?"<>|')
# Sottocartella (dentro root_dir) della cache miniature su disco.
THUMB_CACHE_DIRNAME: str = ".thumbs"
# Estensioni caricabili direttamente come immagine dal generatore di default.
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
# Numero massimo di suggerimenti tag restituiti di default.
DEFAULT_SUGGESTION_LIMIT: int = 5

# Firma del generatore di miniature: nome relativo -> Surface oppure None
# (None = nessuna miniatura per questo asset, es. file audio).
ThumbGenerator = Callable[[str], Optional[pygame.Surface]]


class AssetCatalog:
    """Catalogo di asset su disco con tag persistenti e miniature in cache.

    I nomi degli asset sono path relativi a `root_dir` in forma POSIX
    (es. "sfondo.png" oppure "video/intro.mp4" con recursive=True).
    """

    def __init__(self, root_dir: Path, extensions: Sequence[str],
                 catalog_filename: str, *, recursive: bool = False,
                 thumb_size: Optional[tuple[int, int]] = None) -> None:
        self.root_dir = Path(root_dir)
        self.extensions = frozenset(e.lower() for e in extensions)
        self.catalog_path = self.root_dir / catalog_filename
        self.recursive = recursive
        self.thumb_size = thumb_size
        # Dati catalogo: { nome: {"tags": [...], ...extra} }
        self._data: dict[str, dict[str, Any]] = {}
        # Lista file su disco (ordinata). NB: mutata in-place da
        # rename/delete/import cosi' i riferimenti esterni restano coerenti.
        self._files: list[str] = []
        # Unione di tutti i tag del catalogo, per i suggerimenti.
        self._library_tags: list[str] = []
        # Miniature in RAM (protette da lock: il caricamento avviene in thread).
        self._thumbnails: dict[str, pygame.Surface] = {}
        self._thumb_lock = threading.Lock()
        self._thumb_loading = False

    # ──────────────────────────────────────────────────────────────────
    # Persistenza catalogo (tag + metadati)
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        """Normalizza i tag da qualsiasi formato legacy a lista di stringhe."""
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",")]
        elif isinstance(value, (list, tuple)):
            parts = [str(p).strip() for p in value]
        else:
            return []
        return [p for p in parts if p]

    @classmethod
    def _normalize_entry(cls, value: Any) -> dict[str, Any]:
        """Normalizza una entry legacy nel formato unificato {"tags": [...], ...}."""
        if isinstance(value, dict):
            entry = dict(value)
            if "tags" in entry:
                entry["tags"] = cls._normalize_tags(entry["tags"])
            return entry
        if isinstance(value, (list, tuple, str)):
            return {"tags": cls._normalize_tags(value)}
        return {}

    def load(self) -> None:
        """Carica (ri-carica) il catalogo da disco, normalizzando i formati legacy."""
        data: dict[str, dict[str, Any]] = {}
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data = {str(k): self._normalize_entry(v) for k, v in raw.items()}
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("AssetCatalog: catalogo non leggibile %s: %s",
                               self.catalog_path, e)
        self._data = data
        self._refresh_library_tags()

    def save(self) -> bool:
        """Salva il catalogo su disco in modo atomico (safe_write_json)."""
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            ok = safe_write_json(self.catalog_path, self._data, indent=2,
                                 ensure_ascii=False)
        except OSError as e:
            logger.warning("AssetCatalog: salvataggio catalogo fallito %s: %s",
                           self.catalog_path, e)
            return False
        if ok:
            self._refresh_library_tags()
        else:
            logger.warning("AssetCatalog: salvataggio catalogo fallito: %s",
                           self.catalog_path)
        return ok

    # ──────────────────────────────────────────────────────────────────
    # File su disco
    # ──────────────────────────────────────────────────────────────────

    def refresh(self) -> list[str]:
        """Riscansiona la directory e restituisce la lista ordinata dei file.

        La lista restituita e' quella interna: le operazioni successive
        (rename/delete/import) la mutano in-place mantenendola coerente.
        """
        names: list[str] = []
        if not self.root_dir.exists():
            logger.warning("AssetCatalog: cartella asset non trovata: %s", self.root_dir)
            self._files[:] = []
            return self._files
        iterator = self.root_dir.rglob("*") if self.recursive else self.root_dir.glob("*")
        for f in iterator:
            if not f.is_file() or f.suffix.lower() not in self.extensions:
                continue
            if f.name == self.catalog_path.name:
                continue
            rel = f.relative_to(self.root_dir)
            # Salta le cartelle nascoste (es. cache miniature .thumbs)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            names.append(rel.as_posix())
        self._files[:] = sorted(names)
        return self._files

    @property
    def files(self) -> list[str]:
        """Lista corrente dei file (vista interna, non modificarla dall'esterno)."""
        return self._files

    def search(self, text: str = "", tags: Optional[Sequence[str]] = None,
               tag_label_fn: Optional[Callable[[str], str]] = None) -> list[str]:
        """Filtra i file per testo (nome o tag) e/o per insieme di tag richiesti.

        `tag_label_fn` traduce un tag-id nella label mostrata all'utente
        (es. TagManager.get_label): se fornita, il testo viene cercato
        nelle label invece che negli id grezzi.
        """
        query = (text or "").lower().strip()
        wanted = {t.lower() for t in (tags or []) if t}
        if not query and not wanted:
            return list(self._files)
        out: list[str] = []
        for name in self._files:
            entry_tags = self.get_tags(name)
            if wanted and not wanted.issubset({t.lower() for t in entry_tags}):
                continue
            if query:
                shown = ([tag_label_fn(t) for t in entry_tags]
                         if tag_label_fn else entry_tags)
                tags_str = " ".join(shown).lower()
                if query not in name.lower() and query not in tags_str:
                    continue
            out.append(name)
        return out

    # ──────────────────────────────────────────────────────────────────
    # Tag
    # ──────────────────────────────────────────────────────────────────

    def get_tags(self, name: str) -> list[str]:
        """Tag correnti dell'asset (copia, sicura da modificare)."""
        return list(self._data.get(name, {}).get("tags", []))

    def set_tags(self, name: str, tags: Iterable[str], *, save: bool = True) -> bool:
        """Sostituisce i tag dell'asset (dedup + ordinati) e persiste."""
        entry = self._data.setdefault(name, {})
        entry["tags"] = sorted({t.strip() for t in tags if t and t.strip()})
        return self.save() if save else True

    def add_tag(self, name: str, tag: str, *, save: bool = True) -> bool:
        """Aggiunge un tag all'asset. Ritorna False se vuoto o gia' presente."""
        tag = (tag or "").strip()
        if not tag:
            return False
        current = self.get_tags(name)
        if tag in current:
            return False
        current.append(tag)
        return self.set_tags(name, current, save=save)

    def remove_tag(self, name: str, tag: str, *, save: bool = True) -> bool:
        """Rimuove un tag dall'asset. Ritorna False se non presente."""
        current = self.get_tags(name)
        if tag not in current:
            return False
        current.remove(tag)
        return self.set_tags(name, current, save=save)

    @property
    def library_tags(self) -> list[str]:
        """Tutti i tag unici presenti nel catalogo (per i suggerimenti)."""
        return self._library_tags

    def suggest_tags(self, prefix: str, exclude: Iterable[str] = (),
                     limit: int = DEFAULT_SUGGESTION_LIMIT) -> list[str]:
        """Suggerimenti di tag esistenti che iniziano con `prefix`."""
        prefix = (prefix or "").strip().lower()
        if not prefix:
            return []
        excluded = {e.strip().lower() for e in exclude}
        return [t for t in self._library_tags
                if t.lower().startswith(prefix) and t.lower() not in excluded][:limit]

    def _refresh_library_tags(self) -> None:
        tags: set[str] = set()
        for entry in self._data.values():
            tags.update(entry.get("tags", []))
        self._library_tags = sorted(tags)

    # ──────────────────────────────────────────────────────────────────
    # Metadati extra per asset (es. duration per la musica)
    # ──────────────────────────────────────────────────────────────────

    def get_entry_value(self, name: str, key: str, default: Any = None) -> Any:
        """Legge un metadato extra dell'asset (es. "duration")."""
        return self._data.get(name, {}).get(key, default)

    def set_entry_value(self, name: str, key: str, value: Any, *,
                        save: bool = False) -> bool:
        """Scrive un metadato extra dell'asset; con save=True persiste subito."""
        self._data.setdefault(name, {})[key] = value
        return self.save() if save else True

    # ──────────────────────────────────────────────────────────────────
    # Operazioni sui file (rename / delete / import)
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def is_valid_stem(stem: str) -> bool:
        """True se `stem` e' un nome file valido (non vuoto, senza caratteri vietati)."""
        stem = (stem or "").strip()
        return bool(stem) and not any(ch in INVALID_NAME_CHARS for ch in stem)

    def rename(self, old_name: str, new_stem: str) -> Optional[str]:
        """Rinomina un asset mantenendo estensione e sottocartella.

        Ritorna il nuovo nome relativo, oppure None se il nuovo nome non e'
        valido, e' identico, il file di destinazione esiste gia' o la rename
        su disco fallisce. Sposta anche entry di catalogo e miniature.
        """
        stem = (new_stem or "").strip()
        if not self.is_valid_stem(stem):
            return None
        old_rel = Path(old_name)
        new_name = old_rel.with_name(stem + old_rel.suffix).as_posix()
        if new_name == old_name:
            return None
        src, dst = self.root_dir / old_rel, self.root_dir / new_name
        if not src.exists() or dst.exists():
            return None
        try:
            src.rename(dst)
        except OSError as e:
            logger.warning("AssetCatalog: rename fallita %s -> %s: %s",
                           old_name, new_name, e)
            return None
        if old_name in self._data:
            self._data[new_name] = self._data.pop(old_name)
        self.save()
        if old_name in self._files:
            self._files[self._files.index(old_name)] = new_name
        with self._thumb_lock:
            if old_name in self._thumbnails:
                self._thumbnails[new_name] = self._thumbnails.pop(old_name)
        # Sposta anche la miniatura su disco (best effort)
        old_cache = self._thumb_cache_path(old_name)
        new_cache = self._thumb_cache_path(new_name)
        try:
            if old_cache.exists() and not new_cache.exists():
                old_cache.rename(new_cache)
        except OSError:
            pass
        return new_name

    def delete(self, name: str, reason: str = "user_delete_asset") -> bool:
        """Soft-delete: sposta l'asset nel cestino .editor_trash/ (safe_delete).

        Recuperabile per 7 giorni e tracciato in .editor_audit.log.
        Aggiorna lista file, catalogo (con save) e miniature.
        """
        p = self.root_dir / name
        if p.exists() and not safe_delete(p, reason=reason):
            logger.warning("AssetCatalog: delete fallita per '%s'", name)
            return False
        if name in self._files:
            self._files.remove(name)
        self._data.pop(name, None)
        self.save()
        with self._thumb_lock:
            self._thumbnails.pop(name, None)
        try:
            self._thumb_cache_path(name).unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def import_file(self, src_path: Path | str) -> Optional[str]:
        """Copia un file esterno nella root del catalogo con nome univoco.

        Ritorna il nome assegnato, oppure None se il file non esiste,
        l'estensione non e' gestita o la copia fallisce.
        """
        src = Path(src_path)
        if not src.exists() or src.suffix.lower() not in self.extensions:
            return None
        target, count = src.name, 1
        while (self.root_dir / target).exists():
            target = f"{src.stem}_{count}{src.suffix}"
            count += 1
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(self.root_dir / target))
        except OSError as e:
            logger.warning("AssetCatalog: import fallito per %s: %s", src, e)
            return None
        if target not in self._files:
            self._files.append(target)
            self._files.sort()
        return target

    # ──────────────────────────────────────────────────────────────────
    # Miniature (cache RAM + disco, caricate in thread)
    # ──────────────────────────────────────────────────────────────────

    def get_thumbnail(self, name: str) -> Optional[pygame.Surface]:
        """Miniatura in RAM per l'asset, se gia' caricata (thread-safe)."""
        with self._thumb_lock:
            return self._thumbnails.get(name)

    @property
    def loading_thumbs(self) -> bool:
        """True se il thread di caricamento miniature e' attivo."""
        return self._thumb_loading

    def _thumb_cache_path(self, name: str) -> Path:
        # I nomi possono contenere sottocartelle: appiattiti per il file di cache
        safe_name = name.replace("/", "__")
        return self.root_dir / THUMB_CACHE_DIRNAME / f"{safe_name}.png"

    def _default_thumb_generator(self, name: str) -> Optional[pygame.Surface]:
        """Generatore di default: carica l'immagine e la scala a thumb_size."""
        if self.thumb_size is None or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
            return None
        raw = pygame.image.load(str(self.root_dir / name))
        return pygame.transform.smoothscale(raw, self.thumb_size)

    def start_thumbnail_thread(self, generator: Optional[ThumbGenerator] = None,
                               should_continue: Optional[Callable[[], bool]] = None,
                               on_thumbnail: Optional[Callable[[str], None]] = None) -> bool:
        """Avvia (se non gia' attivo) il thread che carica le miniature mancanti.

        `generator(name)` produce la Surface per gli asset senza cache disco
        (default: caricamento immagine + smoothscale). `should_continue()`
        permette di interrompere il lavoro (es. modale chiusa). `on_thumbnail`
        viene chiamata (dal thread) quando una miniatura diventa disponibile.
        """
        if self.thumb_size is None or self._thumb_loading:
            return False
        self._thumb_loading = True
        threading.Thread(
            target=self._thumbnail_task,
            args=(generator or self._default_thumb_generator,
                  should_continue, on_thumbnail),
            daemon=True,
        ).start()
        return True

    def _thumbnail_task(self, generator: ThumbGenerator,
                        should_continue: Optional[Callable[[], bool]],
                        on_thumbnail: Optional[Callable[[str], None]]) -> None:
        cache_dir = self.root_dir / THUMB_CACHE_DIRNAME
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for name in list(self._files):
                if should_continue is not None and not should_continue():
                    break
                with self._thumb_lock:
                    if name in self._thumbnails:
                        continue
                try:
                    thumb = self._load_cached_thumb(name)
                    if thumb is None:
                        thumb = generator(name)
                        if thumb is not None:
                            if self.thumb_size and thumb.get_size() != self.thumb_size:
                                thumb = pygame.transform.smoothscale(thumb, self.thumb_size)
                            pygame.image.save(thumb, str(self._thumb_cache_path(name)))
                    if thumb is not None:
                        with self._thumb_lock:
                            self._thumbnails[name] = thumb
                        if on_thumbnail is not None:
                            on_thumbnail(name)
                except Exception as e:
                    logger.debug("AssetCatalog: miniatura fallita per %s: %s", name, e)
        finally:
            self._thumb_loading = False

    def _load_cached_thumb(self, name: str) -> Optional[pygame.Surface]:
        """Carica la miniatura dalla cache disco; se corrotta la elimina."""
        cache_path = self._thumb_cache_path(name)
        if not cache_path.exists():
            return None
        try:
            thumb = pygame.image.load(str(cache_path))
        except Exception:
            # Cache corrotta: la eliminiamo per rigenerarla dall'originale
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        try:
            return thumb.convert_alpha()
        except pygame.error:
            # Display non inizializzato (es. test headless): surface non convertita
            return thumb
