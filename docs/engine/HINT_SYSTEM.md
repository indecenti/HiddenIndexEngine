# Hint System — Hidden Engine

## Overview

An **advanced, configurable** hint system for professional hidden object games:

- **Visual auto-hint**: after N seconds of inactivity the object receives a growing glow
- **Manual hint**: button with cooldown and a progressive score penalty
- **Layer intensity**: hidden objects receive more visible hints
- **Progressive disabling**: after 3 hints the button is disabled
- **Statistics**: hints used are tracked for achievements and replayability

---

## In-game usage

### Automatic hint

1. **Look for an object** during the scene
2. After ~30 seconds of inactivity (configurable) the object receives a growing **cyan glow**
3. The glow grows for 10 seconds until it reaches maximum visibility
4. When the object is found, the timer resets

### Manual hint

1. Press **H** during the scene (or click the "?" button in the HUD)
2. An object not yet found receives a cyan particle effect + glow
3. The button enters a **20-second cooldown**
4. **Score penalty**:
   - 1st hint: -50 pts
   - 2nd hint: -75 pts
   - 3rd hint: -100 pts + button disabled

### No hints

Completing the level with 0 hints unlocks the **"No Hints"** achievement and grants bonus points.

---

## Configuration

### Game config (game_config.json)

```json
{
  "layer_hint_intensity": {
    "objects_low": 1.8,      // Hidden objects = hint 80% more visible
    "objects_mid": 1.0,      // Standard intensity
    "objects_high": 0.6,     // Obvious objects = subtle hint
    "overlay": 0.4
  }
}
```

**How it works**:
- The base glow is multiplied by the layer factor
- Objects on `objects_low` receive a 1.8x more intense glow
- This balances difficulty: hidden objects are easier to find with hints

### Object (objects_catalog.json)

```json
{
  "id": "rusty_key",
  "default_hint_delay": 30   // Seconds before the first auto-hint glow
}
```

This value can be overridden **per scene** in scene.json:

```json
{
  "instance_id": "key_1",
  "catalog_id": "rusty_key",
  "hint_delay": 45           // Override: wait 45 s before the glow
}
```

---

## Technical implementation

### Flow

```
[core.py]
  |
  hint.update(dt, objects, layer_config)  <- every frame
  |
  [for every object not yet found]
    - increment inactivity_timer
    - if > hint_delay, activate the growing glow
    - glow = 0.3 + (time_after_delay / 10) x 0.7
    - multiply by layer_hint_intensity
  |
  [player presses H or clicks the button]
    |
    use_manual_hint() -> (success, penalty)
    |
    level_manager.apply_score_penalty(penalty)
    |
    effects.spawn_hint_effect()  <- cyan particles
```

### Statistics

When the scene ends:

```python
SceneResult {
  hints_used: 2,  # tracked automatically
  score: 450,     # penalties already applied
  # "no_hints" achievement = hints_used == 0
}
```

It is saved through SaveManager for permanent statistics.

---

## Visual effects

### Auto-hint glow (cyan)

- **Color**: cyan (100, 180-255, 255)
- **Intensity**: grows gradually from 0.3 to 1.0 in the 10 seconds after the delay
- **Layer modulation**: multiplied by layer_hint_intensity
- **Rendering**: integrated into object rendering

### Manual hint effect (particles)

- **Color**: bright cyan
- **Particles**: 20 particles in a burst
- **Speed**: 60-140 px/s
- **Duration**: ~1 second
- **Sound**: optional (via audio_manager)

---

## Achievements and replayability

### "No Hints" achievement

```json
{
  "id": "no_hints_garden",
  "condition": "level_no_hints",
  "unlock_on": "hints_used == 0 AND level_complete"
}
```

### Recurring motivation

The system creates **4 different reasons** to replay:

1. **Score**: "Can I do better?"
2. **Speed**: "Can I finish in 2 minutes?"
3. **Precision**: "Can I avoid wrong clicks?"
4. **Difficulty**: "Can I make it without hints?"

Every metric is **independent**: the player with the top score can come back for the time record.

---

## Tunable parameters

In `HintSystem.__init__()`:

```python
self.manual_hint_cooldown_max = 20.0  # seconds between hints
self.max_hints_before_disable = 3     # max hints before disabling
self.hint_penalties = [0, -50, -75, -100]  # progressive penalties
```

**Suggested balancing**:
- **Easy**: cooldown=10, max_hints=5, penalties=[-25, -50, -50]
- **Normal**: cooldown=20, max_hints=3, penalties=[-50, -75, -100]
- **Hard**: cooldown=30, max_hints=2, penalties=[-100, -150]

---

## Debug

### Full log

```bash
# core.py: H key pressed
[INFO] Hint used: key_1 | Penalty: -50 pts | Hints: 1

# hint_system.py: end-of-scene statistics
hints_used_total: 2
per_object: { "key_1": 2, "clock_1": 0 }
no_hints_achievement: false
```

### Disable auto-hint (testing)

```python
# core.py
self.hint.auto_hint_enabled = False
```

### Force a manual hint (debug)

```python
# console during debugging
self.hint.hints_used_total = 0  # reset
self.hint.manual_hint_cooldown = 0.0  # available immediately
```

---

## Files involved

- **engine/hint_system.py** — core logic (180 lines)
- **engine/effects_engine.py** — particle rendering
- **engine/level_manager.py** — score integration + statistics
- **engine/core.py** — game loop + H key input
- **game_config.json** — layer_hint_intensity configuration

---

## Next steps

- [ ] "?" button in the HUD for the visual hint
- [ ] Hint sound (cyan whoosh)
- [ ] Pulsing glow animation instead of growing (optional)
- [ ] Hint context: "Look at the bottom right" (text, optional)
- [ ] Leaderboard statistics: "Run without hints" category

---

**Status**: implementation complete
**Last modified**: 2026-04-16
