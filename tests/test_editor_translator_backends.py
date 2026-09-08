"""
tests/test_editor_translator_backends.py

The engines the translation editor can use, and finding the ones already here.

A lot of machines already run Ollama and nobody thinks to mention it, so the
editor probes for it: if it answers, translation costs nothing to set up. The
probing must never be what makes a dialog slow, and a machine with nothing
listening must get an ordinary "not available", not an exception.

Nothing here touches the network: every test drives the HTTP helpers through a
fake, which is also the only way these can run on a build machine.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from editor.tools import translator_backends as tb
from editor.tools.translator_backends import (
    BackendOption, LibreTranslateBackend, OllamaBackend, PROBE_TIMEOUT_S,
    _best_ollama_model, _clean_model_output, _translation_prompt,
    discover_backends,
)


@pytest.fixture
def http(monkeypatch):
    """Replace the two HTTP helpers and record what they were asked."""

    class Fake:
        def __init__(self):
            self.gets: list = []
            self.posts: list = []
            self.get_answers: dict = {}
            self.post_answers: dict = {}

        def get(self, url, timeout):
            self.gets.append((url, timeout))
            return self.get_answers.get(url)

        def post(self, url, payload, timeout):
            self.posts.append((url, payload, timeout))
            return self.post_answers.get(url)

    fake = Fake()
    monkeypatch.setattr(tb, "_get_json", fake.get)
    monkeypatch.setattr(tb, "_post_json", fake.post)
    return fake


# ─────────────────────────────────────────────────────────────────────────────
# 1. OLLAMA
# ─────────────────────────────────────────────────────────────────────────────

def test_a_machine_without_ollama_reports_it_calmly(http):
    assert OllamaBackend().models() == []
    assert OllamaBackend().is_installed() is False


def test_ollama_lists_the_models_it_has(http):
    http.get_answers[f"{tb.OLLAMA_URL}/api/tags"] = {
        "models": [{"name": "gemma3:4b"}, {"name": "llama3.1:8b"}]}
    assert OllamaBackend().models() == ["gemma3:4b", "llama3.1:8b"]


def test_ollama_is_probed_with_a_short_timeout(http):
    """Discovery runs while a dialog opens: it must not be what makes it slow."""
    OllamaBackend().models()
    assert http.gets and http.gets[0][1] == PROBE_TIMEOUT_S


def test_ollama_without_a_model_offers_no_pair(http):
    assert OllamaBackend().installed_pairs() == set()


def test_ollama_with_a_model_handles_every_pair(http):
    pairs = OllamaBackend(model="gemma3:4b").installed_pairs()
    assert ("en", "de") in pairs and ("de", "en") in pairs
    assert all(a != b for a, b in pairs)


def test_ollama_translates_through_generate(http):
    http.post_answers[f"{tb.OLLAMA_URL}/api/generate"] = {"response": "  Hallo  "}
    assert OllamaBackend(model="m").translate("Hello", "en", "de") == "Hallo"
    url, payload, _ = http.posts[0]
    assert payload["model"] == "m" and payload["stream"] is False
    assert payload["options"]["temperature"] == 0


def test_ollama_without_a_model_refuses_to_translate(http):
    with pytest.raises(RuntimeError):
        OllamaBackend().translate("Hello", "en", "de")


def test_ollama_that_does_not_answer_raises(http):
    with pytest.raises(RuntimeError):
        OllamaBackend(model="m").translate("Hello", "en", "de")


def test_the_prompt_tells_the_model_to_keep_the_placeholders():
    prompt = _translation_prompt("Found {n} objects", "en", "de")
    assert "{0}" in prompt and "{name}" in prompt
    assert "German" in prompt and "English" in prompt
    assert prompt.endswith("Found {n} objects")


# ─────────────────────────────────────────────────────────────────────────────
# 2. RIPULITURA DELL'OUTPUT DI UN MODELLO DI CHAT
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,clean", [
    ("Hallo", "Hallo"),
    ("  Hallo  ", "Hallo"),
    ('"Hallo"', "Hallo"),
    ("'Hallo'", "Hallo"),
    ("“Hallo”", "Hallo"),
    ("```\nHallo\n```", "Hallo"),
    ("", ""),
])
def test_a_chat_model_answer_is_stripped_of_its_decoration(raw, clean):
    assert _clean_model_output(raw) == clean


def test_a_quote_inside_the_text_is_left_alone():
    assert _clean_model_output('Er sagte "hallo" laut') == 'Er sagte "hallo" laut'


# ─────────────────────────────────────────────────────────────────────────────
# 3. LIBRETRANSLATE
# ─────────────────────────────────────────────────────────────────────────────

def test_a_machine_without_libretranslate_reports_it_calmly(http):
    assert LibreTranslateBackend().is_installed() is False


def test_libretranslate_reads_the_languages_it_serves(http):
    http.get_answers[f"{tb.LIBRETRANSLATE_URL}/languages"] = [
        {"code": "en"}, {"code": "it"}]
    backend = LibreTranslateBackend()
    assert backend.languages() == {"en", "it"}
    assert ("en", "it") in backend.installed_pairs()


def test_libretranslate_asks_only_once(http):
    http.get_answers[f"{tb.LIBRETRANSLATE_URL}/languages"] = [{"code": "en"}]
    backend = LibreTranslateBackend()
    backend.languages()
    backend.languages()
    assert len(http.gets) == 1, "the language list is cached"


def test_libretranslate_translates(http):
    http.get_answers[f"{tb.LIBRETRANSLATE_URL}/languages"] = [
        {"code": "en"}, {"code": "de"}]
    http.post_answers[f"{tb.LIBRETRANSLATE_URL}/translate"] = {
        "translatedText": "Hallo"}
    assert LibreTranslateBackend().translate("Hello", "en", "de") == "Hallo"


def test_libretranslate_needs_no_download(http):
    http.get_answers[f"{tb.LIBRETRANSLATE_URL}/languages"] = [
        {"code": "en"}, {"code": "de"}]
    assert LibreTranslateBackend().download("en", "de") is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. SCOPERTA
# ─────────────────────────────────────────────────────────────────────────────

def test_discovery_always_offers_something(http):
    """With nothing listening, Argos is still there to be installed."""
    options = discover_backends()
    assert options and options[-1].label == "Argos Translate"


def test_a_running_service_comes_first(http):
    http.get_answers[f"{tb.OLLAMA_URL}/api/tags"] = {"models": [{"name": "gemma3:4b"}]}
    options = discover_backends()
    assert options[0].label == "Ollama" and options[0].ready is True
    assert options[0].models == ["gemma3:4b"]


def test_discovery_picks_a_default_model(http):
    http.get_answers[f"{tb.OLLAMA_URL}/api/tags"] = {
        "models": [{"name": "codellama:70b"}, {"name": "gemma3:4b"}]}
    ollama = discover_backends()[0].backend
    assert ollama.model == "gemma3:4b", "a suggested model wins over the first"


def test_the_default_model_falls_back_to_what_is_there():
    assert _best_ollama_model(["something:1b"]) == "something:1b"
    assert _best_ollama_model([]) == ""


def test_discovery_can_be_faked_for_a_caller():
    marker = [BackendOption(object(), "Fake", "", True)]
    assert discover_backends(probe=lambda: marker) == marker


def test_a_detail_is_a_key_and_a_count_not_a_sentence(http):
    """The detail is shown in the editor's language, so this module must not
    format it: it shipped as "3 models available" in English for everyone."""
    http.get_answers[f"{tb.OLLAMA_URL}/api/tags"] = {
        "models": [{"name": "a"}, {"name": "b"}]}
    option = discover_backends()[0]
    assert option.detail_key == "tr_detail_models" and option.detail_count == 2
    assert option.detail_text == ""


def test_an_uninstallable_engine_carries_its_install_hint(http):
    argos = discover_backends()[-1]
    if not argos.ready:
        assert "argostranslate" in argos.detail_text


def test_discovery_never_raises_on_a_broken_service(monkeypatch):
    def explode(*_args, **_kw):
        raise OSError("connection reset")

    monkeypatch.setattr(tb.urllib.request, "urlopen", explode)
    options = discover_backends()
    assert options, "a broken service must not take discovery down"
