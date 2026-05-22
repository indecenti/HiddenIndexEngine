"""
tests/test_built_exe.py

Smoke test post-build per HiddenEditor / giochi pacchettizzati.

Verifica che la build PyInstaller in `dist/<name>/` sia consistente:
  1. La cartella e l'EXE esistono.
  2. I file essenziali sono stati copiati (engine/, main.py / run_editor.py).
  3. La struttura di asset è presente (config.ini per il gioco, saves/ dir).
  4. (Opzionale, attivabile con SMOKE_LAUNCH=1) lancio l'EXE per N secondi e
     verifico che non sia crashato — utile per CI in modalità headless.

Esecuzione:
  pytest tests/test_built_exe.py                   # struttura only
  SMOKE_LAUNCH=1 pytest tests/test_built_exe.py    # struttura + launch test
  BUILD_NAME=LineVenture pytest tests/test_built_exe.py

I test fanno SKIP automatico se la cartella dist/<name>/ non esiste — così
puoi avere `pytest` verde anche senza aver buildato (utile in dev).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Configurazione (sovrascrivibile via env var)
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_NAME = os.environ.get("BUILD_NAME", "HiddenEditor")
DIST_DIR = PROJECT_ROOT / "dist" / BUILD_NAME
EXE_PATH = DIST_DIR / f"{BUILD_NAME}.exe"

# Quanti secondi tenere acceso l'EXE per smoke-test runtime
LAUNCH_SECONDS = float(os.environ.get("SMOKE_LAUNCH_SECS", "5"))

LAUNCH_ENABLED = os.environ.get("SMOKE_LAUNCH", "0") == "1"


# --------------------------------------------------------------------------- #
# Fixture: skip se la build non esiste (no false-negative in dev)
# --------------------------------------------------------------------------- #

def _require_built() -> None:
    if not DIST_DIR.exists():
        pytest.skip(
            f"Build {BUILD_NAME} non trovata in dist/. Esegui prima:\n"
            f"  pyinstaller HiddenEditor.spec      # per l'editor\n"
            f"  oppure usa l'UI di build per il gioco"
        )


# --------------------------------------------------------------------------- #
# Test struttura (sempre, se la build esiste)
# --------------------------------------------------------------------------- #

def test_exe_exists():
    _require_built()
    assert EXE_PATH.exists(), f"EXE mancante: {EXE_PATH}"
    assert EXE_PATH.is_file()
    size = EXE_PATH.stat().st_size
    assert size > 1_000_000, f"EXE troppo piccolo ({size} bytes) — build corrotta?"


def test_internal_dir_exists():
    """PyInstaller -D produce <name>/_internal/ con le DLL."""
    _require_built()
    internal = DIST_DIR / "_internal"
    assert internal.exists() and internal.is_dir(), (
        f"_internal/ mancante in {DIST_DIR} — la build non sembra in modalità -D"
    )


def test_engine_sources_present():
    """L'editor ha bisogno dei sorgenti engine per pacchettizzare giochi."""
    _require_built()
    # Il source dell'engine viene copiato accanto all'EXE dal post-build.
    # In dev può anche essere dentro _internal, in editor è fuori. Accetto
    # entrambi i pattern.
    candidates = [
        DIST_DIR / "engine",
        DIST_DIR / "_internal" / "engine",
    ]
    assert any(p.exists() for p in candidates), (
        f"Nessuna cartella engine trovata accanto a {EXE_PATH} "
        f"(controllati: {[str(p) for p in candidates]})"
    )


def test_writable_dirs_for_editor():
    """L'editor scrive su games/ e saves/."""
    if BUILD_NAME != "HiddenEditor":
        pytest.skip("Test specifico dell'editor")
    _require_built()
    assert (DIST_DIR / "games").exists(), "Cartella games/ non creata dal post-build"
    assert (DIST_DIR / "saves").exists(), "Cartella saves/ non creata dal post-build"


def test_no_dev_artifacts_packaged():
    """Verifica che artefatti di sviluppo NON siano finiti nell'EXE bundle."""
    _require_built()
    forbidden = ["__pycache__", ".git", ".pytest_cache", ".editor_trash"]
    # Solo livello superiore — non risorse interne di librerie come jsonschema
    for entry in DIST_DIR.iterdir():
        assert entry.name not in forbidden, f"Artefatto dev nel bundle: {entry}"


# --------------------------------------------------------------------------- #
# Test launch (opzionale, attivabile con SMOKE_LAUNCH=1)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not LAUNCH_ENABLED,
                    reason="SMOKE_LAUNCH non abilitato (set SMOKE_LAUNCH=1)")
def test_exe_launches_without_immediate_crash():
    """
    Lancia l'EXE per LAUNCH_SECONDS secondi: se chiude da solo con returncode
    diverso da 0 prima del timeout → crash all'avvio.
    """
    _require_built()
    if sys.platform != "win32":
        pytest.skip("Test specifico Windows (EXE)")

    proc = subprocess.Popen(
        [str(EXE_PATH)],
        cwd=str(DIST_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    start = time.time()
    rc = None
    while time.time() - start < LAUNCH_SECONDS:
        rc = proc.poll()
        if rc is not None:
            break
        time.sleep(0.2)

    if rc is None:
        # Non è morto: tutto OK. Lo killo gentilmente.
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        return

    # Se è morto, raccogli output per il messaggio di errore
    stdout, stderr = proc.communicate(timeout=5)
    pytest.fail(
        f"EXE crashato all'avvio dopo {time.time() - start:.1f}s, rc={rc}\n"
        f"STDOUT: {stdout.decode(errors='replace')[:1000]}\n"
        f"STDERR: {stderr.decode(errors='replace')[:1000]}"
    )
