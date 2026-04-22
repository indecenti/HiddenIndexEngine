# 🚀 NEXT STEPS — Roadmap Immediata

## ✅ COSA È STATO FATTO (15 aprile 2026)

1. ✅ **Fix Logging Unicode** — Sostituito `→` con `->` in click_detector.py e json_validator.py
2. ✅ **Asset Test Minimali** — Creati background.jpg, chiave_icon.png, orologio_icon.png
3. ✅ **Test Run End-to-End** — Flusso completo funzionante: Menu → Scena → Click → Risultati → Save
4. ✅ **Verifica Moduli** — Tutti i 16 moduli core implementati e funzionanti
5. ✅ **Documentazione** — Creato ANALYSIS_REPORT.md completo

---

## 📋 TODO LISTA ORDINATA

### **IMMEDIATE (Oggi/Domani) — 1-2 ore**

#### 1. **Estendere Test Coverage**
- [ ] Test con risoluzioni diverse (640×480, 2560×1440, 4K)
- [ ] Test cambio lingua runtime (IT → EN → FR)
- [ ] Test fullscreen mode (toggle in impostazioni)
- [ ] Test pausa (ESC durante scena)
- [ ] Test hint system (click destro)
- [ ] Test menu impostazioni completo

**Come testare**:
```bash
# Modifica config.ini
resolution_w = 1920
resolution_h = 1080
fullscreen = 0
language = it

python main.py --game villa_segreta
```

---

#### 2. **Aggiungere Asset Veri (Opzionale ma Consigliato)**
- [ ] Background HD (1280×720 minimum)
- [ ] 5-10 icone oggetti veri (48×48 PNG con alpha)
- [ ] Logo gioco
- [ ] Audio ambientale (menu_theme.mp3)
- [ ] SFX (click, trovato, errore)

**Placement**:
```
games/villa_segreta/
├── audio/
│   ├── menu_theme.mp3
│   └── sfx/
│       ├── click.wav
│       ├── found.wav
│       └── error.wav
├── objects/
│   ├── chiave_icon.png ✅ (esiste)
│   ├── orologio_icon.png ✅ (esiste)
│   ├── ... altri oggetti
└── ui/
    ├── logo.png
    └── menu_background.png
```

---

### **SHORT TERM (Questa Settimana) — 4-8 ore**

#### 3. **Aggiungere Più Livelli**
- [ ] Copiar cartella `level1_giardino` → `level2_castello`
- [ ] Modificare JSON (nome, timer, oggetti, coordinate)
- [ ] Aggiungere background nuovo
- [ ] Aggiungere stringhe traduzioni (it.json, en.json, ecc.)

**Struttura**:
```
games/villa_segreta/levels/
├── level1_giardino/
│   ├── level_config.json
│   └── scene1/ scene2/ scene3/
├── level2_castello/          ← NUOVO
│   ├── level_config.json
│   └── scene1/ scene2/ scene3/
└── level3_citta/             ← NUOVO
    └── ...
```

**Template level_config.json**:
```json
{
  "id": "level2_castello",
  "name_key": "level2_name",
  "description_key": "level2_desc",
  "unlock_after": "level1_giardino",
  "scenes": [
    {"id": "scene1_cucina", "order": 1, "time_limit": 120},
    {"id": "scene2_torre", "order": 2, "time_limit": 100}
  ]
}
```

---

#### 4. **Tradurre Completamente**
- [ ] Aggiungere chiavi mancanti in strings/it.json
- [ ] Tradurre per en.json, es.json, fr.json, de.json
- [ ] Testare multilingua runtime

**Chiavi essenziali**:
```json
{
  "game_title": "La Villa Segreta",
  "level1_name": "Il Giardino Abbandonato",
  "level1_desc": "Un luogo pieno di segreti...",
  "obj_chiave": "La Chiave Arrugginita",
  "obj_orologio": "L'Orologio Antico",
  "scene1_name": "La Fontana",
  "hud_time": "Tempo",
  "hud_score": "Punti"
}
```

---

### **MEDIUM TERM (2-3 Settimane) — 8-16 ore**

#### 5. **Implementare Moduli Avanzati (Opzionale)**

**5a. Achievements**
- [ ] Creare `engine/achievements_manager.py`
- [ ] Leggere spec §13 per logica condizioni
- [ ] Integrare in `level_manager.py` per evaluazione a fine livello
- [ ] Visualizzare in menu achievements

**5b. Leaderboard**
- [ ] Creare `engine/leaderboard_manager.py`
- [ ] Tracciare best_score, best_time_seconds per livello
- [ ] Calcolare trend (ultimi N run)
- [ ] Visualizzare dashboard

---

#### 6. **Configurare PyInstaller per EXE**
- [ ] Creare spec file PyInstaller
- [ ] Build EXE con `--onefile`
- [ ] Testare su Windows clean (no Python)
- [ ] Creare installer NSIS

**Comandi**:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico main.py
```

---

### **NICE-TO-HAVE (Optional) — 16+ ore**

#### 7. **Editor Livelli Grafico**
- [ ] Creare `editor/editor_main.py` (Tkinter GUI)
- [ ] Posizionare oggetti drag-and-drop
- [ ] Preview tempo reale
- [ ] Export JSON automatico

---

#### 8. **Profili Qualità Rendering**
- [ ] Configurare in `config.ini`: quality=high/medium/low
- [ ] Ridurre particelle su bassa qualità
- [ ] Misurare FPS e suggerire downgrade se <45 FPS

---

## 🎮 COME USARE ADESSO

### Test Rapido (5 min)
```bash
cd G:\HiddenIndexEngine
python main.py --game villa_segreta
# Clicca menu → livello → obietti → risultati
```

### Modifica Configurazione (config.ini)
```ini
[engine]
default_game = villa_segreta
resolution_w = 1280
resolution_h = 720
fullscreen = 0
language = it
```

### Aggiungere Nuovo Gioco
1. Copiare `games/villa_segreta` → `games/new_game`
2. Modificare `game_config.json`
3. Creare livelli/scene/oggetti
4. Lanciare: `python main.py --game new_game`

---

## 📊 CHECKLIST PRIMA DI RELEASE

- [ ] Tutti i livelli testati (almeno 5 min gameplay)
- [ ] Tutte le lingue testate (cambio da menu)
- [ ] Risoluzione 1280×720 + 1920×1080 testate
- [ ] Fullscreen + Windowed testate
- [ ] Pausa (ESC) funzionante
- [ ] Salvataggio persistente verificato
- [ ] Nessun errore nei log per 30 min gameplay
- [ ] EXE compilato e testato su PC clean
- [ ] README.md scritto con istruzioni
- [ ] Credits/Licenze inserite

---

## 📞 SUPPORT

**Domande frequenti**:

**P: Perché il background è nero?**  
R: Background.jpg non caricato correttamente. Verifica il path in scene.json vs. file system.

**P: Come aggiungere un oggetto nuovo?**  
R: Aggiungi entry in `objects_catalog.json` + icona PNG + coordinate nel `scene.json`.

**P: Come cambiare il timer di una scena?**  
R: Modifica `time_limit` nel `scene.json` della scena specifica.

**P: Posso avere più scene nello stesso livello?**  
R: Sì! Aggiungi folder `scene2/`, `scene3/` ecc. e list in `level_config.json["scenes"]`.

---

## 🎯 GOAL FINALE

**MVP (Minimum Viable Product)**:
- 3 livelli completi (9 scene totali)
- 5-10 oggetti unici per livello
- Audio ambiente
- Multilingua (IT/EN)
- EXE distribuibile

**Tempo stimato**: 2-3 settimane di lavoro steady.

---

**Last Updated**: 2026-04-15  
**Status**: ✅ **READY FOR CONTENT CREATION**
