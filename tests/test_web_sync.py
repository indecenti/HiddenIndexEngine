"""
tests/test_web_sync.py

ARMATURA anti-drift tra engine Python e runtime web (editor/web_template/runtime.js).

Il runtime web REPLICA la logica dell'engine. Questi test falliscono se le
costanti condivise divergono o se un minigioco usato non e' implementato lato web.
Vedi WEB_EXPORT_SYNC.md.

Esegui:  pytest tests/test_web_sync.py -v
"""

from __future__ import annotations

import re
import json
import glob
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_JS = ROOT / "editor" / "web_template" / "runtime.js"
SYNC_DOC = ROOT / "WEB_EXPORT_SYNC.md"


def _engine_rules() -> dict:
    from editor.web_rules import engine_rules
    return engine_rules()


def _runtime_text() -> str:
    return RUNTIME_JS.read_text(encoding="utf-8")


def _extract_block(text: str, start_marker: str) -> str:
    """Estrae il corpo {...} di un oggetto JS dopo start_marker (bilanciando le graffe)."""
    i = text.index(start_marker)
    i = text.index("{", i)
    depth, j = 0, i
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise ValueError("blocco non bilanciato per " + start_marker)


def _parse_rules_defaults() -> dict:
    block = _extract_block(_runtime_text(), "const RULES_DEFAULTS")
    out = {}

    def num(key):
        m = re.search(rf"\b{key}:\s*([\d.]+)", block)
        return float(m.group(1)) if m else None

    out["points_per_object"] = num("points_per_object")
    out["bonus_time_max"] = num("bonus_time_max")
    out["miss_time_penalty"] = num("miss_time_penalty")
    out["miss_point_penalty"] = num("miss_point_penalty")
    out["bonus_ratio_3star"] = num("bonus_ratio_3star")
    out["hint_free"] = num("hint_free")
    out["hint_cooldown"] = num("hint_cooldown")
    out["hint_max_uses"] = num("hint_max_uses")
    out["ref_w"] = num("ref_w")
    out["ref_h"] = num("ref_h")

    m = re.search(r"hint_penalties:\s*\[([^\]]*)\]", block)
    out["hint_penalties"] = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else None

    m = re.search(r"star_multiplier:\s*\{([^}]*)\}", block)
    sm = {}
    if m:
        for k, v in re.findall(r"(\d+)\s*:\s*(\d+)", m.group(1)):
            sm[k] = int(v)
    out["star_multiplier"] = sm
    return out


# ── Test ────────────────────────────────────────────────────────────────────

def test_runtime_defaults_match_engine():
    """I fallback RULES_DEFAULTS in runtime.js devono restare allineati all'engine."""
    eng = _engine_rules()
    js = _parse_rules_defaults()
    scalars = ["points_per_object", "bonus_time_max", "miss_time_penalty",
               "miss_point_penalty", "bonus_ratio_3star", "hint_free",
               "hint_cooldown", "hint_max_uses", "ref_w", "ref_h"]
    for k in scalars:
        assert float(eng[k]) == float(js[k]), (
            f"DRIFT su '{k}': engine={eng[k]} ma runtime.js RULES_DEFAULTS={js[k]}. "
            f"Aggiorna RULES_DEFAULTS in editor/web_template/runtime.js (vedi WEB_EXPORT_SYNC.md)."
        )
    assert eng["hint_penalties"] == js["hint_penalties"], (
        f"DRIFT hint_penalties: engine={eng['hint_penalties']} runtime={js['hint_penalties']}"
    )
    eng_sm = {str(k): v for k, v in eng["star_multiplier"].items()}
    assert eng_sm == js["star_multiplier"], (
        f"DRIFT star_multiplier: engine={eng_sm} runtime={js['star_multiplier']}"
    )


def test_used_minigames_are_implemented():
    """Ogni minigame_trigger usato nei giochi deve avere una classe JS in MINIGAME_CLASSES."""
    block = _extract_block(_runtime_text(), "const MINIGAME_CLASSES")
    implemented = set(re.findall(r"(\w+)\s*:", block))

    used = set()
    for f in glob.glob(str(ROOT / "games" / "*" / "levels" / "**" / "scene.json"), recursive=True):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for o in data.get("objects", []):
            trig = o.get("minigame_trigger")
            if trig and trig.get("minigame_id"):
                used.add(trig["minigame_id"])

    missing = used - implemented
    assert not missing, (
        f"Minigiochi usati nei giochi ma NON implementati nel runtime web: {sorted(missing)}. "
        f"Implementali in runtime.js (MINIGAME_CLASSES) o gestisci il fallback. Implementati: {sorted(implemented)}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_runtime_js_syntax_valid():
    """runtime.js deve essere sintatticamente valido (node --check)."""
    r = subprocess.run(["node", "--check", str(RUNTIME_JS)], capture_output=True, text=True)
    assert r.returncode == 0, f"Errore di sintassi in runtime.js:\n{r.stderr}"


def test_sync_contract_present():
    """Il contratto di sincronizzazione deve esistere."""
    assert SYNC_DOC.exists(), "WEB_EXPORT_SYNC.md mancante: e' il contratto engine<->web."
