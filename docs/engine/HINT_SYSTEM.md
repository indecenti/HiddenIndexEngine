# 🎯 Sistema Hint Professionale — Hidden Engine

## Panoramica

Sistema hint **avanzato e configurabile** per giochi hidden object professionali:

- ✅ **Auto-hint visuale**: dopo N secondi di inattività, l'oggetto riceve un glow crescente
- ✅ **Hint manuale**: pulsante con cooldown, penalità punti progressiva
- ✅ **Layer intensity**: oggetti nascosti ricevono hint più visibili
- ✅ **Disabilitazione progressiva**: dopo 3 hint, il pulsante si disabilita
- ✅ **Statistiche**: traccia hints usati per achievement e regiocabilità

---

## 🎮 Uso Nel Gioco

### Hint Automatico

1. **Cerca un oggetto** durante la scena
2. Dopo ~30 secondi di inattività (configurabile), l'oggetto riceve un **glow ciano** crescente
3. Il glow aumenta per 10 secondi fino a raggiungere massima visibilità
4. Quando l'oggetto è trovato, il timer si resetta

### Hint Manuale

1. Premi **H** durante la scena (o clicca il pulsante "?" nella HUD)
2. L'oggetto non ancora trovato riceve un effetto particellare ciano + glow
3. Il pulsante entra in **cooldown per 20 secondi**
4. **Penalità punti**:
   - 1° hint: -50 pt
   - 2° hint: -75 pt
   - 3° hint: -100 pt + pulsante disabilitato

### Nessun Hint

Completare il livello con 0 hint utilizzati sblocca l'achievement **"Senza Hint"** e fornisce bonus punti.

---

## 📋 Configurazione

### Game Config (game_config.json)

```json
{
  "layer_hint_intensity": {
    "objects_low": 1.8,      // Oggetti nascosti = hint 80% più visibile
    "objects_mid": 1.0,      // Intensità standard
    "objects_high": 0.6,     // Oggetti evidenti = hint sottile
    "overlay": 0.4
  }
}
```

**Come funziona**:
- Il glow base è moltiplicato per il fattore del layer
- Oggetti su `objects_low` ricevono glow 1.8× più intenso
- Questo bilanzia la difficoltà: oggetti nascosti sono più facili da trovare con gli hint

### Oggetto (objects_catalog.json)

```json
{
  "id": "chiave_arrugginita",
  "default_hint_delay": 30   // Secondi prima del primo glow auto-hint
}
```

Questo valore può essere sovrascritto **per scena** in scene.json:

```json
{
  "instance_id": "chiave_1",
  "catalog_id": "chiave_arrugginita",
  "hint_delay": 45           // Override: aspetta 45 sec prima del glow
}
```

---

## 🔧 Implementazione Tecnica

### Flusso

```
[core.py]
  ↓
  hint.update(dt, objects, layer_config)  ← Ogni frame
  ↓
  [per ogni oggetto non trovato]
    - Incrementa inactivity_timer
    - Se > hint_delay, attiva glow crescente
    - Glow = 0.3 + (tempo_dopo_delay / 10) × 0.7
    - Moltiplica per layer_hint_intensity
  ↓
  [Giocatore preme H o clicca pulsante]
    ↓
    use_manual_hint() → (success, penalty)
    ↓
    level_manager.apply_score_penalty(penalty)
    ↓
    effects.spawn_hint_effect()  ← Particelle ciano
```

### Statistiche

Quando la scena termina:

```python
SceneResult {
  hints_used: 2,  # Tracciato automaticamente
  score: 450,     # Già sconta penalità
  # Achievement "no_hints" = hints_used == 0
}
```

Viene salvato in SaveManager per statistiche permanenti.

---

## 🎨 Effetti Visivi

### Glow Auto-Hint (Azzurro)

- **Colore**: Ciano (100, 180-255, 255)
- **Intensità**: Cresce gradualmente da 0.3 a 1.0 nei 10 secondi dopo delay
- **Layer modulation**: moltiplicato per layer_hint_intensity
- **Rendering**: Integrato nel rendering degli oggetti

### Effetto Hint Manuale (Particelle)

- **Colore**: Ciano luminoso
- **Particelle**: 20 particelle in esplosione
- **Velocità**: 60-140 px/sec
- **Durata**: ~1 secondo
- **Suono**: Opzionale (via audio_manager)

---

## 📊 Achievement & Regiocabilità

### Achievement "Senza Hint"

```json
{
  "id": "no_hints_giardino",
  "condition": "level_no_hints",
  "unlock_on": "hints_used == 0 AND level_complete"
}
```

### Motivazione Ricorsiva

Il sistema crea **4 motivi diversi** per rigiocare:

1. **Punteggio**: "Posso fare di più?"
2. **Velocità**: "Posso finire in 2 min?"
3. **Precisione**: "Posso evitare click sbagliati?"
4. **Difficoltà**: "Posso farcela senza hint?"

Ogni metrica è **indipendente**: il giocatore che ha il massimo punti può tornare per il tempo record.

---

## ⚙️ Parametri Sintonizzabili

Nel `HintSystem.__init__()`:

```python
self.manual_hint_cooldown_max = 20.0  # Secondi tra un hint e l'altro
self.max_hints_before_disable = 3     # Max hint prima di disabilitare
self.hint_penalties = [0, -50, -75, -100]  # Penalità progressive
```

**Bilanciamento consigliato**:
- **Facile**: cooldown=10, max_hints=5, penalties=[-25, -50, -50]
- **Normale**: cooldown=20, max_hints=3, penalties=[-50, -75, -100]
- **Difficile**: cooldown=30, max_hints=2, penalties=[-100, -150]

---

## 🐛 Debug

### Log Completo

```bash
# core.py: Tasto H premuto
[INFO] Hint usato: chiave_1 | Penalità: -50 pt | Hints: 1

# hint_system.py: Statistiche a fine scena
hints_used_total: 2
per_object: { "chiave_1": 2, "orologio_1": 0 }
no_hints_achievement: false
```

### Disabilita Auto-Hint (Test)

```python
# core.py
self.hint.auto_hint_enabled = False
```

### Fuerza Hint Manuale (Debug)

```python
# console durante debug
self.hint.hints_used_total = 0  # Reset
self.hint.manual_hint_cooldown = 0.0  # Disponibile subito
```

---

## 📚 Files Coinvolti

- **engine/hint_system.py** — Logica core (180 righe)
- **engine/effects_engine.py** — Rendering particelle
- **engine/level_manager.py** — Integrazione punteggio + statistiche
- **engine/core.py** — Game loop + input H
- **game_config.json** — Configurazione layer_hint_intensity

---

## 🚀 Next Steps

- [ ] Pulsante "?" nella HUD per hint visuale
- [ ] Suono hint (whoosh ciano)
- [ ] Animazione glow pulsante invece di crescente (opzionale)
- [ ] Hint context: "Guarda in basso a destra" (testo, opzionale)
- [ ] Statistiche leaderboard: "Run without hints" categoria

---

**Status**: ✅ Implementazione completa e professionale
**Ultima modifica**: 2026-04-16
