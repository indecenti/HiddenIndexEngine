"""
editor/tools/object_profiles.py

Object profile DB: pre-compute zero-shot CLIP "context affinity" per ogni oggetto
del catalogo, salvato in SQLite. Permette al scatter di matchare oggetto -> zona BG
in modo semanticamente coerente (un libro va su mensole, un lampadario al soffitto).

Schema SQLite:
    CREATE TABLE object_profile (
        catalog_id   TEXT PRIMARY KEY,
        style        TEXT NOT NULL,
        prompts_ver  TEXT NOT NULL,
        visual_emb   BLOB NOT NULL,    -- 512 float32
        profile      TEXT NOT NULL,    -- JSON {context: score}
        computed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

Path: engine/data/object_profiles.db

API:
    build_profiles(catalog, style, base_path, clip_visual, clip_text, overwrite=False)
    get_profile(catalog_id, base_path) -> ProfileRecord | None
    get_profiles_for_style(style, base_path) -> dict[catalog_id -> ProfileRecord]
    profile_score(profile, ade_class_id) -> float  # query lookup
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable

import numpy as np

log = logging.getLogger(__name__)

DB_REL_PATH = "engine/data/object_profiles.db"
SCHEMA_VERSION = "v1"
PROMPTS_VERSION = "v1"  # incrementa se cambi PROMPTS o ADE_TO_CONTEXT


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PROMPTS — ogni "context" e' una zona BG semantica
# ─────────────────────────────────────────────────────────────────────────────
# Mappiamo ogni context a uno o piu' prompts CLIP. Embedding texto medio
# dei prompts diventa il vettore-target di quel context.
CONTEXTS: dict[str, list[str]] = {
    "floor": [
        "an object resting on the wooden floor",
        "an item lying on the ground",
        "a thing on the floor of a room",
    ],
    "table": [
        "an object placed on a table or desk",
        "an item on a wooden table top",
        "something resting on a desk surface",
    ],
    "shelf": [
        "an object on a wooden shelf",
        "an item placed on a bookshelf",
        "something arranged on a shelving unit",
    ],
    "wall": [
        "an object mounted on a wall",
        "a picture or item hanging on a wall",
        "something attached to a vertical wall",
    ],
    "ceiling": [
        "an object hanging from the ceiling",
        "a chandelier or lamp suspended from above",
        "something attached to the ceiling",
    ],
    "outdoor": [
        "an outdoor object in a garden or yard",
        "an item used outside in nature",
        "an outdoor decoration or equipment",
    ],
    "small_handheld": [
        "a small handheld personal item",
        "a tiny object you can hold in your hand",
        "a small portable trinket",
    ],
    "large_furniture": [
        "a large piece of furniture",
        "a big bulky household object",
        "a tall freestanding item",
    ],
    "kitchen": [
        "a kitchen utensil or tool",
        "an item used for cooking food",
        "a piece of kitchenware",
    ],
    "tool": [
        "a hand tool or instrument",
        "a mechanical tool for working",
        "a piece of equipment",
    ],
    "book_paper": [
        "a book or paper document",
        "a scroll or piece of writing",
        "a stack of paper sheets",
    ],
    "decorative": [
        "a decorative ornament",
        "an artistic item for decoration",
        "a fancy display object",
    ],
}


# Mappa: classe ADE20K (id) -> context name
# (id usati da SegFormer-B0 ADE20K standard)
# Solo i piu' rilevanti per scene HO (interni)
ADE_TO_CONTEXT: dict[int, str] = {
    3:   "floor",   # floor
    6:   "floor",   # road
    13:  "floor",   # earth/ground
    28:  "floor",   # rug
    53:  "floor",   # stairs

    15:  "table",   # table
    33:  "table",   # desk
    64:  "table",   # coffee table

    25:  "shelf",   # shelf
    24:  "shelf",   # cabinet (drawer-like)

    0:   "wall",    # wall
    8:   "wall",    # window
    14:  "wall",    # door

    5:   "ceiling", # ceiling

    4:   "outdoor", # tree
    9:   "outdoor", # grass
    16:  "outdoor", # mountain
    21:  "outdoor", # water/sea
    23:  "outdoor", # sofa (inside, but treat as misc)
}


def db_path(base_path: Path) -> Path:
    return base_path / DB_REL_PATH


def _ensure_schema(con: sqlite3.Connection):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS object_profile (
            catalog_id  TEXT PRIMARY KEY,
            style       TEXT NOT NULL,
            prompts_ver TEXT NOT NULL,
            visual_emb  BLOB NOT NULL,
            profile     TEXT NOT NULL,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_style ON object_profile(style);
    """)
    con.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION))
    con.commit()


def _connect(base_path: Path) -> sqlite3.Connection:
    p = db_path(base_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    _ensure_schema(con)
    return con


def _compute_context_targets(clip_text) -> dict[str, np.ndarray]:
    """Per ogni context, encoda tutti i suoi prompts, fa la media, normalizza.
    Restituisce dict[context_name -> (512,) float32 L2-normalized]."""
    targets = {}
    all_prompts = []
    prompt_to_ctx = []
    for ctx, prompts in CONTEXTS.items():
        for p in prompts:
            all_prompts.append(p)
            prompt_to_ctx.append(ctx)
    log.info(f"[OBJ_PROFILES] encoding {len(all_prompts)} context prompts...")
    t0 = time.time()
    feats = clip_text.encode_text(all_prompts)  # (N, 512) L2-normalized
    log.info(f"[OBJ_PROFILES] text encoding done in {(time.time()-t0)*1000:.0f}ms")
    # Media per context
    for ctx in CONTEXTS:
        mask = [c == ctx for c in prompt_to_ctx]
        ctx_feats = feats[mask]
        mean = ctx_feats.mean(axis=0)
        mean /= (np.linalg.norm(mean) + 1e-8)
        targets[ctx] = mean.astype(np.float32)
    return targets


@dataclass
class ProfileRecord:
    catalog_id: str
    style: str
    visual_emb: np.ndarray   # (512,) float32 L2-normalized
    profile: dict             # {context_name -> score}


def build_profiles(catalog: list[dict], style: str, base_path: Path,
                   clip_visual, clip_text,
                   overwrite: bool = False,
                   progress_cb=None) -> int:
    """Pre-compute profiles per tutti gli oggetti del catalogo dello stile.

    Skip oggetti gia' in db con prompts_ver matching (unless overwrite=True).
    Restituisce numero di oggetti processati (nuovi/aggiornati).
    """
    style_pool = [c for c in catalog if c.get("style", "real") == style]
    if not style_pool:
        log.warning(f"[OBJ_PROFILES] nessun oggetto stile '{style}'")
        return 0

    # Calcola targets una sola volta
    log.info(f"[OBJ_PROFILES] build_profiles style='{style}' ({len(style_pool)} oggetti)")
    targets = _compute_context_targets(clip_text)
    # Matrice targets (K_contexts, 512) per dot product veloce
    ctx_names = list(targets.keys())
    target_matrix = np.stack([targets[c] for c in ctx_names], axis=0)

    con = _connect(base_path)
    # Skip set: oggetti gia' presenti con prompts_ver coerente
    if not overwrite:
        existing = set()
        for row in con.execute("SELECT catalog_id FROM object_profile WHERE prompts_ver = ?",
                                (PROMPTS_VERSION,)):
            existing.add(row[0])
    else:
        existing = set()

    to_process = [c for c in style_pool if c["id"] not in existing]
    log.info(f"[OBJ_PROFILES] {len(to_process)}/{len(style_pool)} da processare")

    t0 = time.time()
    n_done = 0
    n_skipped = 0
    for i, entry in enumerate(to_process):
        cid = entry["id"]
        icon_rel = entry.get("icon", "")
        candidates = [
            base_path / "engine" / "assets" / icon_rel,
            base_path / icon_rel,
        ]
        icon_path = next((p for p in candidates if p.exists()), None)
        if not icon_path:
            n_skipped += 1
            continue
        try:
            from PIL import Image
            img = Image.open(icon_path).convert("RGB")
            arr = np.array(img)
            visual_emb = clip_visual.encode_image(arr)  # (512,) L2-normalized
            # Profile = cosine similarity con tutti i context targets
            sims = (target_matrix @ visual_emb).astype(np.float32)
            profile = {ctx: float(s) for ctx, s in zip(ctx_names, sims)}
            # Salva
            con.execute(
                "INSERT OR REPLACE INTO object_profile "
                "(catalog_id, style, prompts_ver, visual_emb, profile) VALUES (?,?,?,?,?)",
                (cid, style, PROMPTS_VERSION,
                 visual_emb.tobytes(),
                 json.dumps(profile)),
            )
            n_done += 1
        except Exception as e:
            log.debug(f"[OBJ_PROFILES] errore su {cid}: {e}")
            n_skipped += 1
        if progress_cb and (i + 1) % 50 == 0:
            try: progress_cb(i + 1, len(to_process))
            except Exception: pass
    con.commit()
    con.close()
    dt = time.time() - t0
    log.info(f"[OBJ_PROFILES] done style='{style}': {n_done} processed, {n_skipped} skipped in {dt:.1f}s")
    return n_done


def get_profile(catalog_id: str, base_path: Path) -> Optional[ProfileRecord]:
    """Lookup singolo. None se non presente."""
    p = db_path(base_path)
    if not p.exists():
        return None
    con = sqlite3.connect(str(p))
    try:
        row = con.execute(
            "SELECT catalog_id, style, visual_emb, profile FROM object_profile WHERE catalog_id = ?",
            (catalog_id,)
        ).fetchone()
        if not row:
            return None
        return ProfileRecord(
            catalog_id=row[0],
            style=row[1],
            visual_emb=np.frombuffer(row[2], dtype=np.float32),
            profile=json.loads(row[3]),
        )
    finally:
        con.close()


def get_profiles_for_style(style: str, base_path: Path) -> dict[str, ProfileRecord]:
    """Bulk lookup per stile (caricato in memoria, cosi e' veloce)."""
    p = db_path(base_path)
    if not p.exists():
        return {}
    con = sqlite3.connect(str(p))
    try:
        out = {}
        for row in con.execute(
            "SELECT catalog_id, style, visual_emb, profile FROM object_profile WHERE style = ?",
            (style,)
        ):
            out[row[0]] = ProfileRecord(
                catalog_id=row[0],
                style=row[1],
                visual_emb=np.frombuffer(row[2], dtype=np.float32),
                profile=json.loads(row[3]),
            )
        return out
    finally:
        con.close()


def profile_score(profile: dict, ade_class_id: int) -> float:
    """Lookup score di affinity per una classe ADE20K.

    Restituisce 0.0 se la classe non e' mappata o se il profile manca del context.
    """
    ctx = ADE_TO_CONTEXT.get(int(ade_class_id))
    if not ctx:
        return 0.0
    return float(profile.get(ctx, 0.0))


def get_stats(base_path: Path) -> dict:
    """Statistica DB: quanti oggetti per stile."""
    p = db_path(base_path)
    if not p.exists():
        return {"db_exists": False}
    con = sqlite3.connect(str(p))
    try:
        out = {"db_exists": True, "by_style": {}, "total": 0}
        for row in con.execute("SELECT style, COUNT(*) FROM object_profile GROUP BY style"):
            out["by_style"][row[0]] = row[1]
            out["total"] += row[1]
        return out
    finally:
        con.close()
