"""
editor/core/tags.py

TagManager — Gestore centralizzato della tassonomia dei tag.
Responsabile della persistenza, normalizzazione e harvesting dai cataloghi.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Any

logger = logging.getLogger(__name__)

class TagManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.taxonomy_path = base_path / "engine" / "data" / "tags_taxonomy.json"
        self.tags: Dict[str, Dict[str, Any]] = {}
        self.version = "1.0"
        
        # Carica il registro esistente o lo crea
        self.load()

    def load(self):
        """Carica la tassonomia dal file JSON."""
        if self.taxonomy_path.exists():
            try:
                with open(self.taxonomy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tags = data.get("tags", {})
                    self.version = data.get("version", "1.0")
                logger.info(f"[TagManager] Caricati {len(self.tags)} tag dal registro.")
            except Exception as e:
                logger.error(f"[TagManager] Errore caricamento tassonomia: {e}")
                self.tags = {}
        else:
            logger.info("[TagManager] Registro non trovato. Verrà creato al primo salvataggio.")
            self.tags = {}

    def save(self):
        """Salva la tassonomia su disco in modo atomico."""
        try:
            self.taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.taxonomy_path.with_suffix(".tmp")
            data = {
                "version": self.version,
                "tags": self.tags
            }
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            import os
            if self.taxonomy_path.exists():
                bak_path = self.taxonomy_path.with_suffix(".bak")
                if bak_path.exists(): os.remove(bak_path)
                os.rename(self.taxonomy_path, bak_path)
            
            os.rename(temp_path, self.taxonomy_path)
            logger.info(f"[TagManager] Registro salvato: {len(self.tags)} tag.")
        except Exception as e:
            logger.error(f"[TagManager] Errore salvataggio tassonomia: {e}")

    def harvest_from_all_catalogs(self):
        """Scansiona tutti i cataloghi noti per popolare il registro iniziale."""
        found_tags: Set[str] = set()
        
        # 1. Cataloghi Globali in engine/data/
        data_dir = self.base_path / "engine" / "data"
        for p in data_dir.glob("global_*_catalog.json"):
            if "backup" in p.name.lower(): continue
            self._extract_from_json(p, found_tags)
            
        # 2. Catalogo Backgrounds
        bg_cat = self.base_path / "engine" / "assets" / "backgrounds" / "backgrounds_catalog.json"
        if bg_cat.exists():
            try:
                with open(bg_cat, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # La struttura dei background è dict-based: { "file.jpg": { "tags": [...] } }
                    for item in data.values():
                        if isinstance(item, dict):
                            for t in item.get("tags", []):
                                found_tags.add(t.strip().lower())
            except: pass

        # 3. Cataloghi dei Giochi
        games_dir = self.base_path / "games"
        if games_dir.exists():
            for g_dir in games_dir.iterdir():
                if g_dir.is_dir():
                    g_cat = g_dir / "objects_catalog.json"
                    self._extract_from_json(g_cat, found_tags)

        # Aggiorna il registro interno senza sovrascrivere le label esistenti
        count = 0
        for t_id in sorted(list(found_tags)):
            if t_id not in self.tags and t_id != "":
                # Crea una entry professionale con label IT capitalizzata
                self.tags[t_id] = {
                    "it": t_id.capitalize(),
                    "cat": "Generale"
                }
                count += 1
        
        if count > 0:
            logger.info(f"[TagManager] Harvesting completato: aggiunti {count} nuovi tag.")
            self.save()

    def _extract_from_json(self, path: Path, tag_set: Set[str]):
        if not path.exists(): return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                objs = data.get("objects", [])
                for obj in objs:
                    for t in obj.get("tags", []):
                        tag_set.add(t.strip().lower())
        except: pass

    def get_all_tag_ids(self) -> List[str]:
        return sorted(list(self.tags.keys()))

    def get_suggestions(self, query: str, limit: int = 20) -> List[str]:
        """Ritorna i tag che corrispondono alla query, ordinati per rilevanza."""
        query = query.lower().strip()
        if not query:
            return self.get_all_tag_ids()[:limit]
        
        matches = [t for t in self.tags.keys() if query in t]
        # Priorità a chi inizia con la query
        matches.sort(key=lambda x: (not x.startswith(query), x))
        return matches[:limit]

    def ensure_tag(self, tag_id: str) -> str:
        """Assicura che un tag esista nel registro, altrimenti lo crea (normalizzato)."""
        tag_id = tag_id.strip().lower().replace(" ", "_")
        if not tag_id: return ""
        if tag_id not in self.tags:
            self.tags[tag_id] = {
                "it": tag_id.replace("_", " ").capitalize(),
                "cat": "Generale"
            }
            self.save()
            logger.info(f"[TagManager] Nuovo tag creato e registrato: {tag_id}")
        return tag_id

    def get_label(self, tag_id: str, lang: str = "it") -> str:
        tag_data = self.tags.get(tag_id, {})
        return tag_data.get(lang, tag_id)
