"""
engine/utils.py

Funzioni di utilità fondamentali per tutto il motore.
PRIMO FILE DA CARICARE — usato da ogni altro modulo.

Gestisce:
- Path alle risorse (compatibile con PyInstaller EXE)
- Path ai file scrivibili (salvataggi, config)
- Logging centralizzato
- Flag DEBUG per Developer Mode
- Safe file operations (atomic JSON write, delete con cestino)
"""

import os
import sys
import math
import json
import shutil
import logging
import datetime
import pygame
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

# ---------------------------------------------------------------------------
# Flag globale Developer Mode
# Impostato a True solo in sviluppo. PyInstaller lo compilerà come False.
# ---------------------------------------------------------------------------
DEBUG: bool = not getattr(sys, "frozen", False)


# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------

def is_android_runtime() -> bool:
    # python-for-android imposta queste env vars all'avvio dell'app
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ


def get_android_safe_insets() -> tuple[int, int, int, int]:
    """Inset (left, top, right, bottom) in PIXEL FISICI del display cutout +
    barre di sistema. Best-effort via pyjnius: (0,0,0,0) su desktop o se non
    disponibile (API < 28, finestra non ancora attached, ecc.)."""
    if not is_android_runtime():
        return (0, 0, 0, 0)
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        if activity is None:
            return (0, 0, 0, 0)
        decor = activity.getWindow().getDecorView()
        insets = decor.getRootWindowInsets()
        if insets is None:
            return (0, 0, 0, 0)
        l = t = r = b = 0
        try:
            cutout = insets.getDisplayCutout()  # API 28+
            if cutout is not None:
                l = max(l, cutout.getSafeInsetLeft())
                t = max(t, cutout.getSafeInsetTop())
                r = max(r, cutout.getSafeInsetRight())
                b = max(b, cutout.getSafeInsetBottom())
        except Exception:
            pass
        return (int(l), int(t), int(r), int(b))
    except Exception:
        return (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Path management
# ---------------------------------------------------------------------------

def get_base_path() -> Path:
    """Path base corretto per sviluppo, EXE PyInstaller e APK Android."""
    if is_android_runtime():
        # p4a unpacka i file dell'app dentro ANDROID_PRIVATE/app
        return Path(os.environ.get('ANDROID_PRIVATE', '/data/data')) / 'app'
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # Risale alla root partendo da questo file (modifica parents[N] in base alla profondità)
    return Path(__file__).resolve().parents[1]


def get_resource_path(*parts: str) -> Path:
    """
    Restituisce il path a una risorsa di sola lettura del progetto.
    Cerca PRIMA all'esterno (permette override utente) e poi nel bundle (se frozen).
    """
    # 1. Prova all'esterno (sviluppo o asset distribuiti accanto all'EXE)
    base = get_base_path()
    external_path = base.joinpath(*parts)
    if external_path.exists():
        return external_path

    # 2. Fallback all'interno del bundle PyInstaller (se presente e non trovato fuori)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        internal_path = Path(sys._MEIPASS).joinpath(*parts)
        if internal_path.exists():
            return internal_path

    return external_path


def get_writable_path(*parts: str) -> Path:
    """
    Restituisce il path per file che devono essere scritti (salvataggi, config utente, log).
    Desktop: get_base_path() / "saves".
    Android: ANDROID_PRIVATE / "saves" (internal storage privato app, no permessi runtime).
    La cartella viene creata automaticamente se non esiste.
    """
    if is_android_runtime():
        base = Path(os.environ['ANDROID_PRIVATE']) / "saves"
    else:
        base = get_base_path() / "saves"
    base.mkdir(parents=True, exist_ok=True)

    path = base
    for p in parts:
        path = path / p

    if path.parent != base:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_user_config_path() -> Path:
    """Path del config.ini SCRIVIBILE con le preferenze utente (volumi, display).

    Desktop: get_base_path()/config.ini (posizione storica, immutata).
    Android: get_writable_path("config.ini") -> ANDROID_PRIVATE/saves/config.ini,
    perche' la dir di unpack dell'app (get_base_path()) e' READ-ONLY a runtime: una
    scrittura li' fallisce e le preferenze andrebbero perse ad ogni riavvio.

    All'avvio (main.py) i default bundlati vanno letti da get_base_path()/config.ini
    e POI sovrascritti da questo file utente (se esiste)."""
    if is_android_runtime():
        return get_writable_path("config.ini")
    return get_base_path() / "config.ini"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configura il logger globale del motore."""
    # In sviluppo: DEBUG su stdout + file
    # In exe: INFO su file (non WARNING — altrimenti i crash non vengono loggati)
    level = logging.DEBUG if DEBUG else logging.INFO
    log_path = get_writable_path("engine.log")

    handlers: list[logging.Handler] = [logging.FileHandler(str(log_path), encoding="utf-8")]
    if DEBUG:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def get_logger(name: str) -> logging.Logger:
    """Restituisce un logger con il nome del modulo chiamante."""
    return logging.getLogger(name)


# Tiene vivo il file di faulthandler per tutta la durata del processo.
_FAULT_LOG_FH = None


def install_crash_handlers() -> None:
    """Cattura i crash che altrimenti non lascerebbero traccia in engine.log.

    Due categorie distinte, entrambe invisibili senza questo hook quando l'app
    gira windowed (pythonw / exe PyInstaller) ma anche da console se l'utente
    la chiude subito:
      1. Segfault nativi (torch/CLIP/numpy/pygame): faulthandler scrive lo stack
         C/Python su 'crash_native.log'.
      2. Eccezioni Python non gestite che sfuggono dal main loop: sys.excepthook
         le logga su engine.log invece di mandarle solo su stderr.
    Idempotente: chiamabile più volte senza effetti collaterali.
    """
    global _FAULT_LOG_FH
    try:
        import faulthandler
        if _FAULT_LOG_FH is None:
            fault_path = get_writable_path("crash_native.log")
            _FAULT_LOG_FH = open(str(fault_path), "w", encoding="utf-8")
            faulthandler.enable(file=_FAULT_LOG_FH, all_threads=True)
    except Exception:
        pass

    prev_hook = sys.excepthook

    def _log_uncaught(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logging.getLogger("crash").critical(
                "Eccezione non gestita (crash)",
                exc_info=(exc_type, exc_value, exc_tb),
            )
        prev_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _log_uncaught


# ---------------------------------------------------------------------------
# Safe file operations — atomic write + soft-delete trash
# ---------------------------------------------------------------------------
#
# Tutte le scritture JSON dell'editor passano per `safe_write_json`: scrive su
# file `.tmp` siblings, fsync, poi os.replace atomico. Un crash a metà write
# non corrompe più il catalogo / la scena / il save.
#
# Tutte le eliminazioni distruttive passano per `safe_delete`: il file viene
# SPOSTATO in `.editor_trash/<sessione>/...` (preservando la struttura della
# cartella sorgente) e ogni operazione è loggata in `.editor_audit.log`.
# Niente cancellazioni silenziose: ogni delete è recuperabile dal cestino e
# tracciato nell'audit log.
#
# Il cestino non viene mai svuotato automaticamente al boot. La pulizia
# avviene SOLO via `cleanup_trash(max_age_days=...)` chiamata esplicitamente.

# Timestamp di sessione: tutti i file cancellati nella stessa esecuzione
# finiscono nella stessa sottocartella del cestino (raggruppamento naturale).
_SESSION_TS: str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
_TRASH_DIRNAME: str = ".editor_trash"
_AUDIT_LOG_NAME: str = ".editor_audit.log"


def _get_trash_root() -> Path:
    """Cartella radice del cestino: <base_path>/.editor_trash/"""
    return get_base_path() / _TRASH_DIRNAME


def _get_audit_log_path() -> Path:
    """File di audit append-only delle operazioni distruttive."""
    return get_base_path() / _AUDIT_LOG_NAME


def _audit_log(action: str, path: Union[str, Path], detail: str = "") -> None:
    """
    Append-only di una riga nell'audit log. Non solleva mai eccezioni:
    l'audit deve essere best-effort, mai bloccare l'operazione utente.
    """
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts}\t{action}\t{path}\t{detail}\n"
        with open(_get_audit_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Audit silenzioso solo qui — è già un best-effort
        logging.getLogger(__name__).debug("audit log write failed", exc_info=True)


def safe_write_json(path: Union[str, Path], data, *, indent: int = 2,
                    ensure_ascii: bool = False, sort_keys: bool = False) -> bool:
    """
    Scrive `data` come JSON in `path` in modo atomico e crash-safe.

    Strategia:
      1. Serializza i dati prima di toccare il filesystem (se la serializzazione
         fallisce, il file originale rimane intatto).
      2. Scrive su file temporaneo sibling (`<path>.tmp`).
      3. flush + fsync per garantire che i bytes siano effettivamente su disco.
      4. os.replace(tmp, path): rename atomico su POSIX e su Windows (Python ≥3.3).
      5. Best-effort fsync della directory padre su POSIX (no-op su Windows).

    Returns True se tutto è andato a buon fine, False altrimenti.
    Errori loggati ma non sollevati (compatibile con l'API del vecchio _save_json).
    """
    p = Path(path)
    log = logging.getLogger(__name__)
    try:
        # 1. Serializza PRIMA di aprire il file: se i dati non sono serializzabili,
        #    il file originale resta intatto.
        payload = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii,
                             sort_keys=sort_keys)
    except (TypeError, ValueError) as e:
        log.error(f"safe_write_json: serializzazione fallita per {p}: {e}")
        return False

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")

    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Filesystem che non supporta fsync (es. alcuni mount di rete).
                # Non fatale: il payload è già in cache OS.
                pass
        os.replace(tmp, p)

        # Best-effort fsync della directory padre (POSIX). Su Windows os.open
        # di una directory non è supportato — questo blocco è no-op silenzioso.
        try:
            dir_fd = os.open(str(p.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            pass

        return True
    except Exception as e:
        log.error(f"safe_write_json: scrittura atomica fallita per {p}: {e}")
        # Cleanup del tmp orfano se è rimasto
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def safe_delete(path: Union[str, Path], reason: str = "", *,
                also_remove_empty_parent: bool = False) -> bool:
    """
    Cancella `path` spostandolo nel cestino locale (`.editor_trash/<sessione>/`).

    Caratteristiche:
      - File O directory accettati (per directory usa shutil.move ricorsivo).
      - Path NON esistente: ritorna True (nothing to do) senza warning.
      - Conflict-safe: se nel cestino esiste già un file con lo stesso nome
        (perché cancellato due volte nella stessa sessione), accoda un suffisso
        numerico — non si sovrappone mai.
      - Audit log: ogni delete loggata in `.editor_audit.log` (timestamp, path,
        path nel cestino, reason).
      - `also_remove_empty_parent`: se True, dopo la delete tenta di rmdir() la
        cartella padre se rimane vuota (utile per cleanup ricorsivo). Mai
        ricorsivo verso l'alto: una sola directory.

    Returns True su successo (o se il file non esisteva), False su errore.
    NON solleva eccezioni: chi chiama può ispezionare il return value.
    """
    log = logging.getLogger(__name__)
    p = Path(path)

    if not p.exists():
        log.debug(f"safe_delete: path inesistente, nothing to do: {p}")
        return True

    try:
        # Path assoluto per audit + per costruire la struttura del cestino
        abs_p = p.resolve()
        base = get_base_path().resolve()

        # Costruisce il path di destinazione nel cestino preservando la
        # struttura relativa al base_path quando possibile.
        try:
            rel = abs_p.relative_to(base)
        except ValueError:
            # File fuori dal base_path (es. cancellazione di un file utente
            # selezionato altrove): usa solo il nome.
            rel = Path(abs_p.name)

        trash_dest = _get_trash_root() / _SESSION_TS / rel
        trash_dest.parent.mkdir(parents=True, exist_ok=True)

        # Conflict resolution: se esiste già (es. stesso file cancellato due
        # volte), accoda suffisso numerico.
        final_dest = trash_dest
        n = 1
        while final_dest.exists():
            final_dest = trash_dest.with_name(f"{trash_dest.stem}__{n}{trash_dest.suffix}")
            n += 1

        shutil.move(str(abs_p), str(final_dest))
        _audit_log("DELETE", str(abs_p), f"trash={final_dest} reason={reason}")
        log.info(f"safe_delete: {abs_p} → trash ({reason or 'no reason'})")

        # Opzionale: rimuovi la cartella padre se rimasta vuota
        if also_remove_empty_parent:
            try:
                parent = abs_p.parent
                if parent.exists() and parent != base and not any(parent.iterdir()):
                    parent.rmdir()
                    log.debug(f"safe_delete: rimossa cartella padre vuota {parent}")
            except OSError:
                # Non vuota o permessi: ignorato
                pass

        return True

    except Exception as e:
        log.error(f"safe_delete: fallita eliminazione di {p}: {e}", exc_info=DEBUG)
        _audit_log("DELETE_FAILED", str(p), f"error={e} reason={reason}")
        return False


def cleanup_trash(max_age_days: int = 7) -> int:
    """
    Rimuove definitivamente le sessioni del cestino più vecchie di `max_age_days`.
    Mai chiamata automaticamente: deve essere invocata esplicitamente (menu
    'Manutenzione', tool CLI, ecc.). Returns il numero di sessioni rimosse.
    """
    log = logging.getLogger(__name__)
    trash = _get_trash_root()
    if not trash.exists():
        return 0

    cutoff = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
    removed = 0
    for session_dir in trash.iterdir():
        if not session_dir.is_dir():
            continue
        try:
            # Il nome della sessione è "YYYYMMDD_HHMMSS"
            ts = datetime.datetime.strptime(session_dir.name, "%Y%m%d_%H%M%S")
        except ValueError:
            # Cartella estranea — skip
            continue
        if ts < cutoff:
            try:
                shutil.rmtree(session_dir)
                _audit_log("TRASH_PURGE", str(session_dir),
                           f"age_days>{max_age_days}")
                removed += 1
            except Exception as e:
                log.warning(f"cleanup_trash: impossibile rimuovere {session_dir}: {e}")
    if removed:
        log.info(f"cleanup_trash: rimosse {removed} sessioni > {max_age_days} giorni")
    return removed


# ---------------------------------------------------------------------------
# Graphic Utilities (Perspective Warp)
# ---------------------------------------------------------------------------

# Costante: dimensione minima del side del dest per attivare il warp
_WARP_MIN_SIZE: int = 4

# Detection di numpy/scipy una volta sola a livello modulo.
# Su Android (p4a) scipy non è cross-compilato, quindi `warp_surface` fa
# fallback (ritorna la surface originale senza warp prospettico) invece di
# crashare. Su desktop l'import normale ha successo.
# Senza questa cache, `warp_surface` faceva try/except ad ogni chiamata —
# overhead nullo su desktop, ma su Android (dove il caso "manca" si verifica
# ogni frame durante il rendering scene) era un costo evitabile.
try:
    import numpy as _np_module  # noqa: F401
    from scipy.ndimage import map_coordinates as _scipy_map_coordinates  # noqa: F401
    _HAS_WARP_DEPS = True
except ImportError:
    _np_module = None  # type: ignore
    _scipy_map_coordinates = None  # type: ignore
    _HAS_WARP_DEPS = False


def warp_surface(surface: pygame.Surface, target_quad: list[tuple[float, float]]) -> pygame.Surface:
    """
    Perspective warp senza artefatti usando inverse bilinear mapping vettorizzato.

    Algoritmo:
      1. Converte la surface sorgente in array numpy con pre-moltiplicazione alpha.
      2. Per ogni pixel del dest calcola la coordinata UV nella source risolvendo
         il sistema bilineare inverso con Newton (4 iterazioni).
      3. Pixel del bounding-box fuori dal quad → alpha=0 (trasparente).
      4. scipy.ndimage.map_coordinates campiona con interpolazione bilineare (order=1).
      5. De-pre-moltiplica alpha e ricostruisce la pygame.Surface.

    Fix rispetto alla versione precedente:
      - Pre-moltiplicazione alpha prima dell'interpolazione: evita color-fringing
        (aloni scuri) ai bordi dei PNG trasparenti.
      - Newton senza clamp aggressivo a [0,1]: permette di identificare i pixel
        fuori dal quad e azzera il loro alpha invece di campionare il bordo sorgente.
    """
    # Fast-path Android (o ambiente senza scipy): nessun warp possibile.
    # Decisione fatta una volta sola a livello modulo (vedi _HAS_WARP_DEPS).
    if not _HAS_WARP_DEPS:
        return surface

    # Alias locali per leggibilità (codice originale usa np / map_coordinates).
    np = _np_module
    map_coordinates = _scipy_map_coordinates

    try:
        src_w, src_h = surface.get_size()
        if src_w < _WARP_MIN_SIZE or src_h < _WARP_MIN_SIZE:
            return surface

        # ── 1. Quad target (coordinate float nel sistema dest) ──────────────
        # Ordine: NW, NE, SE, SW  →  indici 0,1,2,3
        nw, ne, se, sw = [np.array(p, dtype=np.float64) for p in target_quad]

        xs = np.array([nw[0], ne[0], se[0], sw[0]])
        ys = np.array([nw[1], ne[1], se[1], sw[1]])
        min_x, max_x = xs.min(), xs.max()
        min_y, max_y = ys.min(), ys.max()

        dest_w = int(np.ceil(max_x - min_x)) + 1
        dest_h = int(np.ceil(max_y - min_y)) + 1
        if dest_w < _WARP_MIN_SIZE or dest_h < _WARP_MIN_SIZE:
            return surface

        # Trasla il quad in coordinate locali del dest (origin = top-left del bounding box)
        offset = np.array([min_x, min_y], dtype=np.float64)
        p0 = nw - offset   # NW
        p1 = ne - offset   # NE
        p2 = se - offset   # SE
        p3 = sw - offset   # SW

        # ── 2. Griglia di coordinate pixel del dest ─────────────────────────
        dx = np.arange(dest_w, dtype=np.float64)
        dy = np.arange(dest_h, dtype=np.float64)
        gx, gy = np.meshgrid(dx, dy)           # shape (dest_h, dest_w)

        # ── 3. Inverse bilinear mapping: (gx, gy) → (u, v) ─────────────────
        #
        # Forward bilinear:
        #   P(u,v) = (1-u)(1-v)·p0 + u(1-v)·p1 + u·v·p2 + (1-u)v·p3
        #
        # Sistema non-lineare in (u,v); soluzione con 4 iterazioni Newton.
        # ────────────────────────────────────────────────────────────────────
        def _bilinear(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            w00 = (1.0 - u) * (1.0 - v)
            w10 = u          * (1.0 - v)
            w11 = u          * v
            w01 = (1.0 - u) * v
            px = w00 * p0[0] + w10 * p1[0] + w11 * p2[0] + w01 * p3[0]
            py = w00 * p0[1] + w10 * p1[1] + w11 * p2[1] + w01 * p3[1]
            return px, py

        def _jacobian(u: np.ndarray, v: np.ndarray
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            dpu_x = (1.0 - v) * (p1[0] - p0[0]) + v * (p2[0] - p3[0])
            dpu_y = (1.0 - v) * (p1[1] - p0[1]) + v * (p2[1] - p3[1])
            dpv_x = (1.0 - u) * (p3[0] - p0[0]) + u * (p2[0] - p1[0])
            dpv_y = (1.0 - u) * (p3[1] - p0[1]) + u * (p2[1] - p1[1])
            return dpu_x, dpu_y, dpv_x, dpv_y

        # Guess iniziale: proiezione lineare sul quad
        u = gx / max(dest_w - 1, 1)
        v = gy / max(dest_h - 1, 1)

        # Newton: clamp a [-0.5, 1.5] per stabilità numerica ma abbastanza ampio
        # da conservare l'informazione su quali pixel sono fuori dal quad.
        for _ in range(4):
            fx, fy = _bilinear(u, v)
            rx, ry = gx - fx, gy - fy
            dpu_x, dpu_y, dpv_x, dpv_y = _jacobian(u, v)
            det = dpu_x * dpv_y - dpu_y * dpv_x
            safe_det = np.where(np.abs(det) < 1e-12, 1e-12, det)
            du =  (dpv_y * rx - dpv_x * ry) / safe_det
            dv = -(dpu_y * rx - dpu_x * ry) / safe_det
            u = np.clip(u + du, -0.5, 1.5)
            v = np.clip(v + dv, -0.5, 1.5)

        # Pixel del bounding-box che cadono fuori dal quad → saranno trasparenti
        outside_mask = (u < -1e-3) | (u > 1.0 + 1e-3) | (v < -1e-3) | (v > 1.0 + 1e-3)

        # Clamp a [0,1] per il campionamento (i pixel outside hanno già la loro maschera)
        u_s = np.clip(u, 0.0, 1.0)
        v_s = np.clip(v, 0.0, 1.0)

        # Converte (u, v) in coordinate pixel della source
        src_coords_x = u_s * (src_w - 1)   # shape (dest_h, dest_w)
        src_coords_y = v_s * (src_h - 1)

        # ── 4. Campionamento con pre-moltiplicazione alpha ───────────────────
        #
        # Problema senza pre-molt.: i pixel trasparenti (alpha=0) hanno RGB
        # arbitrari (spesso nero). L'interpolazione bilineare li mescola con i
        # pixel opachi adiacenti → aloni scuri ai bordi ("color fringing").
        #
        # Soluzione: R' = R * A/255 prima dell'interpolazione, poi de-pre-molt.
        # dopo. I pixel trasparenti contribuiscono 0 all'RGB → nessun fringing.
        # ────────────────────────────────────────────────────────────────────
        src_arr   = pygame.surfarray.array3d(surface).astype(np.float64)  # (src_w, src_h, 3)
        src_alpha = pygame.surfarray.array_alpha(surface).astype(np.float64)  # (src_w, src_h)

        # Pre-moltiplica ogni canale RGB per alpha/255
        alpha_norm = src_alpha / 255.0
        src_arr[:, :, 0] *= alpha_norm
        src_arr[:, :, 1] *= alpha_norm
        src_arr[:, :, 2] *= alpha_norm

        coords = np.array([src_coords_x, src_coords_y])  # (2, dest_h, dest_w)

        r_ch = map_coordinates(src_arr[:, :, 0], coords, order=1, mode="nearest")
        g_ch = map_coordinates(src_arr[:, :, 1], coords, order=1, mode="nearest")
        b_ch = map_coordinates(src_arr[:, :, 2], coords, order=1, mode="nearest")
        a_ch = map_coordinates(src_alpha,         coords, order=1, mode="nearest")

        # De-pre-moltiplica: R = premult_R / (A/255) dove A > 0
        # Evita la divisione per zero usando 1.0 come denominatore sicuro
        safe_a = np.where(a_ch > 0.5, a_ch, 1.0)
        r_ch = np.where(a_ch > 0.5, r_ch * 255.0 / safe_a, 0.0)
        g_ch = np.where(a_ch > 0.5, g_ch * 255.0 / safe_a, 0.0)
        b_ch = np.where(a_ch > 0.5, b_ch * 255.0 / safe_a, 0.0)

        # I pixel fuori dal quad diventano completamente trasparenti
        a_ch[outside_mask] = 0.0

        # ── 5. Costruisce la pygame.Surface risultante ───────────────────────
        dest_rgb = np.stack([r_ch, g_ch, b_ch], axis=-1).clip(0, 255).astype(np.uint8)
        dest_a   = a_ch.clip(0, 255).astype(np.uint8)

        # dest_rgb.shape = (dest_h, dest_w, 3); per pygame serve (dest_w, dest_h, 3)
        dest_rgb_t = np.transpose(dest_rgb, (1, 0, 2))
        dest_a_t   = np.transpose(dest_a,   (1, 0))

        result = pygame.Surface((dest_w, dest_h), pygame.SRCALPHA)
        pygame.surfarray.blit_array(result, dest_rgb_t)
        pygame.surfarray.pixels_alpha(result)[:] = dest_a_t

        return result

    except Exception:
        logging.exception("warp_surface: fallback alla surface originale")
        return surface


def apply_grayscale(surface: pygame.Surface, factor: float = 1.0) -> pygame.Surface:
    """
    Applica un filtro bianco e nero preservando Alpha e Colorkey in modo robusto.
    """
    if factor <= 0.001: return surface.copy()
    # numpy è sempre presente (in requirements buildozer.spec e in desktop)
    # ma usiamo l'alias module-level già importato per evitare overhead di
    # import re-binding ad ogni chiamata (chiamata in hot path di rendering).
    np = _np_module
    if np is None:
        # Edge case: ambiente strano senza numpy. Ritorna copia senza filtro.
        return surface.copy()
    factor = max(0.0, min(1.0, factor))
    
    # 1. Prepariamo la superficie di destinazione come copia dell'originale
    # Questo preserva formati, alpha-flags e colorkey.
    dest_surf = surface.copy()
    
    # 2. Gestione Alpha
    # Salviamo l'array alpha PRIMA di blit_array (che può azzerarlo su superfici 32bit)
    alpha_arr = None
    if dest_surf.get_masks()[3] != 0: 
        try:
            alpha_arr = pygame.surfarray.array_alpha(dest_surf).copy()
        except:
            pass
            
    # 3. Trasformazione RGB via NumPy
    # array3d restituisce (width, height, 3)
    rgb = pygame.surfarray.array3d(dest_surf).astype(np.float64)
    
    # Luminanza: 0.299R + 0.587G + 0.114B
    luma = rgb[:,:,0] * 0.299 + rgb[:,:,1] * 0.587 + rgb[:,:,2] * 0.114
    
    # Interpolazione
    for i in range(3):
        rgb[:,:,i] = rgb[:,:,i] * (1.0 - factor) + luma * factor
        
    # 4. Riallocazione pixel
    # blit_array su 32bit imposta alpha=255 se l'array è 3D.
    pygame.surfarray.blit_array(dest_surf, rgb.clip(0, 255).astype(np.uint8))
    
    # 5. Ripristino Alpha
    if alpha_arr is not None:
        pygame.surfarray.pixels_alpha(dest_surf)[:] = alpha_arr
    
    return dest_surf



