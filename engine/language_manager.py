"""
engine/language_manager.py

Sistema multilingua. Risolve chiavi di testo nella lingua corrente.

- Le chiavi del motore (btn_play, hud_found, …) risiedono in engine/assets/strings/
- Le chiavi del gioco (game_title, obj_chiave, …) in games/<id>/strings/
- Cambio lingua in tempo reale senza ricaricare la scena
- Fallback automatico a lingua di default se la chiave manca
- Chiave non trovata da nessuna parte → restituisce la chiave stessa (visibile, non crashante)
"""

import json
import os
from engine.utils import get_resource_path, get_logger

log = get_logger(__name__)

# Lingue ufficialmente supportate dal motore. Se non vengono trovati file di
# stringhe (es. boot anomalo) la audit_completeness usa questa lista come
# fallback per dire almeno "queste 5 sono attese".
SUPPORTED_LANGS_DEFAULT: tuple[str, ...] = ("en", "it", "fr", "es", "de")

# Lingua di default del motore e dell'editor: usata quando nessuna preferenza
# e' salvata o quando quella salvata non e' piu' supportata.
DEFAULT_LANG: str = "en"

# Lingua di fallback UNICA e non negoziabile: qualsiasi chiave mancante nella
# lingua corrente viene risolta in inglese prima di degradare alla chiave grezza.
FALLBACK_LANG: str = "en"


# ---------------------------------------------------------------------------
# Accesso globale (per widget/modali senza riferimento all'editor o al gioco)
# ---------------------------------------------------------------------------

_ACTIVE: "LanguageManager | None" = None


def set_active_manager(manager: "LanguageManager | None") -> None:
    """Registra il LanguageManager corrente come sorgente globale per tr()."""
    global _ACTIVE
    _ACTIVE = manager


def get_active_manager() -> "LanguageManager | None":
    return _ACTIVE


def tr(key: str, default: str | None = None) -> str:
    """
    Traduce una chiave usando il LanguageManager attivo.

    Pensata per componenti standalone (modali, widget) che non hanno un
    riferimento all'editor o al gioco. Senza manager attivo restituisce il
    default (inglese) o la chiave stessa.
    """
    if _ACTIVE is not None:
        return _ACTIVE.get(key, default)
    return default if default is not None else key


class LanguageManager:
    def __init__(self) -> None:
        self._engine_strings: dict[str, str] = {}   # testi del motore
        self._game_strings: dict[str, str] = {}      # testi del gioco corrente
        self._fallback_strings: dict[str, str] = {}  # lingua di fallback

        self._current_lang: str = DEFAULT_LANG
        self._fallback_lang: str = FALLBACK_LANG
        self._game_id: str = ""
        self._available_langs: list[str] = []
        self._extra_sources: set[str] = set() # Directory aggiuntive da scansionare

        # Registry chiavi mancanti: emette warning solo alla prima occorrenza
        self._missing_keys: set[str] = set()

    # ------------------------------------------------------------------
    # Inizializzazione
    # ------------------------------------------------------------------

    def load_for_game(self, game_id: str, language: str,
                      fallback: str = FALLBACK_LANG) -> None:
        """
        Carica tutte le stringhe per il gioco e la lingua specificati.

        Il fallback e' sempre FALLBACK_LANG ("en"): il parametro resta per
        retro-compatibilita' della firma, ma un valore diverso viene ignorato
        (con warning) perche' l'inglese e' l'unica lingua garantita completa.
        """
        if fallback != FALLBACK_LANG:
            log.warning(
                "[i18n] Fallback '%s' ignorato: la lingua di fallback e' sempre '%s'",
                fallback, FALLBACK_LANG,
            )
            fallback = FALLBACK_LANG
        if not language:
            language = DEFAULT_LANG
        self._game_id = game_id
        self._fallback_lang = fallback
        self._detect_available_langs(game_id)
        self._load_engine_strings(language)
        self._load_game_strings(game_id, language)
        # Carica fallback solo se diverso dalla lingua corrente
        if language != fallback:
            self._load_fallback_strings(game_id, fallback)
        else:
            self._fallback_strings = {}
        self._current_lang = language
        # Reset registry chiavi mancanti ad ogni cambio lingua
        self._missing_keys.clear()
        
        # Log di riepilogo caricamento
        log.info(
            "Lingua caricata: %s (Fallback: %s). [Engine: %d, Gioco: %d]", 
            language, fallback, len(self._engine_strings), len(self._game_strings)
        )

    def change_language(self, language: str) -> None:
        """Cambia lingua in tempo reale. Tutti i testi si aggiornano al prossimo frame."""
        if language not in self._available_langs:
            log.warning("Lingua '%s' non disponibile. Disponibili: %s", 
                        language, self._available_langs)
            return
        self.load_for_game(self._game_id, language, self._fallback_lang)

    def add_extra_source(self, directory_path: str) -> None:
        """Aggiunge una directory di stringhe extra (es. minigioco) e ricarica i pool."""
        if not directory_path or not os.path.isdir(directory_path):
            log.debug("Directory stringhe extra non valida: %s", directory_path)
            return
        
        path = os.path.abspath(directory_path)
        if path not in self._extra_sources:
            log.info("[i18n] Aggiunta sorgente extra: %s", path)
            self._extra_sources.add(path)
            # Ricarichiamo le stringhe correnti per includere quelle nuove
            self.load_for_game(self._game_id, self._current_lang, self._fallback_lang)

    def remove_extra_source(self, directory_path: str) -> None:
        """Rimuove una sorgente extra e ricarica i pool."""
        path = os.path.abspath(directory_path)
        if path in self._extra_sources:
            log.info("[i18n] Rimozione sorgente extra: %s", path)
            self._extra_sources.remove(path)
            self.load_for_game(self._game_id, self._current_lang, self._fallback_lang)

    def merge_strings(self, additional_strings: dict[str, str]) -> None:
        """Fonde un dizionario di stringhe addizionali (es. da un minigioco) nel pool corrente."""
        if not additional_strings: return
        self._game_strings.update(additional_strings)
        log.debug("Fusi %d nuovi testi nel LanguageManager", len(additional_strings))

    # ------------------------------------------------------------------
    # Risoluzione chiavi
    # ------------------------------------------------------------------

    def get(self, key: str, default: str = None) -> str:
        """
        Risolve una chiave di testo nella lingua corrente.
        Ordine di ricerca: game_strings -> engine_strings -> fallback -> default -> chiave grezza
        Il warning per chiave mancante viene emesso una sola volta per sessione/lingua.
        """
        # 1. Ricerca nel pool del gioco o del motore
        # 1. Ricerca nel pool del gioco (se presente e non vuota)
        if key in self._game_strings:
            val = self._game_strings[key]
            if val and val.strip():
                # --- FIX ANTI-INQUINAMENTO EDITOR ---
                # Se siamo in una lingua non-inglese e il gioco ci dà un placeholder 
                # (es. "Abyssal Crystal"), controlliamo se l'engine ha una traduzione vera.
                if self._current_lang != "en" and key.startswith("obj_"):
                    placeholder = key.replace("obj_", "").replace("_", " ").title()
                    if val == placeholder:
                         if key in self._engine_strings and self._engine_strings[key]:
                             # Trovata traduzione reale nell'engine (es: Cristallo Abissale)
                             return self._engine_strings[key]
                return val
            # else: skip silent
            
        # 2. Ricerca nel pool dell'engine (default)
        if key in self._engine_strings:
            val = self._engine_strings[key]
            if val and val.strip():
                return val
            # else: skip silent
            
        # 2. Esclusione nomi propri o chiavi invalide
        if not key:
            return default if default is not None else ""
            
        # 3. Fallback a inglese (segnala la mancanza della traduzione specifica)
        # Il fallback ha la precedenza sul return della chiave grezza perché
        # vogliamo vedere "Apple" invece di "obj_apple" se l'inglese è disponibile.
        if self._current_lang != self._fallback_lang and key in self._fallback_strings:
            if key not in self._missing_keys:
                self._missing_keys.add(key)
                log.warning(
                    "[i18n] Fallback EN: '%s' non tradotta in '%s'",
                    key, self._current_lang
                )
            return self._fallback_strings[key]

        # 4. Standard: nomi che iniziano con Maiuscola o contengono '_name' alla fine.
        # Spostato dopo il fallback per permettere traduzioni inglesi se mancano quelle locali.
        if key.endswith("_name") or key[0].isupper():
            return default if default is not None else key

        # 5. Fallback finale per oggetti: genera nome leggibile dall'id
        if key.startswith("obj_"):
            formatted = key.replace("obj_", "").replace("_", " ").title()
            if key not in self._missing_keys:
                self._missing_keys.add(key)
                log.debug("[i18n] Fallback generato per oggetto: '%s' -> '%s'", key, formatted)
            return formatted

        # 6. Chiave totalmente mancante dappertutto (Warning solo per chiavi non-oggetto)
        if key not in self._missing_keys:
            self._missing_keys.add(key)
            log.warning(
                "[i18n] Chiave mancante: '%s' (lang='%s', game='%s')",
                key, self._current_lang, self._game_id or "engine"
            )
        return default if default is not None else key

    def __call__(self, key: str, default: str = None) -> str:
        """Alias comodo: lang('btn_play') invece di lang.get('btn_play')."""
        return self.get(key, default)

    # ------------------------------------------------------------------
    # Audit chiavi mancanti
    # ------------------------------------------------------------------

    @property
    def missing_keys(self) -> set[str]:
        """Restituisce il set di chiavi non trovate nella sessione corrente."""
        return frozenset(self._missing_keys)

    def report_missing_keys(self) -> None:
        """Emette un riepilogo completo di tutte le chiavi mancanti (uso da debug/editor)."""
        if not self._missing_keys:
            log.info("[i18n] Nessuna chiave mancante. Localizzazione completa.")
            return
        log.warning(
            "[i18n] RIEPILOGO chiavi mancanti per lang='%s' game='%s' (%d totali):\n  %s",
            self._current_lang,
            self._game_id or "engine",
            len(self._missing_keys),
            "\n  ".join(sorted(self._missing_keys))
        )

    # ------------------------------------------------------------------
    # Audit completezza tra lingue (eseguito al boot del gioco)
    # ------------------------------------------------------------------

    def audit_completeness(self, game_id: str | None = None,
                           *, log_warnings: bool = True) -> dict[str, dict]:
        """
        Confronta TUTTE le chiavi disponibili nelle 5 lingue (engine + gioco)
        e segnala chi è disallineato.

        Per ogni lingua produce:
          {
            "lang": "fr",
            "missing_keys": [...],   # chiavi presenti in altre lingue ma non qui
            "empty_keys": [...],     # chiavi presenti ma con valore vuoto
            "extra_keys": [...],     # chiavi qui ma non altrove (di solito 0)
            "total": int,
          }

        Returns dict {lang: stats}. Logga warning se `log_warnings=True`.
        Chiamabile al boot del gioco PRIMA di entrare nella scena, così
        eventuali traduzioni mancanti vengono diagnosticate subito.
        """
        gid = game_id or self._game_id
        langs = list(self._available_langs) or list(SUPPORTED_LANGS_DEFAULT)

        # Raccogli tutte le chiavi per lingua (engine + gioco), tutte da disco
        per_lang_keys: dict[str, dict[str, str]] = {}
        for lang in langs:
            data: dict[str, str] = {}
            # Engine strings
            eng_p = get_resource_path("engine", "assets", "strings", f"{lang}.json")
            data.update(self._read_json(str(eng_p)))
            # Game strings
            if gid and gid != "engine":
                game_p = get_resource_path("games", gid, "strings", f"{lang}.json")
                data.update(self._read_json(str(game_p)))
            per_lang_keys[lang] = data

        all_keys: set[str] = set()
        for d in per_lang_keys.values():
            all_keys.update(d.keys())

        report: dict[str, dict] = {}
        for lang, d in per_lang_keys.items():
            present = set(d.keys())
            missing = sorted(all_keys - present)
            empty = sorted(k for k in present if not (d.get(k) or "").strip())
            extra = sorted(present - all_keys)  # quasi sempre vuoto
            report[lang] = {
                "lang": lang,
                "missing_keys": missing,
                "empty_keys": empty,
                "extra_keys": extra,
                "total": len(present),
            }

        if log_warnings:
            total_keys_union = len(all_keys)
            log.info(
                "[i18n] Audit completezza (game='%s', %d lingue, %d chiavi union):",
                gid or "engine", len(langs), total_keys_union,
            )
            for lang, st in report.items():
                missing_n = len(st["missing_keys"])
                empty_n = len(st["empty_keys"])
                pct = (1 - missing_n / max(total_keys_union, 1)) * 100
                if missing_n or empty_n:
                    log.warning(
                        "[i18n]   %s: %d/%d chiavi (%.1f%%)  missing=%d  empty=%d",
                        lang, st["total"], total_keys_union, pct, missing_n, empty_n,
                    )
                else:
                    log.info("[i18n]   %s: completa (%d chiavi)", lang, st["total"])

        return report

    @property
    def current_language(self) -> str:
        return self._current_lang

    @property
    def available_languages(self) -> list[str]:
        return list(self._available_langs)

    def _detect_available_langs(self, game_id: str) -> None:
        """Rileva le lingue disponibili controllando sia l'engine che il gioco specificato."""
        # Usiamo un set locale per evitare problemi di mutazione durante il loop
        langs_found = set()
        
        # 1. Engine
        engine_dir = get_resource_path("engine", "assets", "strings")
        if os.path.exists(engine_dir):
            langs_found.update({os.path.splitext(f)[0] for f in os.listdir(engine_dir) if f.endswith(".json")})

        # 2. Gioco
        if game_id and game_id != "engine":
            strings_dir = get_resource_path("games", game_id, "strings")
            if os.path.isdir(strings_dir):
                langs_found.update({os.path.splitext(f)[0] for f in os.listdir(strings_dir) if f.endswith(".json")})
        
        # 3. Sorgenti extra (es. minigiochi)
        for source in self._extra_sources:
            if os.path.isdir(source):
                langs_found.update({os.path.splitext(f)[0] for f in os.listdir(source) if f.endswith(".json")})

        # Salviamo come lista ordinata
        self._available_langs = sorted(list(langs_found))
        
        if not self._available_langs:
            self._available_langs = [DEFAULT_LANG, "it"]
            
        log.debug("Lingue disponibili rilevate: %s (game_id: %s)", self._available_langs, game_id)

    # ------------------------------------------------------------------
    # Caricamento file
    # ------------------------------------------------------------------

    def _load_engine_strings(self, lang: str) -> None:
        """Carica il pool di stringhe del motore (globali)."""
        path = get_resource_path("engine", "assets", "strings", f"{lang}.json")
        self._engine_strings = self._read_json(str(path))
        log.info("[i18n] Engine strings caricate da: %s (Chiavi: %d)", path, len(self._engine_strings))
        log.debug("Engine strings caricate da %s: %d chiavi trovate", path, len(self._engine_strings))

    def _load_game_strings(self, game_id: str, lang: str) -> None:
        """Carica il pool di stringhe specifico del gioco."""
        if not game_id or game_id == "engine": 
            self._game_strings = {}
            return
            
        path = get_resource_path("games", game_id, "strings", f"{lang}.json")
        self._game_strings = self._read_json(str(path))
        log.info("[i18n] Game strings caricate da: %s (Chiavi: %d)", path, len(self._game_strings))
        
        # Merge da sorgenti extra (es. minigiochi attivi)
        for source in self._extra_sources:
            extra_path = os.path.join(source, f"{lang}.json")
            if os.path.exists(extra_path):
                self._game_strings.update(self._read_json(extra_path))

    def _load_fallback_strings(self, game_id: str, lang: str) -> None:
        engine_path = get_resource_path("engine", "assets", "strings", f"{lang}.json")
        merged = self._read_json(engine_path)

        if game_id and game_id != "engine":
            game_path = get_resource_path("games", game_id, "strings", f"{lang}.json")
            merged.update(self._read_json(game_path))
            
        # Merge da sorgenti extra per il fallback
        for source in self._extra_sources:
            extra_path = os.path.join(source, f"{lang}.json")
            if os.path.exists(extra_path):
                merged.update(self._read_json(extra_path))

        self._fallback_strings = merged

    @staticmethod
    def _read_json(path: str) -> dict[str, str]:
        if not os.path.exists(path):
            log.debug("File stringhe non trovato: %s", path)
            return {}
        # Usiamo utf-8-sig per gestire automaticamente il BOM (Byte Order Mark) 
        # che alcuni editor Windows aggiungono silenziosamente.
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            log.error("Errore parsing JSON in '%s': %s", path, exc)
            return {}
        except Exception as e:
            log.error("Errore imprevisto durante la lettura di '%s': %s", path, e)
            return {}
