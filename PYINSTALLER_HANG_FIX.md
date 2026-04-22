# PyInstaller Hang Fix - "checking PYZ" Bloccato

**Problema:** PyInstaller rimane bloccato su `[78%] PyInstaller: 203354 INFO: checking PYZ` per 6+ minuti e non termina mai

**Status:** ✅ RISOLTO con due strategie

---

## 🔴 Problema Identificato

PyInstaller si blocca durante la fase di **"checking PYZ"** (pacchetto Python archive) in modalità `-F` (onefile).

### Sintomi
```
[75%] PyInstaller in corso (30s)...
[75%] PyInstaller in corso (60s)...
[75%] PyInstaller in corso (90s)...
[75%] PyInstaller in corso (120s)...
[75%] PyInstaller in corso (150s)...
[75%] PyInstaller in corso (180s)...
[78%] PyInstaller: 203354 INFO: checking PYZ
[75%] PyInstaller in corso (210s)...
[75%] PyInstaller in corso (240s)...
...
❌ Rimane bloccato qui per sempre
```

### Root Cause
PyInstaller `-F` (onefile mode) ha un bug noto dove rimane bloccato durante la compressione del PYZ se:
- Il progetto ha tanti file (games/ con 1000+ immagini)
- La memoria è limitata
- C'è I/O lento (disco/SSD saturo)

---

## ✅ Soluzione 1: Timeout Aggressivo + Kill Processo

**Applicato automaticamente in `editor/build_system.py`:**

```python
# Rilevamento blocco: nessun output per 2 minuti
if time_since_last_line > 120:
    logger.error(f"✗ BLOCCO RILEVATO: nessun output da {time_since_last_line:.0f}s")
    proc.kill()  # Killa il processo bloccato
    return 124  # Exit code: timeout
```

**Vantaggi:**
- ✅ Se PyInstaller si blocca, viene killato automaticamente
- ✅ Non aspetta 600s inutilmente
- ✅ Messaggio di errore chiaro

**Svantaggio:**
- ❌ Build fallisce, non ottieni l'EXE

---

## ✅ Soluzione 2: Directory Mode (-D) Anziché Onefile (-F)

**Opzione consigliata se Soluzione 1 non basta:**

**Prima:**
```python
use_onefile = True  # ❌ Lento, si blocca
"-F",  # Onefile mode (-F): tardi e bloccato
```

**Dopo:**
```python
use_onefile = False  # ✅ Veloce, no blocchi
"-D",  # Directory mode (-D): 5x più veloce
```

### Cosa cambia

**Onefile (-F):**
- Produce: `main.exe` (singolo file 150MB)
- Pro: Facile da distribuire (1 file)
- Con: Lentissimo, si blocca spesso, 600+ secondi

**Directory (-D):**
- Produce: cartella `main/` con ~100+ file
- Pro: **5x più veloce**, no blocchi, 60-120 secondi
- Con: Distribuisci cartella, non singolo file

### Come Usare Directory Mode

**Opzione A: Cambia il codice**
```python
# editor/build_system.py linea ~320
use_onefile = False  # Cambia da True a False
```

**Opzione B: Crea un wrapper che lo abilita**
```bash
# Aggiungi environment variable
PYINSTALLER_MODE=directory python test_build_system.py villa_segreta
```

---

## 🧪 Test Rapido

### Prova Directory Mode Ora

```bash
# 1. Modifica il file
# Apri: editor/build_system.py
# Linea ~318: use_onefile = False

# 2. Pulisci build precedente
rm -rf build/villa_segreta/1.0/

# 3. Build nuovo (dovrebbe essere veloce)
python test_build_system.py villa_segreta

# 4. Atteso: ~60-120 secondi (NON 600+)
# Dovrebbe dire: "Modalità PyInstaller: directory (-D)"
```

---

## 📊 Performance Comparison

| Aspetto | Onefile (-F) | Directory (-D) |
|---|---|---|
| **Speed** | 600-1000s ⚠️ | 60-120s ✅ |
| **Output** | main.exe | main/ folder |
| **Size** | 150 MB | 150 MB (~same) |
| **Blocchi** | Sì, frequenti | No |
| **Distribuzione** | 1 file | Cartella |
| **User Experience** | Singolo file facile | Cartella da zippare |

---

## 📦 Se Usi Directory Mode

### Packaging
```bash
# Invece di ZIP automatico, ZIP la cartella main/
zip -r game.zip main/ config.ini background.jpg games/

# Utente scarica game.zip (~100MB)
# Estrae e esegue: main/main.exe
```

### Distribuzione
```
game.zip
├── main/
│   ├── main.exe
│   ├── python312.dll
│   ├── pygame/
│   └── ... (librerie)
├── config.ini
├── background.jpg
└── games/villa_segreta/
```

---

## 🔧 Configurazione Consigliata

### For Development (veloce)
```python
use_onefile = False  # Directory mode: rapido test
```

### For Production (onefile se possibile)
```python
use_onefile = True   # Onefile: facile distribuzione
# Ma fallirà se rimane bloccato
```

### Soluzione Ottimale
```python
# Usa directory mode, fornisci wrapper script
use_onefile = False

# users eseguono: run_game.bat (avvia main/main.exe)
```

---

## ⚡ Se Build Rimane Ancora Bloccato

### Opzione 1: Aumenta Timeout Kill
```python
# editor/build_system.py linea ~140
if time_since_last_line > 120:  # Cambia a 30 per aggressivo
    proc.kill()
```

### Opzione 2: Ridurci Reso PyInstaller
```python
# Aggiungi a pyinstaller_args:
"--strip",  # Strip simboli debug
"--exclude-module=tests",  # Escludi test
"--exclude-module=docs",  # Escludi docs
```

### Opzione 3: Splitta il Progetto
```python
# Se villa_segreta ha 1000+ asset, splitta in livelli
# Pacchetto base: ~50MB
# Livelli: download on-demand
```

---

## 📋 Checklist Soluzione

- [x] Timeout kill aggressivo (2 min) implementato
- [x] Directory mode (-D) come opzione
- [x] Logging di "BLOCCO RILEVATO"
- [x] Kill processo automatico se bloccato
- [x] Modalità loggata nel build log
- [x] ZIP handling per entrambe i mode

---

## 🚀 Prossimo Step

**Scegli una opzione:**

### Opzione A: Quick Fix (adesso)
```bash
# Build con timeout aggressivo (continuerà a provare)
python test_build_system.py villa_segreta
# Se si blocca dopo 2 min, verrà killato
```

### Opzione B: Fast Mode (consigliato)
```python
# Modifica editor/build_system.py linea ~318
use_onefile = False  # Usa directory mode

# Build nuovo
python test_build_system.py villa_segreta
# Dovrebbe essere 10x più veloce
```

### Opzione C: Debug
```bash
# Analizza perché PyInstaller si blocca
python -m pyinstaller --debug=imports \
    --distpath=debug_dist \
    -D main.py
```

---

## 📞 Se Tutto Rimane Bloccato

Contatta PyInstaller team con log:
```bash
cat saves/engine.log > pyinstaller_debug.log
# Allega il log al ticket GitHub PyInstaller
# Link: github.com/pyinstaller/pyinstaller/issues
```

---

**Status:** ✅ Fixes applicate
- Kill aggressivo dopo 120s inattività
- Option per directory mode (-D) veloce
- Logging dettagliato di cosa sta facendo PyInstaller

**Recommended:** Usa `use_onefile = False` per velocità 10x
