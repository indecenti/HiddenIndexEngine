"""
tests/test_editor_translator.py

Machine translation for the translation editor.

The service decides *what* to translate and a backend does the translating,
which is what makes this testable without a model: the tests here drive a stub
backend. What matters is that it never destroys work - nothing is overwritten
unless asked, a key with no source text is skipped, one bad string does not
lose the rest of a batch of a thousand - and that a missing package is a state
the editor reports, not a crash.
"""

from __future__ import annotations

import pytest

from editor.tools.translator import (
    MAX_TEXT_LEN, STATUS_NO_BACKEND, STATUS_NO_MODEL, STATUS_READY,
    ArgosBackend, TranslationJob, TranslationService,
)


class StubBackend:
    """A backend that upper-cases and records what it was asked."""

    name = "stub"

    def __init__(self, installed=True, pairs=(("en", "it"), ("en", "de")),
                 fail_on=()):
        self.installed = installed
        self.pairs = set(pairs)
        self.fail_on = set(fail_on)
        self.calls: list = []
        self.downloaded: list = []

    def is_installed(self):
        return self.installed

    def installed_pairs(self):
        return set(self.pairs)

    def download(self, source, target):
        self.downloaded.append((source, target))
        self.pairs.add((source, target))
        return True

    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if text in self.fail_on:
            raise RuntimeError("backend blew up")
        return f"{text.upper()}-{target}"


def _service(**kw):
    return TranslationService(backend=StubBackend(**kw))


def _values(data):
    return lambda key, lang: data.get(lang, {}).get(key, "")


DATA = {
    "en": {"a": "Alpha", "b": "Beta", "c": "", "d": "Delta"},
    "it": {"a": "Alfa", "b": "", "c": "", "d": ""},
    "de": {"a": "", "b": "", "c": "", "d": ""},
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. STATO
# ─────────────────────────────────────────────────────────────────────────────

def test_a_missing_package_is_a_state_not_a_crash():
    service = _service(installed=False)
    assert service.status(["it"]) == STATUS_NO_BACKEND


def test_a_missing_model_is_reported_separately():
    service = _service(pairs=(("en", "it"),))
    assert service.status(["it"]) == STATUS_READY
    assert service.status(["it", "de"]) == STATUS_NO_MODEL


def test_ready_when_every_pair_is_there():
    assert _service().status(["it", "de"]) == STATUS_READY


def test_the_source_language_needs_no_model():
    assert _service(pairs=()).status(["en"]) == STATUS_READY


def test_missing_pairs_lists_what_to_download():
    service = _service(pairs=(("en", "it"),))
    assert service.missing_pairs(["it", "de", "fr"]) == [("en", "de"), ("en", "fr")]


def test_without_the_package_everything_is_missing():
    service = _service(installed=False)
    assert service.missing_pairs(["it", "de"]) == [("en", "it"), ("en", "de")]


# ─────────────────────────────────────────────────────────────────────────────
# 2. IL PIANO NON DISTRUGGE NIENTE
# ─────────────────────────────────────────────────────────────────────────────

def test_the_plan_fills_only_the_empty_cells():
    jobs = _service().plan(["a", "b"], ["it", "de"], _values(DATA))
    assert [(j.key, j.target) for j in jobs] == [("a", "de"), ("b", "it"), ("b", "de")]


def test_the_plan_can_be_asked_to_overwrite():
    jobs = _service().plan(["a"], ["it"], _values(DATA), only_empty=False)
    assert [(j.key, j.target) for j in jobs] == [("a", "it")]


def test_a_key_with_no_source_text_is_skipped():
    """There would be nothing to translate from."""
    jobs = _service().plan(["c"], ["it", "de"], _values(DATA))
    assert jobs == []


def test_the_source_language_is_never_a_target():
    jobs = _service().plan(["a"], ["en", "it", "de"], _values(DATA))
    assert all(job.target != "en" for job in jobs)


def test_a_runaway_value_is_skipped():
    data = {"en": {"x": "y" * (MAX_TEXT_LEN + 1)}, "it": {"x": ""}}
    assert _service().plan(["x"], ["it"], _values(data)) == []


def test_the_plan_carries_the_source_text():
    job = _service().plan(["a"], ["de"], _values(DATA))[0]
    assert job.source_text == "Alpha" and job.source == "en"


def test_the_plan_of_a_finished_project_is_empty():
    data = {lang: {"a": "x"} for lang in ("en", "it", "de")}
    assert _service().plan(["a"], ["it", "de"], _values(data)) == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. ESECUZIONE
# ─────────────────────────────────────────────────────────────────────────────

def test_running_a_plan_produces_a_value_per_job():
    service = _service()
    jobs = service.plan(["a", "b"], ["it", "de"], _values(DATA))
    got = {}
    assert service.run(jobs, on_done=lambda j, t: got.__setitem__((j.key, j.target), t)) == 3
    assert got[("a", "de")] == "ALPHA-de"


def test_one_bad_string_does_not_lose_the_batch():
    service = TranslationService(backend=StubBackend(fail_on=("Beta",)))
    jobs = service.plan(["a", "b", "d"], ["de"], _values(DATA))
    errors = []
    done = service.run(jobs, on_error=lambda j, e: errors.append(j.key))
    assert done == 2 and errors == ["b"]


def test_an_empty_translation_is_not_written():
    class Blank(StubBackend):
        def translate(self, text, source, target):
            return "   "

    service = TranslationService(backend=Blank())
    jobs = service.plan(["a"], ["de"], _values(DATA))
    written = []
    assert service.run(jobs, on_done=lambda j, t: written.append(t)) == 0
    assert written == []


def test_cancelling_stops_at_the_next_job():
    service = _service()
    jobs = service.plan(["a", "b", "d"], ["it", "de"], _values(DATA))
    seen = []

    def record(job, text):
        seen.append(job.key)
        service.cancel()

    service.run(jobs, on_done=record)
    assert len(seen) == 1, "the batch stops after the job that cancelled it"


def test_a_cancelled_service_can_be_reused():
    service = _service()
    service.cancel()
    assert service.cancelled() is True
    service.reset()
    assert service.cancelled() is False
    jobs = service.plan(["a"], ["de"], _values(DATA))
    assert service.run(jobs) == 1


def test_running_an_empty_plan_is_harmless():
    assert _service().run([]) == 0


def test_the_backend_is_called_with_the_pair_of_the_job():
    service = _service()
    backend = service.backend
    service.run([TranslationJob("k", "en", "de", "Hello")])
    assert backend.calls == [("Hello", "en", "de")]


# ─────────────────────────────────────────────────────────────────────────────
# 4. IL BACKEND REALE E' OPZIONALE
# ─────────────────────────────────────────────────────────────────────────────

def test_the_real_backend_reports_absence_without_raising():
    """The editor must open on a machine that has never seen argostranslate."""
    backend = ArgosBackend()
    assert backend.is_installed() in (True, False)
    if not backend.is_installed():
        assert backend.installed_pairs() == set()


def test_the_real_backend_says_how_to_install_itself():
    assert "argostranslate" in ArgosBackend.install_hint


@pytest.mark.parametrize("targets", ([], ["it"], ["it", "de", "fr", "es"]))
def test_status_never_raises_whatever_the_targets(targets):
    assert TranslationService(backend=ArgosBackend()).status(targets) in (
        STATUS_NO_BACKEND, STATUS_NO_MODEL, STATUS_READY)


# ─────────────────────────────────────────────────────────────────────────────
# 5. I SEGNAPOSTO SOPRAVVIVONO
# ─────────────────────────────────────────────────────────────────────────────

from editor.tools.translator import keeps_placeholders, placeholders  # noqa: E402


def test_placeholders_are_found_by_name_and_by_index():
    assert placeholders("Found {n} of {0} in {name}") == {"n", "0", "name"}


def test_a_string_without_placeholders_has_none():
    assert placeholders("Hello") == set()
    assert placeholders(None) == set()


def test_a_format_spec_does_not_change_the_name():
    assert placeholders("{n:.1f}%") == {"n"}


def test_a_translation_that_keeps_them_is_accepted():
    assert keeps_placeholders("Found {n}", "Trovati {n}") is True


def test_a_translation_that_loses_one_is_refused():
    assert keeps_placeholders("Found {n}", "Trovati") is False


def test_a_translation_that_invents_one_is_refused():
    assert keeps_placeholders("Found", "Trovati {n}") is False


def test_a_translation_that_renames_one_is_refused():
    """{n} becoming {numero} crashes str.format just as surely."""
    assert keeps_placeholders("Found {n}", "Trovati {numero}") is False


def test_the_service_drops_a_result_that_lost_a_placeholder():
    class Mangler(StubBackend):
        def translate(self, text, source, target):
            return "Tradotto senza segnaposto"

    service = TranslationService(backend=Mangler())
    data = {"en": {"k": "Found {n} objects"}, "it": {"k": ""}}
    jobs = service.plan(["k"], ["it"], _values(data))
    errors = []
    assert service.run(jobs, on_error=lambda j, e: errors.append(str(e))) == 0
    assert errors and "placeholder" in errors[0]


def test_the_service_accepts_a_result_that_kept_them():
    class Faithful(StubBackend):
        def translate(self, text, source, target):
            return "Trovati {n} oggetti"

    service = TranslationService(backend=Faithful())
    data = {"en": {"k": "Found {n} objects"}, "it": {"k": ""}}
    written = []
    assert service.run(service.plan(["k"], ["it"], _values(data)),
                       on_done=lambda j, t: written.append(t)) == 1
    assert written == ["Trovati {n} oggetti"]
