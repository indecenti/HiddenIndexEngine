# Quick Debug Guide - Build System

## 🆘 Build Bloccato? Ecco Cosa Fare

### 1. Controllare il Log in Tempo Reale
```bash
# Monitorare il progresso
tail -f saves/engine.log | grep -E "\[.*s\]|Progress|Timeout|Watchdog|Heartbeat"

# Se vedi:
# ✓ [Progress] 72% → OK, avanzare
# ✓ [Heartbeat] PyInstaller in corso (300s) → OK, attendere
# ✗ [Timeout] TIMEOUT PyInstaller dopo 600s → BLOCCO RILEVATO
```

### 2. Timeout Rilevati?

#### PyInstaller Timeout (600s)
```
✗ TIMEOUT PyInstaller dopo 600s!
→ Possibili cause:
  • Progetto troppo grande
  • Memoria insufficiente
  • Antivirus blocca processo
  • Disco pieno

→ Azioni:
  1. Aumentare PYINSTALLER_TIMEOUT in build_system.py
  2. Controllare memoria: task manager → Memory
  3. Disabilitare antivirus temporaneamente
  4. Controllare spazio disco: C:\ (>2GB libero needed)
```

#### Build Manager Timeout (900s)
```
✗ TIMEOUT GLOBALE: Build superato 900s
→ Build manager è bloccato oltre PyInstaller
→ Azioni:
  1. Controllare log per quale step è fermo
  2. Possibile: ZIP creation lenta
  3. Aumentare GLOBAL_BUILD_TIMEOUT (non raccomandato)
```

#### UI Polling Timeout (600s)
```
Build in timeout dopo 600s
→ UI non ha ricevuto aggiornamenti per 600s
→ Il processo subprocess è probabilmente morto
→ Azioni:
  1. Controllare se build_manager.py è ancora vivo (task manager)
  2. Controllare se il file status.json viene aggiornato
  3. Cancellare il build (chiudere UI finestra)
```

### 3. Watchdog Detected Block (120s)
```
⚠️ Messagebox: "Build potrebbe essere bloccato: Progresso fermo a 75% per 120s"
→ Il watchdog ha rilevato inattività per 2 minuti
→ PyInstaller è probabilmente bloccato in un step
→ Azioni:
  1. Attendere ancora (max 600s totali)
  2. Controllare task manager → CPU usage
     • Se CPU 0% → veramente bloccato
     • Se CPU >10% → processando, attendere
  3. Se veramente bloccato: Annulla
```

---

## 📊 Dove Trovare Informazioni

### Log File
```bash
# Completo
cat saves/engine.log

# Solo build
cat saves/engine.log | grep -A2 -B2 "Build Manager"

# Solo PyInstaller
cat saves/engine.log | grep PyInstaller

# Filtrare per timing
cat saves/engine.log | grep "\[.*s\]"
```

### Status File (durante build)
```bash
# Controllare progresso in tempo reale
cat build/villa_segreta/1.0/build_status.json | jq .

# Estrarre solo progresso
jq '.progress, .step, .timestamp' build/villa_segreta/1.0/build_status.json

# Watch aggiornamenti
watch 'cat build/villa_segreta/1.0/build_status.json | jq .progress'
```

### Processus (Windows)
```cmd
# Verificare se build_manager.py è in esecuzione
tasklist | find "python"

# Verificare se pyinstaller è in esecuzione
tasklist | find "pyinstaller"

# Memory usage
tasklist /v | find "python"
```

---

## 🧪 Test Rapido Senza Build Reale

### Verificare PyInstaller
```bash
# Versione disponibile
pyinstaller --version

# Test di run
python -c "import PyInstaller; print(PyInstaller.__version__)"

# Test di script
python test_build_system.py villa_segreta --dry-run
```

### Verificare Gioco
```bash
# Controllare che il gioco esista
ls games/villa_segreta/
ls games/villa_segreta/game_config.json

# Controllare config valido
python -c "import json; print(json.load(open('games/villa_segreta/game_config.json')))"
```

### Verificare Path
```bash
# Controllare PYTHONPATH
python -c "import sys; print('\n'.join(sys.path))"

# Verificare engine
python -c "from engine.utils import get_base_path; print(get_base_path())"
```

---

## 🔍 Diagnostica Avanzata

### Se log dice "EXE non generato"
```bash
# Controllare what PyInstaller ha creato
ls -la build/villa_segreta/1.0/dist/
ls -la /tmp/build_villa_segreta_*/dist/

# Controllare error specifico
grep -A20 "Building EXE" saves/engine.log
```

### Se log dice "ZIP creazione fallito"
```bash
# Controllare spazio disco
df -h

# Controllare permessi cartella
ls -la build/villa_segreta/1.0/

# Controllare se ZIP è corrotto (interrotto)
unzip -t build/villa_segreta/1.0/villa_segreta_v1.0.zip
```

### Se watchdog dice "Build bloccato"
```bash
# Verificare che il file status.json viene aggiornato
# Controllare il timestamp
stat build/villa_segreta/1.0/build_status.json | grep Modify

# Se timestamp non cambia = processo morto
watch 'stat build/villa_segreta/1.0/build_status.json | grep Modify'
```

---

## ⚡ Quick Fixes

| Problema | Veloce Fix | Test |
|---|---|---|
| PyInstaller non trovato | `pip install pyinstaller` | `pyinstaller --version` |
| Memoria insufficiente | Chiudere altre app | `task manager` |
| Disco pieno | Pulire C:\ | `df -h` |
| Antivirus blocca | Disabilitare temp | `task manager` |
| Progetto corrotto | Ricaricare gioco | `python main.py --game villa_segreta` |
| Cache PyInstaller | Aggiunto `--clean` | Già in codice ✅ |
| Status file non aggiornato | Check processo | `ps aux \| grep python` |

---

## 📞 Escalation Path

Se dopo questi step il build è ancora bloccato:

1. **Raccogliere dati:**
   ```bash
   # Salvare log
   cp saves/engine.log debug_engine.log
   
   # Salvare status.json
   cp build/villa_segreta/1.0/build_status.json debug_status.json
   
   # Salvare output PyInstaller (se esiste)
   cp /tmp/build_villa_segreta_*/build/main/out00-Analysis.txt debug_analysis.txt 2>/dev/null || echo "N/A"
   
   # System info
   wmic os get osversion > debug_osinfo.txt
   systeminfo | find "Memory" >> debug_osinfo.txt
   ```

2. **Analizzare pattern:**
   - A quale % si blocca? (72%, 75%, 85%?)
   - Quanto tempo? (600s? 120s?)
   - Ogni volta o sporadico?

3. **Next Steps:**
   - Se blocco a 72% (Analysis): aumentare PYINSTALLER_TIMEOUT a 900s
   - Se blocco a 75% (Building): verificare memoria disponibile
   - Se blocco a 85%+ (Linking): possibile file system issue

---

## 🎯 Success Criteria

Build riuscito quando vedi:
```
[Progress] 100% - ✓ Build completato!
[EXE] /path/to/main.exe (145.3 MB)
[ZIP] /path/to/villa_segreta_v1.0.zip (98.5 MB, 2340 file)
[Build Complete] Tempo totale: 45.1s
```

E il file ZIP è verificabile:
```bash
unzip -t build/villa_segreta/1.0/villa_segreta_v1.0.zip
Archive:  build/villa_segreta/1.0/villa_segreta_v1.0.zip
    testing: main.exe                 OK
    testing: config.ini               OK
    testing: games/villa_segreta/     OK
...
    No errors detected in compressed data.
```

---

**Last Updated:** 2026-04-16  
**Build System Status:** ✅ Production Ready
