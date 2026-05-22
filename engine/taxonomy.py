"""
engine/taxonomy.py

Sistema di lookup multilingua per i tag del catalogo.

I tag-id sono identificatori lowercase snake_case (es. 'legno', 'natale').
Per ogni tag la taxonomy definisce traduzioni nelle 5 lingue supportate
(it / en / fr / es / de) + categoria opzionale.

Le immagini RIMANGONO sul filesystem — questa classe lavora solo con
metadati testuali. Lo schema è validato in engine/schemas/taxonomy_schema.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from engine.utils import get_resource_path

log = logging.getLogger(__name__)

SUPPORTED_LANGS: tuple[str, ...] = ("it", "en", "fr", "es", "de")


class TaxonomyDB:
    """
    Indice in-memory della taxonomy con lookup O(1).

    Uso tipico::

        tax = load_taxonomy()
        tax.label("legno", "en")           -> "Wood"   (se tradotto)
        tax.label("legno", "fr")           -> "Legno"  (fallback IT se manca FR)
        tax.category("legno")              -> "Materiale" (oppure None)
        tax.all_tags()                     -> {"legno", "metallo", ...}
        tax.tags_by_category()["Materiale"] -> ["legno", "metallo", ...]
    """

    def __init__(self, raw: dict) -> None:
        self._version: str = str(raw.get("version", "1.0"))
        self._categories: list[str] = list(raw.get("categories", []))

        # tag_id -> { it, en, fr, es, de, cat }
        self._tags: dict[str, dict] = {}
        for tag_id, defn in (raw.get("tags") or {}).items():
            if not isinstance(defn, dict):
                continue
            self._tags[tag_id] = defn

        # Indice secondario: cat -> [tag_id, ...]
        self._by_cat: dict[str, list[str]] = {}
        for tag_id, defn in self._tags.items():
            cat = defn.get("cat") or "Generale"
            self._by_cat.setdefault(cat, []).append(tag_id)
        for lst in self._by_cat.values():
            lst.sort()

        log.debug("TaxonomyDB caricata: %d tag, %d categorie",
                  len(self._tags), len(self._by_cat))

    # ── Lookup principali ────────────────────────────────────────────────

    def label(self, tag_id: str, lang: str = "it", *, fallback_lang: str = "it") -> str:
        """
        Traduzione di un tag nella lingua richiesta.
        Catena di fallback: lang -> fallback_lang -> tag_id stesso.
        """
        defn = self._tags.get(tag_id)
        if not defn:
            return tag_id
        # 1. lingua richiesta
        v = defn.get(lang, "")
        if v:
            return v
        # 2. fallback lingua (default IT, che è quella più popolata)
        v = defn.get(fallback_lang, "")
        if v:
            return v
        # 3. tag stesso
        return tag_id

    def category(self, tag_id: str) -> Optional[str]:
        defn = self._tags.get(tag_id)
        if not defn:
            return None
        return defn.get("cat") or None

    def has(self, tag_id: str) -> bool:
        return tag_id in self._tags

    # ── Enumerazione ─────────────────────────────────────────────────────

    def all_tags(self) -> set[str]:
        return set(self._tags.keys())

    def all_categories(self) -> list[str]:
        """Categorie ufficiali (campo `categories` del JSON) + scoperte dinamicamente."""
        explicit = set(self._categories)
        from_tags = set(self._by_cat.keys())
        return sorted(explicit | from_tags)

    def tags_by_category(self) -> dict[str, list[str]]:
        return {cat: list(ids) for cat, ids in self._by_cat.items()}

    def labels_for(self, lang: str) -> dict[str, str]:
        """Dict tag_id -> label nella lingua richiesta (con fallback IT)."""
        return {tid: self.label(tid, lang) for tid in self._tags}

    # ── Audit ────────────────────────────────────────────────────────────

    def audit_completeness(self, langs: Iterable[str] = SUPPORTED_LANGS) -> dict[str, list[str]]:
        """
        Per ciascuna lingua, restituisce i tag senza traduzione (campo mancante o vuoto).
        Ritorna {lang: [tag_id, ...]}. IT è quasi sempre presente per definizione.
        """
        report: dict[str, list[str]] = {l: [] for l in langs}
        for tid, defn in self._tags.items():
            for lang in langs:
                v = defn.get(lang)
                if not v:
                    report[lang].append(tid)
        for lang, lst in report.items():
            lst.sort()
        return report

    @property
    def version(self) -> str:
        return self._version

    def __len__(self) -> int:
        return len(self._tags)

    def __contains__(self, tag_id: str) -> bool:
        return tag_id in self._tags


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------

_TAXONOMY_CACHE: Optional[TaxonomyDB] = None


def load_taxonomy(*, force_reload: bool = False) -> TaxonomyDB:
    """
    Carica `engine/data/tags_taxonomy.json`. Cached per default — passa
    force_reload=True per ricaricare (utile dopo edit nell'editor).

    Se il file manca, ritorna una TaxonomyDB vuota (non-fatal: il catalogo
    può comunque funzionare, solo i tag non sono localizzati).
    """
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is not None and not force_reload:
        return _TAXONOMY_CACHE

    path = Path(get_resource_path("engine", "data", "tags_taxonomy.json"))
    raw: dict = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Validazione opzionale non-fatal
            try:
                from engine.json_validator import validate as _validate
                errors = _validate(raw, "taxonomy", source_path=str(path))
                if errors:
                    log.warning("Taxonomy: %d violazioni schema (vedi log)", len(errors))
            except ImportError:
                pass
        except (json.JSONDecodeError, OSError) as e:
            log.error("Errore caricamento taxonomy '%s': %s", path, e)
    else:
        log.warning("Taxonomy non trovata: %s — uso DB vuota", path)

    _TAXONOMY_CACHE = TaxonomyDB(raw)
    return _TAXONOMY_CACHE


# ---------------------------------------------------------------------------
# CLI di self-test
# ---------------------------------------------------------------------------

def main() -> int:
    tax = load_taxonomy(force_reload=True)
    print(f"version={tax.version}  tag_totali={len(tax)}")
    print(f"categorie ({len(tax.all_categories())}): {tax.all_categories()[:10]}...")

    # Esempi
    samples = ["legno", "metallo", "natale", "musica", "nonexistent_tag"]
    print("\nesempi di lookup:")
    for lang in SUPPORTED_LANGS:
        print(f"  [{lang}] " + "  ".join(f"{s}={tax.label(s, lang)!r}" for s in samples))

    # Audit completezza
    print("\naudit completezza traduzioni:")
    report = tax.audit_completeness()
    for lang, missing in report.items():
        pct_done = (1 - len(missing) / max(len(tax), 1)) * 100
        print(f"  {lang}: {len(missing):4d} mancanti / {len(tax)} totali  ({pct_done:5.1f}% completo)")
    return 0


if __name__ == "__main__":
    import sys
    # Permetti l'esecuzione diretta: python engine/taxonomy.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
