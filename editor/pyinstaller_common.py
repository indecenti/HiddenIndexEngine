"""
editor/pyinstaller_common.py

Configurazione PyInstaller CONDIVISA tra:
  - HiddenEditor.spec       (build dell'editor)
  - build_editor.py         (build dell'editor via subprocess)
  - editor/build_system.py  (build dei giochi standalone)

Single source of truth: modificare QUI minigiochi/excludes/hiddenimports
si propaga automaticamente ai tre punti.

Importante: nessuna dipendenza da pygame o moduli pesanti — questo file
viene caricato anche dentro lo .spec di PyInstaller (ambiente vergine).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Esclusioni "pesanti" — moduli che PyInstaller può trovare via dipendenze
# transitive ma che NON servono al gioco e gonfierebbero l'EXE di centinaia
# di MB. Lista basata su PACKAGE_SIZE_FIX.md.
# ---------------------------------------------------------------------------

HEAVY_EXCLUDES: list[str] = [
    # Deep learning
    "torch", "torchvision", "torchaudio", "onnxruntime",
    "transformers", "tokenizers",
    # Data science (mai usata dal motore)
    "sklearn", "matplotlib", "pandas", "pyarrow",
    "llvmlite", "numba", "lxml",
    # Notebook / IDE
    "IPython", "notebook", "jupyter",
]


# ---------------------------------------------------------------------------
# Dipendenze base — sempre incluse in EVERY build (editor + ogni gioco).
# ---------------------------------------------------------------------------

# Moduli che devono essere import-resolvable da PyInstaller anche se non
# vengono trovati per analisi statica del bytecode.
BASE_HIDDEN_IMPORTS: list[str] = [
    "cv2",            # background MP4 — può essere assente, l'engine fa graceful fallback
    "numpy",
    "scipy.ndimage",  # warp prospettico
]

# Pacchetti per cui serve `collect_all` (entry points / data files).
BASE_COLLECT_ALL: list[str] = [
    "jsonschema",
    "jsonschema_specifications",
    "rpds",
]


# ---------------------------------------------------------------------------
# Discovery dinamica dei minigiochi
# ---------------------------------------------------------------------------

def discover_minigame_imports(project_root: Path | str,
                              limit_to: Iterable[str] | None = None) -> list[str]:
    """
    Restituisce gli hidden import per i minigiochi presenti in
    `<project_root>/engine/minigames/`. Convenzione: ogni minigame è una
    sotto-cartella con file `<id>_game.py`.

    Args:
        project_root: root del progetto (Path o stringa).
        limit_to: se passato, restringe ai soli minigiochi nell'iterable
                  (usato dal build per-gioco per non imballare i minigame
                  non usati).

    Returns lista di stringhe pronte per `--hidden-import=<...>`.
    """
    root = Path(project_root)
    mg_dir = root / "engine" / "minigames"
    if not mg_dir.exists():
        return []

    wanted: set[str] | None = set(limit_to) if limit_to is not None else None
    imports: list[str] = []
    for sub in sorted(mg_dir.iterdir()):
        if not sub.is_dir() or sub.name in ("__pycache__",):
            continue
        mg_id = sub.name
        if wanted is not None and mg_id not in wanted:
            continue
        if (sub / f"{mg_id}_game.py").exists():
            imports.append(f"engine.minigames.{mg_id}.{mg_id}_game")
    return imports


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def read_version(project_root: Path | str) -> str:
    """
    Legge la versione dal file `VERSION` nella root del progetto.
    Fallback a '0.0.0-dev' se assente.
    """
    p = Path(project_root) / "VERSION"
    if p.exists():
        v = p.read_text(encoding="utf-8").strip()
        if v:
            return v
    return "0.0.0-dev"


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    """Converte 'A.B.C[-suffix]' in (A, B, C, 0) per resource Windows."""
    core = version.split("-", 1)[0]
    parts = (core.split(".") + ["0", "0", "0", "0"])[:4]
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)  # type: ignore[return-value]


def write_version_info(project_root: Path | str,
                       *,
                       product_name: str = "HiddenEngine",
                       file_description: str = "HiddenEngine — game engine for hidden object games",
                       company: str = "HiddenEngine") -> Path:
    """
    Genera il file `version_info.txt` Windows (resource embedded nell'EXE).
    Lo .spec lo passa come `version=` a EXE(). Returns il path generato.

    Il file viene scritto in `<project_root>/build/version_info.txt` (cartella
    già usata da PyInstaller per i suoi build artefacts, gitignorabile).
    """
    root = Path(project_root)
    version = read_version(root)
    vt = _version_tuple(version)

    out_dir = root / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / "version_info.txt"

    content = f"""# Generato da editor/pyinstaller_common.write_version_info()
# Non modificare a mano: aggiorna VERSION e rebuilda.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'{company}'),
          StringStruct(u'FileDescription', u'{file_description}'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'ProductName', u'{product_name}'),
          StringStruct(u'ProductVersion', u'{version}'),
        ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
"""
    out_p.write_text(content, encoding="utf-8")
    return out_p


# ---------------------------------------------------------------------------
# Helper per costruire i flag CLI di PyInstaller
# ---------------------------------------------------------------------------

def build_cli_args(entry_point: Path | str,
                   *,
                   name: str,
                   project_root: Path | str,
                   onedir: bool = True,
                   windowed: bool = True,
                   icon: Path | str | None = None,
                   extra_hidden: Iterable[str] = (),
                   extra_excludes: Iterable[str] = (),
                   limit_minigames: Iterable[str] | None = None) -> list[str]:
    """
    Costruisce la lista di argomenti CLI di PyInstaller.

    Riproducibile: stessi input → stessi argomenti, sempre.
    """
    args: list[str] = [
        "pyinstaller",
        str(entry_point),
        "-y",              # sovrascrive dist senza prompt
        "--clean",
        f"--name={name}",
    ]
    if onedir:
        args.append("-D")
    else:
        args.append("-F")
    if windowed:
        args.append("-w")

    if icon is not None:
        icon_p = Path(icon)
        if icon_p.exists():
            args.append(f"--icon={icon_p}")

    # collect-all
    for pkg in BASE_COLLECT_ALL:
        args.append(f"--collect-all={pkg}")

    # hidden imports base + minigiochi + extra
    all_hidden = list(BASE_HIDDEN_IMPORTS)
    all_hidden += discover_minigame_imports(project_root, limit_to=limit_minigames)
    all_hidden += list(extra_hidden)
    for h in all_hidden:
        args.append(f"--hidden-import={h}")

    # excludes
    all_excludes = list(HEAVY_EXCLUDES) + list(extra_excludes)
    for ex in all_excludes:
        args.append(f"--exclude-module={ex}")

    return args


# ---------------------------------------------------------------------------
# CLI di self-test (utile per CI: verifica che il file sia importabile e
# che la discovery dei minigame funzioni).
# ---------------------------------------------------------------------------

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(f"project_root: {root}")
    print(f"version: {read_version(root)}")
    print(f"heavy_excludes ({len(HEAVY_EXCLUDES)}): {HEAVY_EXCLUDES[:5]}...")
    print(f"base_hidden_imports: {BASE_HIDDEN_IMPORTS}")
    print(f"base_collect_all: {BASE_COLLECT_ALL}")
    minigames = discover_minigame_imports(root)
    print(f"minigames discovered ({len(minigames)}):")
    for mg in minigames:
        print(f"  - {mg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
