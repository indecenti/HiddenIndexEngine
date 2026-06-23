"""
editor/web_rules.py

FONTE UNICA DI VERITA' per le costanti di gioco condivise tra l'engine Python e
il runtime web (editor/web_template/runtime/core.js, RULES_DEFAULTS).

Questo modulo legge i valori REALI dall'engine e li espone come dict, che
l'exporter inietta in manifest.rules. Il runtime web li usa al posto di costanti
hardcoded. Cosi' una modifica a una costante nell'engine si propaga al web al
prossimo export, senza duplicazione da ricordare.

Vedi docs/web/WEB_EXPORT_SYNC.md (sezioni B e C).
"""

from __future__ import annotations

import inspect


def engine_rules() -> dict:
    """Estrae le costanti canoniche dall'engine. Solo lettura, nessun side effect."""
    from engine import level_manager as LM
    from engine.scaling_manager import REF_W, REF_H
    from engine.hint_system import HintSystem
    from engine.level_manager import RewardTracker

    # HintSystem.__init__ non usa i suoi argomenti se non per memorizzarli:
    # istanziarlo con None/None e' sicuro e ci da' i valori reali delle costanti.
    hs = HintSystem(None, None)

    # initial_hints (hint gratuiti) e' un default di firma del costruttore.
    hint_free = inspect.signature(RewardTracker.__init__).parameters["initial_hints"].default

    return {
        # Scoring (engine/level_manager.py)
        "points_per_object": int(LM.POINTS_PER_OBJECT),
        "bonus_time_max": int(LM.BONUS_TIME_MAX),
        "star_multiplier": {str(k): v for k, v in LM.STAR_MULTIPLIER.items()},
        "miss_time_penalty": float(LM.MISS_PENALTY_TIME),
        "miss_point_penalty": abs(int(LM.MISS_PENALTY_SCORE)),
        # Curva progressiva miss consecutivi + finestra (s). Il web replica la
        # macchina a stati dell'engine (game.js::_missPenalty / _onPointer).
        "miss_penalty_curve": [abs(int(p)) for p in LM.MISS_PENALTY_CURVE],
        "miss_combo_window": float(LM.MISS_COMBO_WINDOW),
        # Risoluzione di riferimento (engine/scaling_manager.py)
        "ref_w": int(REF_W),
        "ref_h": int(REF_H),
        # Hint (engine/hint_system.py + RewardTracker)
        "hint_free": int(hint_free),
        "hint_cooldown": float(hs.manual_hint_cooldown_max),
        "hint_penalties": [abs(int(p)) for p in hs.hint_penalties if p != 0],
        "hint_max_uses": int(hs.max_hints_before_disable),
        # Soglia 3 stelle (engine/level_manager._calc_stars: bonus_ratio >= 0.66)
        "bonus_ratio_3star": 0.66,
    }
