"""
editor/tools/translator_backends.py

The engines the translation editor can use, and finding the ones already here.

Three kinds, in the order the editor prefers them:

  * a **local service the machine already runs**. Ollama and LibreTranslate
    both answer on a known port, so the editor probes them and, if one is
    there, translation costs nothing to set up. This is why discovery exists:
    a lot of machines already have Ollama and nobody thinks to mention it.
  * **Argos Translate**, a pip package with downloadable language packages.
    Offline once installed, but it has to be installed.
  * nothing, which is a state the editor reports rather than a failure.

Every probe is bounded by `PROBE_TIMEOUT_S`: discovery runs while a dialog is
opening and must never be what makes it slow. Only the standard library is
used, so a machine that already runs a service needs no new dependency.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# A local service either answers immediately or is not there.
PROBE_TIMEOUT_S = 0.4
# Translating one string is a real request, so it gets a real timeout.
REQUEST_TIMEOUT_S = 60.0

OLLAMA_URL = "http://127.0.0.1:11434"
LIBRETRANSLATE_URL = "http://127.0.0.1:5000"

# Ollama models worth suggesting when the machine runs it but has nothing
# useful pulled. Small first: the editor should not propose a 40 GB download.
OLLAMA_SUGGESTED = ("gemma3:4b", "qwen2.5:7b", "llama3.1:8b")

LANGUAGE_NAMES = {
    "en": "English", "it": "Italian", "es": "Spanish",
    "fr": "French", "de": "German",
}


def _get_json(url: str, timeout: float) -> Optional[dict]:
    """GET a JSON document, or None when the host is not there."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        logger.debug(f"[TRANSLATOR] {url} non raggiungibile: {exc}")
        return None


def _post_json(url: str, payload: dict, timeout: float) -> Optional[dict]:
    """POST a JSON document and read the answer, or None on any failure."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        logger.warning(f"[TRANSLATOR] richiesta a {url} fallita: {exc}")
        return None


class OllamaBackend:
    """A local Ollama server. No install if the machine already runs one."""

    name = "ollama"
    kind = "service"
    install_hint = "https://ollama.com"

    def __init__(self, url: str = OLLAMA_URL, model: str = "") -> None:
        self.url = url.rstrip("/")
        self.model = model

    # ── Rilevamento ─────────────────────────────────────────────────────────

    def is_installed(self) -> bool:
        return self.models() != []

    def models(self) -> List[str]:
        """The models already pulled, newest API shape first."""
        data = _get_json(f"{self.url}/api/tags", PROBE_TIMEOUT_S)
        if not data:
            return []
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def suggested_models(self) -> List[str]:
        """What to offer pulling when nothing useful is there."""
        return list(OLLAMA_SUGGESTED)

    # ── Contratto backend ───────────────────────────────────────────────────

    def installed_pairs(self) -> Set[Tuple[str, str]]:
        """A language model handles any pair, so the model is what matters."""
        if not self.model:
            return set()
        codes = list(LANGUAGE_NAMES)
        return {(a, b) for a in codes for b in codes if a != b}

    def download(self, source: str, target: str) -> bool:
        """Pull the chosen model. The pair itself needs no download."""
        if not self.model:
            return False
        answer = _post_json(f"{self.url}/api/pull",
                            {"name": self.model, "stream": False},
                            timeout=None)
        return answer is not None and self.model in self.models()

    def translate(self, text: str, source: str, target: str) -> str:
        if not self.model:
            raise RuntimeError("no Ollama model selected")
        answer = _post_json(f"{self.url}/api/generate", {
            "model": self.model,
            "prompt": _translation_prompt(text, source, target),
            "stream": False,
            "options": {"temperature": 0},
        }, REQUEST_TIMEOUT_S)
        if not answer:
            raise RuntimeError("Ollama did not answer")
        return _clean_model_output(answer.get("response", ""))


class LibreTranslateBackend:
    """A local LibreTranslate server: a translation API, not a chat model."""

    name = "libretranslate"
    kind = "service"
    install_hint = "https://libretranslate.com"

    def __init__(self, url: str = LIBRETRANSLATE_URL) -> None:
        self.url = url.rstrip("/")
        self._languages: Optional[Set[str]] = None

    def is_installed(self) -> bool:
        return bool(self.languages())

    def languages(self) -> Set[str]:
        if self._languages is None:
            data = _get_json(f"{self.url}/languages", PROBE_TIMEOUT_S)
            self._languages = {entry.get("code", "") for entry in (data or [])
                               if isinstance(entry, dict)} - {""}
        return self._languages

    def installed_pairs(self) -> Set[Tuple[str, str]]:
        codes = self.languages()
        return {(a, b) for a in codes for b in codes if a != b}

    def download(self, source: str, target: str) -> bool:
        """The server owns its models: there is nothing for the editor to do."""
        return (source, target) in self.installed_pairs()

    def translate(self, text: str, source: str, target: str) -> str:
        answer = _post_json(f"{self.url}/translate", {
            "q": text, "source": source, "target": target, "format": "text",
        }, REQUEST_TIMEOUT_S)
        if not answer:
            raise RuntimeError("LibreTranslate did not answer")
        return str(answer.get("translatedText", ""))


def _translation_prompt(text: str, source: str, target: str) -> str:
    """The instruction a chat model gets. Deliberately narrow.

    A UI string carries placeholders like {n} and {name}: a model that rewrites
    them breaks str.format at runtime, so it is told not to, and the service
    refuses the answer anyway if they changed.
    """
    return (
        f"Translate the following user interface string from "
        f"{LANGUAGE_NAMES.get(source, source)} to "
        f"{LANGUAGE_NAMES.get(target, target)}.\n"
        "Keep every placeholder in braces exactly as it is, for example {0} "
        "or {name}.\n"
        "Answer with the translation only: no quotes, no explanation, no "
        "leading or trailing text.\n\n"
        f"{text}"
    )


def _clean_model_output(text: str) -> str:
    """Strip what a chat model tends to add around the answer."""
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned.strip("`")
        cleaned = cleaned.strip()
        if "\n" in cleaned and cleaned.split("\n", 1)[0].isalpha():
            cleaned = cleaned.split("\n", 1)[1].strip()
    for opening, closing in (('"', '"'), ("'", "'"), ("“", "”"),
                            ("«", "»")):
        if (len(cleaned) > 1 and cleaned.startswith(opening)
                and cleaned.endswith(closing)):
            cleaned = cleaned[1:-1].strip()
    return cleaned


@dataclass
class BackendOption:
    """One engine the user can pick, and what it would take to use it."""

    backend: object
    label: str
    detail: str
    ready: bool
    models: List[str] = field(default_factory=list)


def discover_backends(probe: Optional[Callable[[], Sequence]] = None) -> List[BackendOption]:
    """Every engine the editor could use here, best first.

    A local service already running wins: it needs no install and no download.
    `probe` exists for the tests, which must not depend on what happens to be
    listening on this machine.
    """
    if probe is not None:
        return list(probe())

    options: List[BackendOption] = []

    ollama = OllamaBackend()
    models = ollama.models()
    if models:
        ollama.model = _best_ollama_model(models)
        options.append(BackendOption(
            ollama, "Ollama", f"{len(models)} models available", True, models))

    libre = LibreTranslateBackend()
    if libre.is_installed():
        options.append(BackendOption(
            libre, "LibreTranslate",
            f"{len(libre.languages())} languages", True))

    from editor.tools.translator import ArgosBackend
    argos = ArgosBackend()
    installed = argos.is_installed()
    options.append(BackendOption(
        argos, "Argos Translate",
        "offline models" if installed else ArgosBackend.install_hint,
        installed))
    return options


def _best_ollama_model(models: Sequence[str]) -> str:
    """Pick a sensible default: a suggested one if pulled, else the first."""
    for wanted in OLLAMA_SUGGESTED:
        for model in models:
            if model.split(":")[0] == wanted.split(":")[0]:
                return model
    return models[0] if models else ""
