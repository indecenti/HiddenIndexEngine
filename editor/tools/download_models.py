"""
editor/tools/download_models.py

Downloader dei modelli IA dello scatter, on-demand al primo uso.
Scarica da HuggingFace nella cartella .editor_cache/models/.

API:
    download_model(tier, base_path, progress_cb=None) -> Path | None
        Scarica il modello del tier richiesto. progress_cb(downloaded, total) opzionale.
        Ritorna il Path al file scaricato, o None se fallisce.
        Skip se file gia' presente.

    download_url(url, dest, progress_cb=None) -> bool
        Util generica.

Nessuna dipendenza esterna: usa urllib.request della stdlib.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from editor.tools.scatter_models import (
    MODEL_DEPTH_ANYTHING_SMALL, MODEL_METRIC3D_LARGE,
    MODEL_SEGFORMER_ADE, MODEL_CLIP_VISUAL, MODEL_CLIP_TEXT,
    models_dir, model_path_for, segformer_path, clip_path, clip_text_path,
)

log = logging.getLogger(__name__)

# URL HuggingFace pattern: https://huggingface.co/<repo>/resolve/main/<file>
HF_BASE = "https://huggingface.co"

# Override per mirror locale / azienda (env var)
ENV_MIRROR = "SCATTER_MODELS_MIRROR"


def hf_url(repo: str, file: str) -> str:
    mirror = os.environ.get(ENV_MIRROR, HF_BASE).rstrip("/")
    return f"{mirror}/{repo}/resolve/main/{file}"


def download_url(url: str, dest: Path,
                 progress_cb: Optional[Callable[[int, int], None]] = None,
                 timeout: int = 60) -> bool:
    """Scarica `url` in `dest` con progress callback. Atomic via tmp+rename.

    progress_cb(downloaded_bytes, total_bytes) chiamato ogni ~64KB.
    Ritorna True se successo, False altrimenti.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    log.info(f"[DOWNLOAD] {url} -> {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HiddenEditor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 64 * 1024  # 64 KB
            with open(tmp, "wb") as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    if progress_cb:
                        try:
                            progress_cb(downloaded, total)
                        except Exception:
                            pass
        # Validazione: un download troncato (server/proxy che chiude lo stream senza
        # errore) non deve essere promosso a file finale, altrimenti resta cachato
        # come "completo" per sempre. Scarta il .part e fallisci cosi' si riprova.
        if total > 0 and downloaded != total:
            log.error(f"[DOWNLOAD] troncato {url}: {downloaded}/{total} bytes")
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return False
        # Atomic rename
        os.replace(tmp, dest)
        log.info(f"[DOWNLOAD] OK {dest} ({downloaded} bytes)")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        log.error(f"[DOWNLOAD] fallito {url}: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def model_meta(tier: int) -> dict:
    if tier == 1:
        return MODEL_DEPTH_ANYTHING_SMALL
    if tier == 2:
        return MODEL_METRIC3D_LARGE
    raise ValueError(f"tier {tier} non supportato per download")


def download_model(tier: int, base_path: Path,
                   progress_cb: Optional[Callable[[int, int], None]] = None,
                   force: bool = False) -> Optional[Path]:
    """Scarica il modello del tier richiesto. Skip se gia' presente (a meno di force=True).

    Restituisce Path al file scaricato o None se fallisce.
    """
    meta = model_meta(tier)
    dest = model_path_for(tier, base_path)
    if dest.exists() and not force:
        log.info(f"[DOWNLOAD] tier{tier} gia' presente: {dest}")
        return dest
    url = hf_url(meta["hf_repo"], meta["hf_file"])
    ok = download_url(url, dest, progress_cb=progress_cb, timeout=180)
    if ok:
        return dest
    return None


def download_segformer(base_path: Path,
                       progress_cb: Optional[Callable[[int, int], None]] = None,
                       force: bool = False) -> Optional[Path]:
    """Scarica SegFormer-B0 ADE20K (~15MB) per il tier ULTRA."""
    dest = segformer_path(base_path)
    if dest.exists() and not force:
        log.info(f"[DOWNLOAD] segformer gia' presente: {dest}")
        return dest
    url = hf_url(MODEL_SEGFORMER_ADE["hf_repo"], MODEL_SEGFORMER_ADE["hf_file"])
    ok = download_url(url, dest, progress_cb=progress_cb, timeout=180)
    return dest if ok else None


def download_clip_visual(base_path: Path,
                         progress_cb: Optional[Callable[[int, int], None]] = None,
                         force: bool = False) -> Optional[Path]:
    """Scarica CLIP ViT-B/32 visual FP16 (~176MB) per il tier ULTRA."""
    dest = clip_path(base_path)
    if dest.exists() and not force:
        log.info(f"[DOWNLOAD] CLIP gia' presente: {dest}")
        return dest
    url = hf_url(MODEL_CLIP_VISUAL["hf_repo"], MODEL_CLIP_VISUAL["hf_file"])
    ok = download_url(url, dest, progress_cb=progress_cb, timeout=300)
    return dest if ok else None


def download_ultra(base_path: Path,
                   progress_cb: Optional[Callable[[str, int, int], None]] = None,
                   force: bool = False) -> bool:
    """Scarica TUTTI i modelli necessari al tier ULTRA. progress_cb(name, done, total).

    Returns True se tutti i modelli sono presenti alla fine.
    """
    def cb_for(name):
        return (lambda d, t: progress_cb(name, d, t)) if progress_cb else None
    # Metric3D (se manca)
    if not model_path_for(2, base_path).exists():
        if not download_model(2, base_path, progress_cb=cb_for("Metric3D"), force=force):
            return False
    # SegFormer
    if not segformer_path(base_path).exists():
        if not download_segformer(base_path, progress_cb=cb_for("SegFormer"), force=force):
            return False
    # CLIP
    if not clip_path(base_path).exists():
        if not download_clip_visual(base_path, progress_cb=cb_for("CLIP"), force=force):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI per testing manuale: python -m editor.tools.download_models 1
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("uso: python -m editor.tools.download_models <tier_1_or_2> [base_path]")
        sys.exit(1)
    t = int(sys.argv[1])
    bp = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

    def cb(d, tot):
        if tot > 0:
            pct = d / tot * 100
            print(f"\r  {d/1024/1024:6.1f}/{tot/1024/1024:6.1f} MB ({pct:5.1f}%)", end="", flush=True)

    p = download_model(t, bp, progress_cb=cb)
    print()
    if p:
        print(f"OK: {p} ({p.stat().st_size/1024/1024:.1f} MB)")
    else:
        print("FAIL")
        sys.exit(1)
