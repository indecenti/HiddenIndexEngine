"""
tests/test_web_sync.py

ARMATURA anti-drift tra engine Python e runtime web (editor/web_template/runtime/).

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
RUNTIME_DIR = ROOT / "editor" / "web_template" / "runtime"
SYNC_DOC = ROOT / "WEB_EXPORT_SYNC.md"


def _engine_rules() -> dict:
    from editor.web_rules import engine_rules
    return engine_rules()


def _runtime_files() -> list[Path]:
    """Tutti i moduli sorgente del runtime web (core, game, minigiochi, bootstrap)."""
    files = [RUNTIME_DIR / "core.js", RUNTIME_DIR / "game.js"]
    files += sorted((RUNTIME_DIR / "minigames").glob("*.js"))
    files.append(RUNTIME_DIR / "bootstrap.js")
    return [f for f in files if f.exists()]


def _runtime_text() -> str:
    """Concatenazione dei moduli runtime (come il bundle prodotto dall'exporter)."""
    return "\n".join(f.read_text(encoding="utf-8") for f in _runtime_files())


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

    out["miss_combo_window"] = num("miss_combo_window")
    m = re.search(r"miss_penalty_curve:\s*\[([^\]]*)\]", block)
    out["miss_penalty_curve"] = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else None
    return out


# ── Test ────────────────────────────────────────────────────────────────────

def test_runtime_defaults_match_engine():
    """I fallback RULES_DEFAULTS in runtime.js devono restare allineati all'engine."""
    eng = _engine_rules()
    js = _parse_rules_defaults()
    scalars = ["points_per_object", "bonus_time_max", "miss_time_penalty",
               "miss_point_penalty", "miss_combo_window", "bonus_ratio_3star",
               "hint_free", "hint_cooldown", "hint_max_uses", "ref_w", "ref_h"]
    for k in scalars:
        assert float(eng[k]) == float(js[k]), (
            f"DRIFT su '{k}': engine={eng[k]} ma runtime.js RULES_DEFAULTS={js[k]}. "
            f"Aggiorna RULES_DEFAULTS in editor/web_template/runtime/core.js (vedi WEB_EXPORT_SYNC.md)."
        )
    assert eng["hint_penalties"] == js["hint_penalties"], (
        f"DRIFT hint_penalties: engine={eng['hint_penalties']} runtime={js['hint_penalties']}"
    )
    assert eng["miss_penalty_curve"] == js["miss_penalty_curve"], (
        f"DRIFT miss_penalty_curve: engine={eng['miss_penalty_curve']} "
        f"runtime={js['miss_penalty_curve']}"
    )
    eng_sm = {str(k): v for k, v in eng["star_multiplier"].items()}
    assert eng_sm == js["star_multiplier"], (
        f"DRIFT star_multiplier: engine={eng_sm} runtime={js['star_multiplier']}"
    )


def test_used_minigames_are_implemented():
    """Ogni minigame_trigger usato nei giochi deve avere un modulo JS in runtime/minigames/."""
    implemented = {p.stem for p in (RUNTIME_DIR / "minigames").glob("*.js")}

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
        f"Crea il modulo runtime/minigames/<id>.js (auto-registrato) o gestisci il fallback. "
        f"Implementati: {sorted(implemented)}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_runtime_js_syntax_valid():
    """Ogni modulo del runtime web deve essere sintatticamente valido (node --check)."""
    for f in _runtime_files():
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"Errore di sintassi in {f.name}:\n{r.stderr}"


def test_sync_contract_present():
    """Il contratto di sincronizzazione deve esistere."""
    assert SYNC_DOC.exists(), "WEB_EXPORT_SYNC.md mancante: e' il contratto engine<->web."


# ── Parita' COMPORTAMENTALE dello scoring (non solo costanti) ─────────────────
#
# test_runtime_defaults_match_engine garantisce solo che le COSTANTI coincidano.
# Questo test pilota la FORMULA di fine scena su una griglia di input fissi
# (golden vector) attraverso ENTRAMBI i runtime e pretende output identici:
#   - Python: engine.level_manager.LevelManager.compute_scene_score (sorgente)
#   - JS:     game.js::_doFinish, eseguita davvero via tests/js/score_parity_harness.js
# Cosi' una divergenza di formula (es. Math.round vs int(), soglia stelle)
# diventa un fallimento di test invece di un bug silenzioso lato web.

HARNESS_JS = ROOT / "tests" / "js" / "score_parity_harness.js"
GAME_JS = RUNTIME_DIR / "game.js"


def _score_golden_cases() -> list[dict]:
    """Casi (score, timeLeft, timeTotal, found, total) con failed=False.

    Coprono: rapporto tempo pieno, boundary 3 stelle a 0.66, casi dove il
    troncamento differisce dall'arrotondamento, bonus zero, scena incompleta
    (found < total) e timeTotal = 0.
    """
    cases: list[dict] = []
    time_pairs = [
        (1000.0, 1000.0),   # ratio 1.0   -> bonus 500, 3 stelle
        (660.0, 1000.0),    # ratio 0.66  -> bonus 330, 3 stelle (boundary)
        (659.6, 1000.0),    # 329.8 -> trunc 329 (2 stelle) ma round 330 (3 stelle)
        (500.0, 1000.0),    # ratio 0.5   -> bonus 250, 2 stelle
        (333.4, 1000.0),    # 166.7 -> trunc 166
        (1.0, 1000.0),      # 0.5 -> trunc 0
        (0.0, 1000.0),      # bonus 0, allFound -> 2 stelle
    ]
    for score in (0, 100, 250, 1000):
        for total in (3, 5):
            for time_left, time_total in time_pairs:
                cases.append({"score": score, "timeLeft": time_left,
                              "timeTotal": time_total, "found": total, "total": total})
            # scena incompleta: bonus 0, 1 stella
            cases.append({"score": score, "timeLeft": 800.0, "timeTotal": 1000.0,
                          "found": total - 1, "total": total})
    # edge: timeTotal = 0 (nessun bonus possibile su entrambi i lati)
    cases.append({"score": 100, "timeLeft": 0.0, "timeTotal": 0.0, "found": 3, "total": 3})
    return cases


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_scene_score_parity_python_vs_js():
    """La formula di scoring di fine scena deve dare risultati identici su Python e JS."""
    from engine.level_manager import LevelManager

    eng = _engine_rules()
    js_rules = {
        "bonus_time_max": eng["bonus_time_max"],
        "bonus_ratio_3star": eng["bonus_ratio_3star"],
        # le chiavi di star_multiplier servono come indice in JS -> stringhe
        "star_multiplier": {str(k): v for k, v in eng["star_multiplier"].items()},
        "miss_point_penalty": eng["miss_point_penalty"],
    }
    cases = _score_golden_cases()
    proc = subprocess.run(
        ["node", str(HARNESS_JS), str(GAME_JS)],
        input=json.dumps({"rules": js_rules, "cases": cases}),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"harness JS fallito (rc={proc.returncode}):\n{proc.stderr}"
    js_out = json.loads(proc.stdout)["scores"]
    assert len(js_out) == len(cases), "numero di risultati JS != numero di casi"

    mismatches = []
    for c, js in zip(cases, js_out):
        time_elapsed = c["timeTotal"] - c["timeLeft"]
        py_bonus, py_stars, py_score = LevelManager.compute_scene_score(
            c["found"], c["total"], c["score"], time_elapsed, c["timeTotal"], False
        )
        if (py_bonus, py_stars, py_score) != (js["bonus"], js["stars"], js["score"]):
            mismatches.append(
                f"  {c}: python=(bonus={py_bonus},stars={py_stars},score={py_score}) "
                f"!= js=(bonus={js['bonus']},stars={js['stars']},score={js['score']})"
            )
    assert not mismatches, (
        "DRIFT scoring Python<->JS (game.js::_doFinish vs "
        "LevelManager.compute_scene_score):\n" + "\n".join(mismatches) +
        "\nAllinea la formula in editor/web_template/runtime/game.js (vedi WEB_EXPORT_SYNC.md)."
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_miss_penalty_parity_python_vs_js():
    """La curva di penalita' miss progressiva deve dare valori identici su Python e JS."""
    from engine.level_manager import LevelManager

    eng = _engine_rules()
    js_rules = {
        "miss_penalty_curve": list(eng["miss_penalty_curve"]),
        "miss_point_penalty": eng["miss_point_penalty"],
        "miss_combo_window": eng["miss_combo_window"],
    }
    consec = list(range(1, 9))  # 1..8: oltre la lunghezza della curva deve clampare all'ultimo valore
    proc = subprocess.run(
        ["node", str(HARNESS_JS), str(GAME_JS)],
        input=json.dumps({"rules": js_rules, "cases": [], "missConsecutive": consec}),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"harness JS fallito (rc={proc.returncode}):\n{proc.stderr}"
    js_pen = json.loads(proc.stdout)["missPenalties"]
    py_pen = [LevelManager.miss_penalty(n) for n in consec]
    assert py_pen == js_pen, (
        f"DRIFT penalita' miss Python<->JS:\n  python={py_pen}\n  js    ={js_pen}\n"
        "Allinea game.js::_missPenalty o la curva (vedi WEB_EXPORT_SYNC.md)."
    )


# NOTA / TODO parita' ANCORA da coprire (divergenze note, NON ancora pinnate):
#   - Incremento hint da combo (+0.02/livello): l'engine lo applica solo se il gioco
#     definisce hint_earn_config.combo_thresholds; NESSUN gioco attuale lo fa, quindi
#     combo_level=0 ed e' INERTE oggi (la curva 0.20/0.143/0.112/0.05 e' gia' identica
#     tra Python e JS). Per pinnarlo serve far fluire hint_earn_config nel manifest e
#     replicare _check_combo_threshold lato JS.
#   - first_second_bonus (+50 punteggio se il PRIMO oggetto e' trovato entro 1.0s):
#     l'engine (RewardTracker.on_object_found) lo aggiunge, il web no. Divergenza di
#     punteggio reale ma minore; allineabile esponendolo nelle rules + aggiungendolo
#     in game.js _onPointer.
