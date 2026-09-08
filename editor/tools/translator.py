"""
editor/tools/translator.py

Machine translation for the translation editor.

The editor ships five languages and a project carries thousands of keys, so
the gap between "the strings exist in English" and "the game is playable in
German" is thousands of small edits. This fills the empty cells with a model
that runs locally: nothing is sent anywhere, and after the language packages
are downloaded once it works offline.

Two things are kept apart on purpose:

  * `TranslationService` decides *what* to translate - which cells are empty,
    which language to take the source from, how many there are - and is pure
    data, so it is testable without a model;
  * a backend does the translating. `ArgosBackend` is the real one; the tests
    use a stub. A backend that is not installed is not an error: the editor
    says how to install it and carries on.

Nothing is ever overwritten unless the caller asks for it: the default plan
only fills cells that are empty.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Protocol, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# How the service reports what it can do right now.
STATUS_NO_BACKEND = "no_backend"     # the package is not installed
STATUS_NO_MODEL = "no_model"         # installed, but the language pair is missing
STATUS_READY = "ready"

# A backend translates at most this many characters in one call: a UI string is
# short, and a runaway value is a sign of a corrupt entry rather than a caption.
MAX_TEXT_LEN = 2000

# Placeholders of a UI string: "{0}", "{name}", "{n:.1f}". A translation that
# loses one crashes str.format() at runtime, and a machine translator will
# happily reword them, so a result that does not carry the same set is refused.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*|\d+)[^{}]*\}")


def placeholders(text: str) -> Set[str]:
    """The placeholder names a string uses."""
    return set(_PLACEHOLDER_RE.findall(str(text or "")))


def keeps_placeholders(source: str, translated: str) -> bool:
    """True when the translation carries exactly the source placeholders."""
    return placeholders(source) == placeholders(translated)


@dataclass(frozen=True)
class TranslationJob:
    """One cell to fill: `key` in `target`, from `source_text` in `source`."""

    key: str
    source: str
    target: str
    source_text: str


class TranslationBackend(Protocol):
    """What the service needs from a translation engine."""

    name: str

    def is_installed(self) -> bool:
        """True when the package the backend needs is importable."""

    def installed_pairs(self) -> Set[Tuple[str, str]]:
        """Language pairs already downloaded, as (source, target)."""

    def download(self, source: str, target: str) -> bool:
        """Fetch the model for one pair. True when it is usable afterwards."""

    def translate(self, text: str, source: str, target: str) -> str:
        """Translate one string."""


class ArgosBackend:
    """Argos Translate: local models, offline once the packages are there.

    Everything is imported inside the methods: the editor must start, and the
    translation editor must open, on a machine where the package is absent.
    """

    name = "argostranslate"
    install_hint = "pip install argostranslate"

    def is_installed(self) -> bool:
        try:
            import argostranslate.translate  # noqa: F401
        except Exception:
            return False
        return True

    def installed_pairs(self) -> Set[Tuple[str, str]]:
        try:
            from argostranslate import package
            return {(p.from_code, p.to_code) for p in package.get_installed_packages()}
        except Exception as exc:
            logger.debug(f"[TRANSLATOR] pacchetti installati non leggibili: {exc}")
            return set()

    def download(self, source: str, target: str) -> bool:
        try:
            from argostranslate import package
            package.update_package_index()
            wanted = next(
                (p for p in package.get_available_packages()
                 if p.from_code == source and p.to_code == target), None)
            if wanted is None:
                logger.warning(
                    f"[TRANSLATOR] nessun modello disponibile per {source}->{target}")
                return False
            package.install_from_path(wanted.download())
            return (source, target) in self.installed_pairs()
        except Exception as exc:
            logger.error(f"[TRANSLATOR] download {source}->{target} fallito: {exc}")
            return False

    def translate(self, text: str, source: str, target: str) -> str:
        from argostranslate import translate as argos
        return argos.translate(text, source, target)


@dataclass
class TranslationService:
    """Decides what to translate, and runs it through a backend."""

    backend: TranslationBackend
    source_lang: str = "en"
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    # ── Stato ───────────────────────────────────────────────────────────────

    def status(self, targets: Sequence[str] = ()) -> str:
        """What the service can do for `targets` right now."""
        if not self.backend.is_installed():
            return STATUS_NO_BACKEND
        if targets and self.missing_pairs(targets):
            return STATUS_NO_MODEL
        return STATUS_READY

    def missing_pairs(self, targets: Sequence[str]) -> List[Tuple[str, str]]:
        """Pairs that still have to be downloaded for these targets."""
        if not self.backend.is_installed():
            return [(self.source_lang, t) for t in targets if t != self.source_lang]
        installed = self.backend.installed_pairs()
        return [(self.source_lang, t) for t in targets
                if t != self.source_lang and (self.source_lang, t) not in installed]

    # ── Cosa tradurre ───────────────────────────────────────────────────────

    def plan(self, keys: Iterable[str], targets: Sequence[str],
             value_of: Callable[[str, str], str],
             only_empty: bool = True) -> List[TranslationJob]:
        """The cells that would be filled, in the order they would be.

        `value_of(key, lang)` reads the current value. A key with no source
        text is skipped: there would be nothing to translate from.
        """
        jobs: List[TranslationJob] = []
        for key in keys:
            source_text = str(value_of(key, self.source_lang) or "").strip()
            if not source_text or len(source_text) > MAX_TEXT_LEN:
                continue
            for target in targets:
                if target == self.source_lang:
                    continue
                current = str(value_of(key, target) or "").strip()
                if only_empty and current:
                    continue
                jobs.append(TranslationJob(key, self.source_lang, target, source_text))
        return jobs

    # ── Esecuzione ──────────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Ask a running batch to stop at the next job."""
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def reset(self) -> None:
        self._cancel.clear()

    def run(self, jobs: Sequence[TranslationJob],
            on_done: Optional[Callable[[TranslationJob, str], None]] = None,
            on_error: Optional[Callable[[TranslationJob, Exception], None]] = None,
            ) -> int:
        """Translate every job. Returns how many produced a value.

        A job that fails is reported and skipped: one bad string must not lose
        the rest of a batch of a thousand.
        """
        done = 0
        for job in jobs:
            if self._cancel.is_set():
                break
            try:
                text = self.backend.translate(job.source_text, job.source, job.target)
            except Exception as exc:                       # noqa: BLE001
                logger.warning(f"[TRANSLATOR] {job.key} [{job.target}]: {exc}")
                if on_error:
                    on_error(job, exc)
                continue
            text = str(text or "").strip()
            if not text:
                continue
            if not keeps_placeholders(job.source_text, text):
                # "Found {n} objects" coming back without {n} would crash
                # str.format() the first time the game shows it.
                logger.warning(
                    f"[TRANSLATOR] {job.key} [{job.target}]: segnaposto persi")
                if on_error:
                    on_error(job, ValueError("placeholders lost"))
                continue
            done += 1
            if on_done:
                on_done(job, text)
        return done
