"""
editor/tools/scatter_models.py

Modelli per scatter intelligente, tier-based.

  TIER 0 - Classic    : nessuna IA, solo algoritmo Sobel/Canny/Saliency
  TIER 1 - Light GPU  : Depth Anything V2 Small (24MB ONNX)
                        Output: depth_map. Normals derivate via gradient.
  TIER 2 - Pro GPU    : Metric3D v2 ViT-Large (170MB ONNX FP16)
                        Output: depth_map + normal_map nativi.

Tutti i tier hanno interfaccia comune:
    model.analyze(rgb_array) -> dict {
        "depth":   np.ndarray (H,W) float32 0..1   (None per tier 0)
        "normals": np.ndarray (H,W,3) float32 -1..1 (None per tier 0)
        "tier":    int (0/1/2)
        "ms":      float  inference time
    }

Auto-detect:
    get_best_model() prova in ordine: TIER 2 (CUDA) -> TIER 1 (CUDA/DirectML/CPU) -> TIER 0
    Override manuale via env var SCATTER_TIER=0|1|2 o parametro force_tier=N.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

MODELS_DIR_NAME = ".editor_cache/models"

# Metadati dei modelli (filename, hf_repo, hf_file, input_size, size_mb)
MODEL_DEPTH_ANYTHING_SMALL = {
    "filename": "depth_anything_v2_small_fp16.onnx",
    "hf_repo": "onnx-community/depth-anything-v2-small",
    "hf_file": "onnx/model_fp16.onnx",
    "input_size": 518,
    "size_mb_approx": 50,
    "display_name": "Depth Anything V2 Small (FP16)",
}
# Pro: Metric3D v2 ViT-Small FP16 (depth + normals nativi in un solo forward)
# Bundle leggero ma qualita' superiore al Depth Anything per "trovare appoggi"
# Per GPU top-tier (>= 4070) esiste anche vit-large FP16 (825MB) ma serve >12GB VRAM
MODEL_METRIC3D_LARGE = {
    "filename": "metric3d_vit_small_fp16.onnx",
    "hf_repo": "onnx-community/metric3d-vit-small",
    "hf_file": "onnx/model_fp16.onnx",
    "input_size": 616,
    "size_mb_approx": 76,
    "display_name": "Metric3D v2 ViT-Small (FP16)",
}
# Tier ULTRA: SegFormer per semantic seg (150 classi ADE20K) — solo 15MB
MODEL_SEGFORMER_ADE = {
    "filename": "segformer_b0_ade20k.onnx",
    "hf_repo": "optimum/segformer-b0-finetuned-ade-512-512",
    "hf_file": "model.onnx",
    "input_size": 512,
    "size_mb_approx": 15,
    "display_name": "SegFormer-B0 ADE20K",
}
# Tier ULTRA: CLIP ViT-B/32 visual FP16 per object-zone matching
MODEL_CLIP_VISUAL = {
    "filename": "clip_vit_b32_openai_visual_fp16.onnx",
    "hf_repo": "Marqo/onnx-open_clip-ViT-B-32",
    "hf_file": "onnx16-open_clip-ViT-B-32-openai-visual.onnx",
    "input_size": 224,
    "size_mb_approx": 176,
    "display_name": "CLIP ViT-B/32 Visual (FP16, OpenAI weights)",
}
# CLIP Text encoder per object profiling zero-shot (context affinity)
# Uso Xenova/clip-vit-base-patch32 (standard HF model export)
MODEL_CLIP_TEXT = {
    "filename": "clip_vit_b32_text_xenova_fp16.onnx",
    "hf_repo": "Xenova/clip-vit-base-patch32",
    "hf_file": "onnx/text_model_fp16.onnx",
    "input_size": 77,
    "size_mb_approx": 127,
    "display_name": "CLIP ViT-B/32 Text (FP16, Xenova export)",
}

# Soglie quick-benchmark per declassare (ms). Se inference > soglia, retrocedi al tier sotto.
# NB: tier2 (Metric3D 616px + normals) e' piu' pesante di tier1 (Depth Anything 518px),
# quindi deve avere un budget MAGGIORE, non minore: altrimenti il modello migliore
# veniva declassato proprio sulle macchine dove tier1 passava.
_BENCH_TIER1_MAX_MS = 1500
_BENCH_TIER2_MAX_MS = 2500


# ─────────────────────────────────────────────────────────────────────────────
# Optional onnxruntime import
# ─────────────────────────────────────────────────────────────────────────────
try:
    import onnxruntime as ort  # type: ignore
    _HAS_ORT = True
    _ORT_PROVIDERS = ort.get_available_providers()
    log.info(f"[SCATTER_MODELS] onnxruntime providers: {_ORT_PROVIDERS}")
except Exception as e:
    _HAS_ORT = False
    _ORT_PROVIDERS = []
    log.info(f"[SCATTER_MODELS] onnxruntime non disponibile ({e}), tier 0 only")

try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False


def has_cuda() -> bool:
    return _HAS_ORT and "CUDAExecutionProvider" in _ORT_PROVIDERS

def has_directml() -> bool:
    return _HAS_ORT and "DmlExecutionProvider" in _ORT_PROVIDERS

def has_any_gpu_provider() -> bool:
    return has_cuda() or has_directml()


def _silence_ort_stderr():
    """Context manager per silenziare lo stderr nativo (C++) di onnxruntime durante init.

    Necessario per i modelli FP16 che falliscono il primo tentativo (rumore visivo).
    """
    import os, sys, contextlib
    @contextlib.contextmanager
    def _redirect():
        try:
            old_stderr_fd = os.dup(2)
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull_fd, 2)
            os.close(devnull_fd)
            yield
        finally:
            try:
                os.dup2(old_stderr_fd, 2)
                os.close(old_stderr_fd)
            except Exception:
                pass
    return _redirect()


def _best_providers(prefer_cuda: bool = True) -> list:
    """Lista provider ordinati per preferenza (CUDA > DirectML > CPU)."""
    out = []
    if prefer_cuda and has_cuda():
        out.append("CUDAExecutionProvider")
    if has_directml():
        out.append("DmlExecutionProvider")
    out.append("CPUExecutionProvider")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BASE
# ─────────────────────────────────────────────────────────────────────────────

class ScatterModelBase:
    """Interfaccia comune. Le sottoclassi devono implementare analyze()."""

    tier: int = 0
    name: str = "base"

    def is_loaded(self) -> bool:
        return True

    def analyze(self, rgb: np.ndarray) -> dict:
        """Restituisce dict con depth/normals/tier/ms."""
        raise NotImplementedError


class ClassicTier0(ScatterModelBase):
    """Tier 0: nessun modello IA. analyze() restituisce None per depth/normals."""
    tier = 0
    name = "classic"

    def analyze(self, rgb: np.ndarray) -> dict:
        return {"depth": None, "normals": None, "tier": 0, "ms": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1: Depth Anything V2 Small
# ─────────────────────────────────────────────────────────────────────────────

class DepthAnythingSmall(ScatterModelBase):
    """Wrapper di Depth Anything V2 Small via onnxruntime."""

    tier = 1
    name = "depth-anything-v2-small"

    def __init__(self, model_path: Path, providers: Optional[list] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        if not model_path.exists():
            raise FileNotFoundError(f"Modello mancante: {model_path}")
        self.model_path = model_path
        self.input_size = MODEL_DEPTH_ANYTHING_SMALL["input_size"]
        providers = providers or _best_providers(prefer_cuda=False)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        # FP16 + SimplifiedLayerNormFusion = bug noto in onnxruntime.
        # Disabilito quella ottimizzazione specifica; il resto resta abilitato.
        try:
            opts.add_session_config_entry("session.disable_layer_norm_fusion", "1")
        except Exception:
            pass
        # FP16 + SimplifiedLayerNormFusion = bug noto. Silenzio stderr e fallback BASIC.
        with _silence_ort_stderr():
            try:
                self.session = ort.InferenceSession(str(model_path), opts, providers=providers)
            except Exception as e_first:
                log.info(f"[SCATTER_MODELS] Tier1 ALL opt failed (FP16 fusion bug), uso BASIC")
                opts2 = ort.SessionOptions()
                opts2.log_severity_level = 3
                opts2.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                self.session = ort.InferenceSession(str(model_path), opts2, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        log.info(f"[SCATTER_MODELS] Tier1 caricato con provider: {self.session.get_providers()}")

    def is_loaded(self) -> bool:
        return self.session is not None

    def analyze(self, rgb: np.ndarray) -> dict:
        """Restituisce depth + normals derivate via gradient."""
        t0 = time.time()
        h, w, _ = rgb.shape
        size = self.input_size

        # Resize a input_size x input_size (Depth Anything richiede multiplo di 14)
        try:
            import cv2
            rgb_resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
        except Exception:
            from PIL import Image
            rgb_resized = np.array(Image.fromarray(rgb).resize((size, size), Image.BILINEAR))

        # Normalize ImageNet mean/std (richiesto dai modelli ViT)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        inp = rgb_resized.astype(np.float32) / 255.0
        inp = (inp - mean) / std
        inp = inp.transpose(2, 0, 1)[None]  # (1, 3, H, W)
        inp = np.ascontiguousarray(inp, dtype=np.float32)

        out = self.session.run(None, {self.input_name: inp})[0]
        # out shape: (1, H, W) o (1, 1, H, W)
        depth = out.squeeze()
        if depth.ndim != 2:
            depth = depth[0]

        # Resize back a (h, w)
        try:
            import cv2
            depth_full = cv2.resize(depth, (w, h), interpolation=cv2.INTER_LINEAR)
        except Exception:
            depth_full = np.kron(depth, np.ones((h // depth.shape[0] + 1, w // depth.shape[1] + 1)))[:h, :w]

        # Normalize 0..1
        d_min, d_max = float(depth_full.min()), float(depth_full.max())
        if d_max - d_min > 1e-6:
            depth_full = (depth_full - d_min) / (d_max - d_min)
        depth_full = depth_full.astype(np.float32)

        # Normals approssimate via gradient (cross product di gradX, gradY)
        normals = self._derive_normals_from_depth(depth_full)

        dt = (time.time() - t0) * 1000
        return {"depth": depth_full, "normals": normals, "tier": 1, "ms": dt}

    @staticmethod
    def _derive_normals_from_depth(depth: np.ndarray) -> np.ndarray:
        """Stima normals via cross-product di Sobel gradients (approssimata)."""
        try:
            import cv2
            gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=5)
            gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=5)
        except Exception:
            gx = np.gradient(depth, axis=1).astype(np.float32)
            gy = np.gradient(depth, axis=0).astype(np.float32)
        # Scala (depth e' relativo); fattore empirico per accentuare le pendenze
        gx *= 4.0
        gy *= 4.0
        # Normal in coord camera: (-gx, -gy, 1) normalizzato
        nz = np.ones_like(depth)
        norms = np.stack([-gx, -gy, nz], axis=-1)
        magnitude = np.linalg.norm(norms, axis=-1, keepdims=True) + 1e-8
        return (norms / magnitude).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2: Metric3D v2 ViT-Large (depth + normals nativi)
# ─────────────────────────────────────────────────────────────────────────────

class Metric3DLarge(ScatterModelBase):
    """Wrapper di Metric3D v2 ViT-Large via onnxruntime.

    Output del modello: depth metrico + normals + confidence in un solo pass.
    """

    tier = 2
    name = "metric3d-vit-large"

    def __init__(self, model_path: Path, providers: Optional[list] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        if not model_path.exists():
            raise FileNotFoundError(f"Modello mancante: {model_path}")
        self.model_path = model_path
        self.input_size = MODEL_METRIC3D_LARGE["input_size"]
        providers = providers or _best_providers(prefer_cuda=True)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        try:
            opts.add_session_config_entry("session.disable_layer_norm_fusion", "1")
        except Exception:
            pass
        with _silence_ort_stderr():
            try:
                self.session = ort.InferenceSession(str(model_path), opts, providers=providers)
            except Exception as e_first:
                log.info(f"[SCATTER_MODELS] Tier2 ALL opt failed (FP16 fusion bug), uso BASIC")
                opts2 = ort.SessionOptions()
                opts2.log_severity_level = 3
                opts2.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                self.session = ort.InferenceSession(str(model_path), opts2, providers=providers)
        # Metric3D ha potenzialmente 1 input ma scopro i nomi dinamicamente
        self.input_name = self.session.get_inputs()[0].name
        # Output names: cerco "depth", "normal", "confidence" tra gli output
        self.output_names = [o.name for o in self.session.get_outputs()]
        log.info(f"[SCATTER_MODELS] Tier2 caricato con provider: {self.session.get_providers()}")
        log.info(f"[SCATTER_MODELS] Tier2 outputs: {self.output_names}")

    def is_loaded(self) -> bool:
        return self.session is not None

    def analyze(self, rgb: np.ndarray) -> dict:
        t0 = time.time()
        h, w, _ = rgb.shape
        size = self.input_size

        try:
            import cv2
            rgb_resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
        except Exception:
            from PIL import Image
            rgb_resized = np.array(Image.fromarray(rgb).resize((size, size), Image.BILINEAR))

        # Metric3D usa normalization standard ImageNet + FP16 input se modello e' FP16
        mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
        inp = rgb_resized.astype(np.float32)
        inp = (inp - mean) / std
        inp = inp.transpose(2, 0, 1)[None]
        # FP16 se richiesto
        try:
            inp_dtype = self.session.get_inputs()[0].type
            if "float16" in inp_dtype:
                inp = inp.astype(np.float16)
            else:
                inp = inp.astype(np.float32)
        except Exception:
            inp = inp.astype(np.float32)
        inp = np.ascontiguousarray(inp)

        outs = self.session.run(None, {self.input_name: inp})

        # Trovo depth e normals tra gli outputs
        depth = None
        normals = None
        for name, arr in zip(self.output_names, outs):
            arr_np = np.array(arr)
            low_name = name.lower()
            if "depth" in low_name and depth is None:
                d = arr_np.squeeze()
                if d.ndim == 2:
                    depth = d
            elif "normal" in low_name and normals is None:
                n = arr_np.squeeze()
                # Aspetto shape (3, H, W) o (H, W, 3)
                if n.ndim == 3:
                    if n.shape[0] == 3:
                        n = n.transpose(1, 2, 0)
                    if n.shape[-1] == 3:
                        normals = n

        # Fallback: se non trovo per nome, assumo primo = depth, secondo = normals
        if depth is None and len(outs) >= 1:
            d = np.array(outs[0]).squeeze()
            if d.ndim == 2: depth = d
        if normals is None and len(outs) >= 2:
            n = np.array(outs[1]).squeeze()
            if n.ndim == 3:
                if n.shape[0] == 3:
                    n = n.transpose(1, 2, 0)
                if n.shape[-1] == 3:
                    normals = n

        # Resize back
        if depth is not None:
            try:
                import cv2
                depth = cv2.resize(depth.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
            except Exception:
                pass
            d_min, d_max = float(depth.min()), float(depth.max())
            if d_max - d_min > 1e-6:
                depth = (depth - d_min) / (d_max - d_min)
            depth = depth.astype(np.float32)

        if normals is not None:
            try:
                import cv2
                n_resized = np.zeros((h, w, 3), dtype=np.float32)
                for c in range(3):
                    n_resized[..., c] = cv2.resize(normals[..., c].astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
                normals = n_resized
            except Exception:
                pass
            # Normalizza
            mag = np.linalg.norm(normals, axis=-1, keepdims=True) + 1e-8
            normals = (normals / mag).astype(np.float32)

        dt = (time.time() - t0) * 1000
        return {"depth": depth, "normals": normals, "tier": 2, "ms": dt}


# ─────────────────────────────────────────────────────────────────────────────
# TIER ULTRA: SegFormer (semantic seg) + CLIP visual (similarity)
# ─────────────────────────────────────────────────────────────────────────────

# ADE20K classes (150). Source: nvidia/segformer config.
# Solo subset chiave per scoring; il resto e' "neutro".
ADE20K_FLOOR_LIKE  = {3, 6, 11, 13, 28, 53}    # floor, road, sidewalk, earth, rug, stairs-equivalent
ADE20K_TABLE_LIKE  = {15, 23, 25, 33, 64}      # table, sofa, shelf, desk, coffee_table
ADE20K_WALL_LIKE   = {0, 1, 8, 9}              # wall, building, window, door
ADE20K_SKY_LIKE    = {2, 4, 16, 21, 26, 60, 109, 113}  # sky, tree, mountain, water, sea, lake, fountain, wave
ADE20K_PROHIBITED  = ADE20K_SKY_LIKE | ADE20K_WALL_LIKE  # zone dove NON mettere oggetti
ADE20K_PREFERRED   = ADE20K_FLOOR_LIKE | ADE20K_TABLE_LIKE


class SegFormerADE(ScatterModelBase):
    """SegFormer-B0 fine-tuned su ADE20K: 150 classi semantiche per ogni pixel."""

    name = "segformer-ade20k"

    def __init__(self, model_path: Path, providers: Optional[list] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        if not model_path.exists():
            raise FileNotFoundError(f"Modello mancante: {model_path}")
        self.model_path = model_path
        self.input_size = MODEL_SEGFORMER_ADE["input_size"]
        providers = providers or _best_providers(prefer_cuda=False)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        with _silence_ort_stderr():
            try:
                self.session = ort.InferenceSession(str(model_path), opts, providers=providers)
            except Exception:
                opts2 = ort.SessionOptions()
                opts2.log_severity_level = 3
                opts2.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                self.session = ort.InferenceSession(str(model_path), opts2, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        log.info(f"[SCATTER_MODELS] SegFormer caricato con provider: {self.session.get_providers()}")

    def predict_classes(self, rgb: np.ndarray) -> np.ndarray:
        """Restituisce mappa (H, W) di int — id della classe ADE20K per pixel."""
        t0 = time.time()
        h, w, _ = rgb.shape
        size = self.input_size
        if _HAS_CV2:
            rgb_resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
        else:
            from PIL import Image
            rgb_resized = np.array(Image.fromarray(rgb).resize((size, size), Image.BILINEAR))

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        inp = rgb_resized.astype(np.float32) / 255.0
        inp = (inp - mean) / std
        inp = inp.transpose(2, 0, 1)[None].astype(np.float32)
        inp = np.ascontiguousarray(inp)
        logits = self.session.run(None, {self.input_name: inp})[0]
        # logits shape: (1, 150, h_out, w_out) tipicamente h_out=w_out=128
        classes_small = logits.argmax(axis=1).squeeze().astype(np.int32)
        # Resize back via nearest a (h, w)
        if _HAS_CV2:
            classes = cv2.resize(classes_small.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
            classes = classes.astype(np.int32)
        else:
            # Fallback semplice
            yh = np.linspace(0, classes_small.shape[0] - 1, h).astype(np.int32)
            xw = np.linspace(0, classes_small.shape[1] - 1, w).astype(np.int32)
            classes = classes_small[yh[:, None], xw[None, :]]
        log.info(f"[SCATTER_MODELS] SegFormer inference {(time.time()-t0)*1000:.0f}ms")
        return classes


class ClipVisual(ScatterModelBase):
    """CLIP ViT-B/32 encoder visivo: produce embedding 512-D L2-normalized per immagine."""

    name = "clip-vit-b32-visual"
    EMBED_DIM = 512

    def __init__(self, model_path: Path, providers: Optional[list] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        if not model_path.exists():
            raise FileNotFoundError(f"Modello mancante: {model_path}")
        self.model_path = model_path
        self.input_size = MODEL_CLIP_VISUAL["input_size"]  # 224
        providers = providers or _best_providers(prefer_cuda=False)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        with _silence_ort_stderr():
            try:
                self.session = ort.InferenceSession(str(model_path), opts, providers=providers)
            except Exception:
                opts2 = ort.SessionOptions()
                opts2.log_severity_level = 3
                opts2.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                self.session = ort.InferenceSession(str(model_path), opts2, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_dtype = self.session.get_inputs()[0].type
        log.info(f"[SCATTER_MODELS] CLIP caricato con provider: {self.session.get_providers()}")

    def encode_image(self, rgb: np.ndarray) -> np.ndarray:
        """Encoda una singola immagine RGB (H, W, 3) → embedding (512,) L2-normalized."""
        size = self.input_size
        if _HAS_CV2:
            img = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
        else:
            from PIL import Image
            img = np.array(Image.fromarray(rgb).resize((size, size), Image.BILINEAR))
        # CLIP normalization
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        x = img.astype(np.float32) / 255.0
        x = (x - mean) / std
        x = x.transpose(2, 0, 1)[None]
        if "float16" in self.input_dtype:
            x = x.astype(np.float16)
        else:
            x = x.astype(np.float32)
        x = np.ascontiguousarray(x)
        feat = self.session.run(None, {self.input_name: x})[0]
        feat = feat.astype(np.float32).reshape(-1)
        # L2 normalize
        n = np.linalg.norm(feat) + 1e-8
        return feat / n

    def encode_batch(self, rgbs: list[np.ndarray]) -> np.ndarray:
        """Batch encoding di una lista di immagini. Ritorna (N, 512)."""
        out = np.zeros((len(rgbs), self.EMBED_DIM), dtype=np.float32)
        for i, rgb in enumerate(rgbs):
            out[i] = self.encode_image(rgb)
        return out


class ClipText(ScatterModelBase):
    """CLIP ViT-B/32 text encoder: produce embedding 512-D L2-normalized da testo.

    Tokenizer: usa il SimpleTokenizer di OpenAI CLIP (BPE). Per evitare dipendenze
    extra, includiamo qui una tokenizzazione minimale compatibile. Limita max 77 tok.
    """

    name = "clip-vit-b32-text"
    EMBED_DIM = 512
    CONTEXT_LENGTH = 77

    # Token speciali CLIP standard
    SOT_TOKEN = 49406  # <start_of_text>
    EOT_TOKEN = 49407  # <end_of_text>

    def __init__(self, model_path: Path, providers: Optional[list] = None,
                 vocab_path: Optional[Path] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        if not model_path.exists():
            raise FileNotFoundError(f"Modello mancante: {model_path}")
        self.model_path = model_path
        providers = providers or _best_providers(prefer_cuda=False)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        with _silence_ort_stderr():
            try:
                self.session = ort.InferenceSession(str(model_path), opts, providers=providers)
            except Exception:
                opts2 = ort.SessionOptions()
                opts2.log_severity_level = 3
                opts2.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                self.session = ort.InferenceSession(str(model_path), opts2, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_dtype = self.session.get_inputs()[0].type
        # Lazy load tokenizer
        self._tokenizer = None
        self._vocab_path = vocab_path or (model_path.parent / "clip_bpe_vocab.json")
        log.info(f"[SCATTER_MODELS] CLIP Text caricato con provider: {self.session.get_providers()}")

    def _get_tokenizer(self):
        """Inizializza tokenizer CLIP BPE on-demand. Preferenza:
        1. transformers CLIPTokenizer (gia' installato di solito)
        2. open_clip
        3. openai clip
        4. fallback minimo (mai semantico, ultimo resort)
        """
        if self._tokenizer is not None:
            return self._tokenizer
        # transformers (preferito, no torch dep aggiuntivo)
        try:
            from transformers import CLIPTokenizer
            tk = CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch32")
            self._tokenizer = ("transformers", tk)
            log.info("[SCATTER_MODELS] CLIP tokenizer: transformers CLIPTokenizer")
            return self._tokenizer
        except Exception as e:
            log.debug(f"transformers CLIP tokenizer non disp ({e})")
        try:
            import open_clip
            tk = open_clip.get_tokenizer("ViT-B-32")
            self._tokenizer = ("open_clip", tk)
            log.info("[SCATTER_MODELS] CLIP tokenizer: open_clip")
            return self._tokenizer
        except Exception:
            pass
        try:
            import clip as openai_clip
            self._tokenizer = ("openai_func", openai_clip.tokenize)
            log.info("[SCATTER_MODELS] CLIP tokenizer: openai clip.tokenize")
            return self._tokenizer
        except Exception:
            pass
        log.warning("[SCATTER_MODELS] CLIP tokenizer non disponibile; uso fallback minimo")
        self._tokenizer = ("fallback", None)
        return self._tokenizer

    def tokenize(self, texts: list[str]) -> np.ndarray:
        """Tokenizza lista di stringhe in matrice (N, 77) int64."""
        tk_kind, tk = self._get_tokenizer()
        if tk_kind == "transformers":
            # transformers CLIPTokenizer: usa padding/max_length
            enc = tk(texts, padding="max_length", max_length=self.CONTEXT_LENGTH,
                     truncation=True, return_tensors="np")
            return enc["input_ids"].astype(np.int64)
        if tk_kind == "open_clip":
            tokens = tk(texts)
            return tokens.numpy().astype(np.int64) if hasattr(tokens, 'numpy') else np.array(tokens, dtype=np.int64)
        if tk_kind == "openai_func":
            tokens = tk(texts, context_length=self.CONTEXT_LENGTH, truncate=True)
            return tokens.numpy().astype(np.int64) if hasattr(tokens, 'numpy') else np.array(tokens, dtype=np.int64)
        # fallback
        out = np.zeros((len(texts), self.CONTEXT_LENGTH), dtype=np.int64)
        for i, t in enumerate(texts):
            out[i, 0] = self.SOT_TOKEN
            for j, ch in enumerate(t[:self.CONTEXT_LENGTH - 2]):
                out[i, j + 1] = (ord(ch) * 73 + 19) % 49000 + 100
            eot_pos = min(len(t) + 1, self.CONTEXT_LENGTH - 1)
            out[i, eot_pos] = self.EOT_TOKEN
        return out

    def encode_text(self, texts: list[str]) -> np.ndarray:
        """Encode lista di stringhe → matrice (N, 512) L2-normalized."""
        tokens = self.tokenize(texts)
        if "int32" in self.input_dtype:
            tokens = tokens.astype(np.int32)
        else:
            tokens = tokens.astype(np.int64)
        tokens = np.ascontiguousarray(tokens)
        feats = self.session.run(None, {self.input_name: tokens})[0]
        feats = feats.astype(np.float32)
        # L2 normalize
        norms = np.linalg.norm(feats, axis=-1, keepdims=True) + 1e-8
        return feats / norms


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY + AUTO-DETECT
# ─────────────────────────────────────────────────────────────────────────────

def models_dir(base_path: Path) -> Path:
    p = base_path / MODELS_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def model_path_for(tier: int, base_path: Path) -> Path:
    """Path per modello principale di un tier (depth/normals)."""
    if tier == 1:
        meta = MODEL_DEPTH_ANYTHING_SMALL
    elif tier == 2 or tier == 3:
        meta = MODEL_METRIC3D_LARGE  # tier 3 ULTRA usa Metric3D come base + segformer + clip
    else:
        meta = MODEL_DEPTH_ANYTHING_SMALL
    return models_dir(base_path) / meta["filename"]


def segformer_path(base_path: Path) -> Path:
    return models_dir(base_path) / MODEL_SEGFORMER_ADE["filename"]


def clip_path(base_path: Path) -> Path:
    return models_dir(base_path) / MODEL_CLIP_VISUAL["filename"]


def clip_text_path(base_path: Path) -> Path:
    return models_dir(base_path) / MODEL_CLIP_TEXT["filename"]


def is_model_available(tier: int, base_path: Path) -> bool:
    if tier == 0:
        return True
    if not _HAS_ORT:
        return False
    if tier == 3:
        # ULTRA richiede tutti e 3
        return (model_path_for(2, base_path).exists()
                and segformer_path(base_path).exists()
                and clip_path(base_path).exists())
    return model_path_for(tier, base_path).exists()


def get_status_summary(base_path: Path) -> dict:
    """Diagnostica per UI: cosa e' disponibile, cosa va scaricato."""
    return {
        "ort_installed": _HAS_ORT,
        "providers": list(_ORT_PROVIDERS) if _HAS_ORT else [],
        "has_cuda": has_cuda(),
        "has_directml": has_directml(),
        "tier0_ok": True,
        "tier1_model_present": is_model_available(1, base_path),
        "tier2_model_present": is_model_available(2, base_path),
        "tier3_model_present": is_model_available(3, base_path),
        "segformer_present":   segformer_path(base_path).exists(),
        "clip_present":        clip_path(base_path).exists(),
    }


class UltraEnsemble(ScatterModelBase):
    """Tier 3 ULTRA: composito Metric3D + SegFormer + CLIP visual.

    Espone analyze(rgb) compatibile con altri tier ma con campi extra:
      depth, normals  (da Metric3D)
      semantic        (np.ndarray (H,W) int — ADE20K class id)
      clip_grid       (np.ndarray (gy, gx, 512) — embedding CLIP per cella di 7x7 patch)
    """
    tier = 3
    name = "ultra-ensemble"

    def __init__(self, base_path: Path, providers: Optional[list] = None):
        if not _HAS_ORT:
            raise RuntimeError("onnxruntime non disponibile")
        self.base_path = base_path
        self.metric3d = Metric3DLarge(model_path_for(2, base_path), providers=providers)
        self.segformer = SegFormerADE(segformer_path(base_path), providers=providers)
        self.clip = ClipVisual(clip_path(base_path), providers=providers)
        log.info(f"[SCATTER_MODELS] UltraEnsemble pronto (3 modelli caricati)")

    def is_loaded(self) -> bool:
        return all(m is not None and m.is_loaded()
                   for m in (self.metric3d, self.segformer, self.clip))

    def analyze(self, rgb: np.ndarray) -> dict:
        t0 = time.time()
        # 1) Metric3D: depth + normals
        m3d = self.metric3d.analyze(rgb)
        # 2) SegFormer: semantic seg
        sem = self.segformer.predict_classes(rgb)
        # 3) CLIP grid v2.0: 6x10 patch (60 patch invece di 28). Piu' risoluzione
        #    spaziale per matching object-zone preciso.
        clip_grid = self._clip_grid(rgb, rows=6, cols=10)
        dt = (time.time() - t0) * 1000
        log.info(f"[SCATTER_MODELS] UltraEnsemble analyze done in {dt:.0f}ms")
        return {
            "depth": m3d.get("depth"),
            "normals": m3d.get("normals"),
            "semantic": sem,
            "clip_grid": clip_grid,
            "tier": 3,
            "ms": dt,
        }

    def _clip_grid(self, rgb: np.ndarray, rows: int = 6, cols: int = 10) -> np.ndarray:
        """Estrae embedding CLIP per patch di una griglia rows x cols del BG.

        v2.0: con overlap del 25% tra patch per coverage migliore e meno artefatti
        ai bordi delle celle.
        """
        h, w, _ = rgb.shape
        # Patch piu' grandi del passo (overlap) per smoothing spaziale
        step_h = h / rows
        step_w = w / cols
        patch_h = step_h * 1.25  # 25% overlap
        patch_w = step_w * 1.25
        out = np.zeros((rows, cols, ClipVisual.EMBED_DIM), dtype=np.float32)
        for ry in range(rows):
            for rx in range(cols):
                cy = (ry + 0.5) * step_h
                cx = (rx + 0.5) * step_w
                y0 = max(0, int(cy - patch_h / 2))
                y1 = min(h, int(cy + patch_h / 2))
                x0 = max(0, int(cx - patch_w / 2))
                x1 = min(w, int(cx + patch_w / 2))
                patch = rgb[y0:y1, x0:x1]
                out[ry, rx] = self.clip.encode_image(patch)
        return out


def get_best_model(base_path: Path, force_tier: Optional[int] = None,
                   quick_benchmark: bool = True) -> ScatterModelBase:
    """Factory: ritorna il miglior modello disponibile, con fallback graceful.

    Strategy:
      - force_tier override > env var > auto-detect
      - Auto: prova TIER 2 (CUDA pref), poi TIER 1 (qualunque provider), poi TIER 0
      - Se quick_benchmark e' True, esegue un dummy 256x256 e declassa se troppo lento
    """
    # Override esplicito
    if force_tier is None:
        env_t = os.environ.get("SCATTER_TIER")
        if env_t and env_t.isdigit():
            force_tier = int(env_t)

    if force_tier == 0:
        return ClassicTier0()

    if not _HAS_ORT:
        log.info("[SCATTER_MODELS] onnxruntime non disponibile -> Tier 0")
        return ClassicTier0()

    # Tier 3 ULTRA se forzato o auto e disponibile
    if force_tier == 3 or (force_tier is None and is_model_available(3, base_path)):
        if is_model_available(3, base_path):
            try:
                m = UltraEnsemble(base_path)
                return m
            except Exception as e:
                log.warning(f"[SCATTER_MODELS] ULTRA fallito ({e}), provo Tier2")
        elif force_tier == 3:
            raise FileNotFoundError("Tier3 ULTRA: servono Metric3D + SegFormer + CLIP")

    # Tier 2 se forzato o auto e disponibile
    if force_tier == 2 or (force_tier is None and is_model_available(2, base_path)):
        path = model_path_for(2, base_path)
        if path.exists():
            try:
                m = Metric3DLarge(path)
                if quick_benchmark and not _is_fast_enough(m, _BENCH_TIER2_MAX_MS):
                    log.warning("[SCATTER_MODELS] Tier2 troppo lento -> declasso a Tier1")
                else:
                    return m
            except Exception as e:
                log.warning(f"[SCATTER_MODELS] Tier2 fallito ({e}), provo Tier1")
        elif force_tier == 2:
            raise FileNotFoundError(f"Modello Tier2 mancante in {path}")

    # Tier 1
    if force_tier == 1 or (force_tier is None and is_model_available(1, base_path)):
        path = model_path_for(1, base_path)
        if path.exists():
            try:
                m = DepthAnythingSmall(path)
                if quick_benchmark and not _is_fast_enough(m, _BENCH_TIER1_MAX_MS):
                    log.warning("[SCATTER_MODELS] Tier1 troppo lento -> declasso a Tier0")
                else:
                    return m
            except Exception as e:
                log.warning(f"[SCATTER_MODELS] Tier1 fallito ({e}), uso Tier0")
        elif force_tier == 1:
            raise FileNotFoundError(f"Modello Tier1 mancante in {path}")

    return ClassicTier0()


def _is_fast_enough(model: ScatterModelBase, max_ms: float) -> bool:
    """Quick benchmark con dummy 256x256."""
    try:
        dummy = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        # Warmup (la prima inference e' sempre piu' lenta)
        model.analyze(dummy)
        # Misura
        t0 = time.time()
        model.analyze(dummy)
        dt = (time.time() - t0) * 1000
        log.info(f"[SCATTER_MODELS] benchmark {model.name}: {dt:.0f}ms (soglia {max_ms}ms)")
        return dt <= max_ms
    except Exception as e:
        log.warning(f"[SCATTER_MODELS] benchmark fallito: {e}")
        return False
