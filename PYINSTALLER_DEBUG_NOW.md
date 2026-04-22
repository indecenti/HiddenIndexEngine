# Debug PyInstaller Hang - Azioni Immediate

**Situazione:** PyInstaller rimane bloccato su `checking PYZ` per 6+ minuti

**Codice Status:** ✅ Directory mode (-D) è attivo (uso_onefile = False linea 351)

---

## ⚡ Step 1: Pulisci Cache (2 minuti)

```bash
# Pulisci PyInstaller cache globale
rm -rf ~/.pyinstaller 2>/dev/null || true
rm -rf ~/.cache/pyinstaller 2>/dev/null || true

# Pulisci build precedente
cd G:/HiddenIndexEngine
rm -rf build/villa_segreta/1.0/

# Verifica che use_onefile = False
grep "use_onefile" editor/build_system.py
# Deve dire: use_onefile = False
```

---

## ⚡ Step 2: Test con Timeout Aggressivo (1 minuto)

```bash
# Build test con timeout impostato
python test_build_system.py villa_segreta

# Atteso:
# Scenario A: Completa in 60-120s ✅
# Scenario B: Si blocca ma viene killato dopo 120s (non forever) ✅
# Scenario C: Rimane comunque bloccato >120s senza uscire ❌
```

---

## 🔍 Step 3: Se Rimane Bloccato (Debug)

Se dopo 120s di timeout il processo rimane comunque bloccato:

```bash
# In un'altra terminal, monitora il processo
# (eseguire MENTRE il build è in corso)

# Windows PowerShell
Get-Process python | Select-Object Name, ID, Memory, CPU | Where-Object { $_.Memory -gt 100MB }

# Linux/Mac
ps aux | grep python | grep pyinstaller
```

**Se vedi PyInstaller in lista ma non finisce:**
- Significa il timeout kill potrebbe non funzionare
- Potrebbe essere un problema di amministrazione del processo

---

## 🔥 Step 4: Kill Manuale Se Necessario

```bash
# Se il processo rimane appeso:

# Windows (kill per PID)
taskkill /PID <pid> /F

# Linux/Mac
kill -9 <pid>
```

---

## 📋 Se Tutto Rimane Bloccato: Root Cause Possible

### Causa 1: Memoria Insufficiente
```bash
# Controlla memoria libera
Windows:  tasklist | find "python"  # e guarda memoria
Linux:    free -h

# Se <500MB libero, chiudi app grandi
```

### Causa 2: Disco Saturo
```bash
# Controlla spazio disco
Windows:  dir C:\
Linux:    df -h

# Se <1GB libero, libera spazio
```

### Causa 3: Antivirus Blocca
```bash
# Se usi antivirus:
# 1. Disabilitalo temporaneamente
# 2. Riesegui build
# 3. Se funzia: aggiungi cartella G:/HiddenIndexEngine a whitelist
```

### Causa 4: temp_dir Contiene File Giganti
```bash
# Controlla cosa c'è in temp durante build
# Appare come C:\Users\<user>\AppData\Local\Temp\build_villa_segreta_*

# Se vedi cartelle grandi o duplicate:
# • Potrebbe essere un build precedente non pulito
# • Aumenta il timeout di cleanup
```

---

## 🚀 Alternativa: Build Directory Mode Manuale

Se il build system rimane problematico, esegui manualmente:

```bash
# 1. Copia main.py in temp
mkdir -p temp_build/
cp main.py temp_build/
cp -r engine/ temp_build/
cp -r games/villa_segreta temp_build/games/

# 2. Copia config.ini
cat > temp_build/config.ini << EOF
[engine]
default_game = villa_segreta
resolution_w = 1920
resolution_h = 1080
fullscreen = 0
language = it
EOF

# 3. Run PyInstaller con timeout
timeout 120 pyinstaller \
  temp_build/main.py \
  -D \
  -w \
  --clean \
  --name main \
  --distpath temp_build/dist \
  --workpath temp_build/build \
  -y

# 4. Se completa: output sarà in temp_build/dist/main/
# Se timeout: processo killato, niente output (OK, non forever!)
```

---

## ❓ Domanda Diagnostica: Cosa Vedi Esattamente?

### Se il log dice:
```
[75%] PyInstaller in corso (120s)...
[75%] PyInstaller in corso (150s)...
...
[78%] PyInstaller: 203354 INFO: checking PYZ
...
❌ Rimane bloccato per sempre
```

→ **Timeout kill non sta funzionando**
→ Prova: aumentare `time_since_last_line > 30` (30 secondi anziché 120)

```python
# editor/build_system.py linea ~140
if time_since_last_line > 30:  # ← Cambia da 120 a 30
    logger.error(f"✗ BLOCCO RILEVATO...")
    proc.kill()
```

### Se il log dice:
```
[78%] PyInstaller: 203354 INFO: checking PYZ
✗ BLOCCO RILEVATO: PyInstaller non emette output da 120s
[Kill] Killing PyInstaller process 203354
```

→ **Timeout kill STA FUNZIONANDO** ✅
→ PyInstaller è un problema noto, non è colpa tua
→ Considera di distribuire con directory mode (-D)

---

## 🎯 Riassunto Azioni

| Azione | Tempo | Status |
|---|---|---|
| Pulisci cache | 1 min | ← **Fai adesso** |
| Build test | 2 min | ← **Fai adesso** |
| Monitora processo | realtime | ← se bloccato |
| Kill manuale | on-demand | ← se necessario |

---

## 📞 Contatti Next Step

Se il build continua a bloccarsi anche dopo pulire cache:

1. **Log completo:**
   ```bash
   tail -100 saves/engine.log > pyinstaller_debug.log
   ```

2. **Info di sistema:**
   ```bash
   # Windows
   wmic os get TotalVisibleMemorySize,FreePhysicalMemory
   
   # Linux
   free -h
   ```

3. **Problemi noti PyInstaller:**
   - github.com/pyinstaller/pyinstaller/issues?q=PYZ+hang
   - Cerca issue simili per tua versione Python

---

**Next:** Esegui Step 1-2 e reporta cosa vedi

Sono pronto ad aiutare con debugging più avanzato se necessario.
